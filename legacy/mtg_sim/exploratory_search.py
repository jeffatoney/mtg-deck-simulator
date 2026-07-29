"""Phase 8 bounded exploratory-search scaffolding.

Search is deliberately split from hidden executor state: :class:`ExploratorySearch`
receives only a policy-visible :class:`mtg_sim.domain.Observation`, a
:class:`BeliefState`, and prevalidated public action summaries. Hidden ordered
libraries stay with the executor-side candidate builder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import random
from typing import Callable, Iterable, Sequence

from mtg_sim.domain import Observation
from mtg_sim.engine import Action, GameState, generate_legal_actions, validate_action
from mtg_sim.policies import PolicyDecision, observation_digest
from mtg_sim.rng import ScenarioSeed


class ExploratorySearchError(ValueError):
    """Raised when Phase 8 search safeguards are violated."""


MAX_CANDIDATE_BRANCHES_PER_DECISION = 12
MAX_LOOKAHEAD_PLAYER_TURNS = 3
MAX_EVALUATED_NODES_PER_GAME = 5_000
MAX_RETAINED_ACTIONS_PER_LAYER = 8
UNKNOWN_DRAW_SAMPLE_COUNT = 8


class ResultCategory(StrEnum):
    FIRST_SELECTED_EXPLORATORY_POLICY = "first_selected_exploratory_policy"
    BEST_BOUNDED_SEARCH = "best_bounded_search"
    LATER_MANUAL_REPLAY = "later_manual_replay"


@dataclass(frozen=True, slots=True)
class BeliefState:
    """Policy-visible uncertainty summary for unknown future draws."""

    unseen_card_multiset: tuple[str, ...]
    library_size: int
    scenario_seed: int
    decision_id: str
    sample_count: int = UNKNOWN_DRAW_SAMPLE_COUNT

    def __post_init__(self) -> None:
        if self.library_size < 0:
            raise ExploratorySearchError("belief library size cannot be negative")
        if len(self.unseen_card_multiset) < self.library_size:
            raise ExploratorySearchError("belief state has fewer unseen cards than unknown slots")
        if self.sample_count <= 0:
            raise ExploratorySearchError("unknown draws require at least one sample")

    def sample_unknown_draws(
        self, *, depth: int, action_id: str
    ) -> tuple[tuple[int, str | None], ...]:
        """Sample expected-value draws from the named unknown_draw stream only."""

        samples: list[tuple[int, str | None]] = []
        seed = ScenarioSeed(self.scenario_seed)
        for sample_index in range(self.sample_count):
            sample_seed = seed.derive_int(
                "unknown_draw", self.decision_id, depth, action_id, sample_index
            )
            rng = random.Random(sample_seed)
            card = rng.choice(self.unseen_card_multiset) if self.unseen_card_multiset else None
            samples.append((sample_seed, card))
        return tuple(samples)


@dataclass(frozen=True, slots=True)
class SearchScore:
    """Lexicographic Phase 8 evaluation score."""

    immediate_legal_table_win: int = 0
    protected_table_win: int = 0
    earliest_expected_win_turn: int = 99
    independent_second_line_available: int = 0
    cards_accessed: int = 0
    net_usable_mana: int = 0
    resilient_board_position: int = 0

    def rank_tuple(self) -> tuple[int, int, int, int, int, int, int]:
        return (
            self.immediate_legal_table_win,
            self.protected_table_win,
            -self.earliest_expected_win_turn,
            self.independent_second_line_available,
            self.cards_accessed,
            self.net_usable_mana,
            self.resilient_board_position,
        )


@dataclass(frozen=True, slots=True)
class PublicActionCandidate:
    action_id: str
    label: str
    validation_rules_refs: tuple[str, ...]
    accepted_by_shared_validator: bool
    score_hint: SearchScore = field(default_factory=SearchScore)

    @classmethod
    def from_action(
        cls, action: Action, *, index: int, score_hint: SearchScore | None = None
    ) -> PublicActionCandidate:
        label = action.action_type.value
        if action.source_name:
            label = f"{label}:{action.source_name}"
        digest = hashlib.sha256(f"{index}:{label}:{action.targets}".encode()).hexdigest()[:16]
        return cls(digest, label, (), True, score_hint or SearchScore())


@dataclass(frozen=True, slots=True)
class SearchLogEntry:
    decision_id: str
    candidate_count: int
    branches_searched: int
    nodes_evaluated: int
    maximum_depth: int
    beam_pruning: tuple[str, ...]
    rollout_sample_seeds: tuple[int, ...]
    evaluation_score: SearchScore
    selected_action_id: str | None
    actual_hidden_future_order_inaccessible: bool
    first_standard_exploratory_divergence: str | None


@dataclass(frozen=True, slots=True)
class SearchResult:
    category: ResultCategory
    selected_action: PublicActionCandidate | None
    best_bounded_action: PublicActionCandidate | None
    log: SearchLogEntry


ScoreEvaluator = Callable[[PublicActionCandidate, tuple[str | None, ...], int], SearchScore]


def default_evaluator(
    action: PublicActionCandidate, sampled_cards: tuple[str | None, ...], depth: int
) -> SearchScore:
    """Conservative public evaluator using action hints plus sampled access count."""

    extra_cards = len([card for card in sampled_cards if card is not None])
    hint = action.score_hint
    return SearchScore(
        hint.immediate_legal_table_win,
        hint.protected_table_win,
        min(hint.earliest_expected_win_turn, depth)
        if hint.immediate_legal_table_win
        else hint.earliest_expected_win_turn,
        hint.independent_second_line_available,
        hint.cards_accessed + extra_cards,
        hint.net_usable_mana,
        hint.resilient_board_position,
    )


class ExploratorySearch:
    """Bounded beam search over public, prevalidated candidate summaries."""

    def __init__(self, evaluator: ScoreEvaluator = default_evaluator) -> None:
        self.evaluator = evaluator

    def choose(
        self,
        *,
        observation: Observation,
        belief: BeliefState,
        candidates: Sequence[PublicActionCandidate],
        standard_decision: PolicyDecision | None = None,
    ) -> SearchResult:
        if observation.known_top_library:
            raise ExploratorySearchError("Observation exposes actual future library information")
        if belief.library_size != observation.library_size:
            raise ExploratorySearchError("belief state must match visible library size")
        if any(not candidate.accepted_by_shared_validator for candidate in candidates):
            raise ExploratorySearchError(
                "exploratory search received an action not accepted by the shared legality validator"
            )
        branch_count = min(len(candidates), MAX_CANDIDATE_BRANCHES_PER_DECISION)
        considered = list(candidates[:branch_count])
        beam_pruning: list[str] = []
        if len(candidates) > MAX_CANDIDATE_BRANCHES_PER_DECISION:
            beam_pruning.append("candidate_branch_limit_12")
        nodes = 0
        max_depth = 0
        rollout_seeds: list[int] = []
        ranked: list[
            tuple[tuple[int, int, int, int, int, int, int], PublicActionCandidate, SearchScore]
        ] = []
        for depth in range(1, MAX_LOOKAHEAD_PLAYER_TURNS + 1):
            layer: list[
                tuple[tuple[int, int, int, int, int, int, int], PublicActionCandidate, SearchScore]
            ] = []
            for action in considered:
                if nodes >= MAX_EVALUATED_NODES_PER_GAME:
                    beam_pruning.append("node_limit_5000")
                    break
                samples = belief.sample_unknown_draws(depth=depth, action_id=action.action_id)
                rollout_seeds.extend(seed for seed, _ in samples)
                nodes += 1 + len(samples)
                sampled_cards = tuple(card for _, card in samples)
                score = self.evaluator(action, sampled_cards, depth)
                layer.append((score.rank_tuple(), action, score))
                max_depth = depth
            ranked.extend(layer)
            ranked.sort(key=lambda item: item[0], reverse=True)
            if len(ranked) > MAX_RETAINED_ACTIONS_PER_LAYER:
                ranked = ranked[:MAX_RETAINED_ACTIONS_PER_LAYER]
                beam_pruning.append("beam_width_8")
            considered = [item[1] for item in ranked]
            if nodes >= MAX_EVALUATED_NODES_PER_GAME:
                break
        best = ranked[0] if ranked else None
        selected = considered[0] if considered else None
        divergence = None
        if standard_decision and selected and selected.label != standard_decision.choice:
            divergence = f"standard={standard_decision.choice};exploratory={selected.label}"
        log = SearchLogEntry(
            decision_id=observation_digest(observation),
            candidate_count=len(candidates),
            branches_searched=branch_count,
            nodes_evaluated=nodes,
            maximum_depth=max_depth,
            beam_pruning=tuple(beam_pruning),
            rollout_sample_seeds=tuple(rollout_seeds),
            evaluation_score=best[2] if best else SearchScore(),
            selected_action_id=selected.action_id if selected else None,
            actual_hidden_future_order_inaccessible=True,
            first_standard_exploratory_divergence=divergence,
        )
        return SearchResult(
            ResultCategory.BEST_BOUNDED_SEARCH, selected, best[1] if best else None, log
        )


def validated_public_candidates_from_engine_state(
    state: GameState,
) -> tuple[PublicActionCandidate, ...]:
    """Executor-side adapter: hidden state may generate actions, then strips it away."""

    candidates: list[PublicActionCandidate] = []
    for index, action in enumerate(generate_legal_actions(state)):
        result = validate_action(state, action)
        if not result.accepted:
            continue
        label = action.action_type.value + (f":{action.source_name}" if action.source_name else "")
        action_id = hashlib.sha256(f"{index}:{label}".encode()).hexdigest()[:16]
        candidates.append(
            PublicActionCandidate(
                action_id, label, result.rules_refs, result.accepted, SearchScore()
            )
        )
    return tuple(candidates)


def reject_cross_policy_result_access(
    *, current_policy_id: str, requested_result_policy_id: str
) -> None:
    if current_policy_id != requested_result_policy_id:
        raise ExploratorySearchError("exploratory search cannot access another policy result")


def reject_opponent_dependent_line(
    *, opponent_resources_specified: bool, opponent_choice_policy: str
) -> None:
    if not opponent_resources_specified:
        raise ExploratorySearchError(
            "unspecified opponent resources cannot support deterministic exploratory lines"
        )
    if opponent_choice_policy == "favorable_to_this_deck":
        raise ExploratorySearchError("favorable opponent choices are prohibited")


@dataclass(frozen=True, slots=True)
class ExploratoryResultRecord:
    seed: int
    category: ResultCategory
    result_ref: str
    selected_before_result_known: bool = True
    used_actual_future_information: bool = False
    replayed_after_failure_only: bool = False

    def validate(self) -> None:
        if self.used_actual_future_information:
            raise ExploratorySearchError("actual future information is prohibited")
        if self.replayed_after_failure_only:
            raise ExploratorySearchError("post-result optimization is prohibited")
        if (
            self.category is ResultCategory.LATER_MANUAL_REPLAY
            and self.selected_before_result_known
        ):
            raise ExploratorySearchError("manual replay results must be reported separately")


def validate_replay_seed_set(
    *, planned_seeds: Iterable[int], replayed_seeds: Iterable[int], failed_seeds: Iterable[int]
) -> None:
    planned = tuple(planned_seeds)
    replayed = tuple(replayed_seeds)
    failed = set(failed_seeds)
    if len(replayed) != len(set(replayed)):
        raise ExploratorySearchError("duplicate selective replay seed detected")
    if set(replayed).difference(planned):
        raise ExploratorySearchError("replay contains a seed outside the precommitted plan")
    if replayed and set(replayed).issubset(failed) and set(replayed) != set(planned):
        raise ExploratorySearchError("replaying only failed seeds is prohibited")
