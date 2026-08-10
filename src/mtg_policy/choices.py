"""Policy-layer providers for rules-defined strategic choices."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from mtg_kernel.errors import UnsupportedCapability
from mtg_kernel.strategic_choices import (
    CardSelection,
    CardSelectionRequest,
    FactOrFictionRequest,
    FactOrFictionSelection,
    OptionalTriggerRequest,
    OptionalTriggerSelection,
    SpellCopyTargetRequest,
    SpellCopyTargetSelection,
    TutorChoiceRequest,
    TutorChoiceSelection,
)
from mtg_policy.config import PolicyBundle
from mtg_policy.evaluation import ContextualEvaluator, EvaluatorConfig, score_to_microunits

if TYPE_CHECKING:
    from mtg_kernel.engine import GameExecutor


DUALCASTER_LOOP_ADJUDICATOR = "VISIBLE_LIFE_AND_BLOCKER_RESERVE_V1"
MAX_DUALCASTER_LOOP_TOKENS = 512
_SUPPORTED_DUALCASTER_LOOP_MODES = frozenset({"FAIL_CLOSED_UNTIL_DETERMINISTIC_LOOP_ADJUDICATOR"})
_SUPPORTED_OPTIONAL_TRIGGERS = frozenset({("curiosity:damage", "DRAW")})


def dualcaster_loop_adjudication_supported(config: EvaluatorConfig) -> bool:
    """Return whether the frozen evaluator mode has a production policy adjudicator."""

    return config.dualcaster_loop_handling in _SUPPORTED_DUALCASTER_LOOP_MODES


def _dualcaster_loop_selection(
    request: SpellCopyTargetRequest,
) -> tuple[tuple[str, ...], dict[str, Any]]:
    """Choose a finite Twinflame loop bound from current public combat information."""

    life = request.observation.get("life")
    objects = request.observation.get("objects")
    if not isinstance(life, Mapping) or not isinstance(objects, Sequence):
        raise UnsupportedCapability(
            "canonical Dualcaster/Twinflame loop adjudication is not implemented for "
            "observations without complete visible life and battlefield state"
        )

    opponent_life: dict[str, int] = {}
    for player_id, raw_life in life.items():
        player = str(player_id)
        if player == request.actor_id:
            continue
        if isinstance(raw_life, bool) or not isinstance(raw_life, int) or raw_life < 0:
            raise UnsupportedCapability(
                "canonical Dualcaster/Twinflame loop adjudication is not implemented for "
                "malformed visible life state"
            )
        if raw_life > 0:
            opponent_life[player] = raw_life

    visible_dualcasters = 0
    visible_opponent_blockers = 0
    for raw in objects:
        if not isinstance(raw, Mapping) or raw.get("zone") != "BATTLEFIELD":
            continue
        controller = str(raw.get("controller", ""))
        identity = str(raw.get("identity", ""))
        card_types = raw.get("card_types", ())
        types = {str(value) for value in card_types} if isinstance(card_types, Sequence) else set()
        if controller == request.actor_id and identity == "Dualcaster Mage":
            visible_dualcasters += 1
        elif controller in opponent_life and "Creature" in types:
            visible_opponent_blockers += 1

    required_tokens = sum((value + 1) // 2 for value in opponent_life.values())
    required_tokens += visible_opponent_blockers
    if required_tokens > MAX_DUALCASTER_LOOP_TOKENS:
        raise UnsupportedCapability(
            "canonical Dualcaster/Twinflame visible lethal reserve exceeds the bounded "
            f"policy limit of {MAX_DUALCASTER_LOOP_TOKENS} tokens"
        )

    target_by_handle = {card.handle: card for card in request.legal_targets}
    continue_sets = tuple(
        targets
        for targets in request.legal_target_sets
        if len(targets) == 1
        and targets[0] in target_by_handle
        and target_by_handle[targets[0]].identity == "Dualcaster Mage"
    )
    stop_sets = tuple(
        targets
        for targets in request.legal_target_sets
        if all(
            handle in target_by_handle and target_by_handle[handle].identity != "Dualcaster Mage"
            for handle in targets
        )
    )
    selected: tuple[str, ...]
    token_count = max(0, visible_dualcasters - 1)
    if token_count < required_tokens:
        if not continue_sets:
            raise UnsupportedCapability(
                "canonical Dualcaster/Twinflame loop cannot continue through a legal "
                "Dualcaster target"
            )
        selected = min(continue_sets)
        strategy = "CONTINUE_BOUNDED_DUALCASTER_LOOP"
    else:
        if request.original_target_handles in stop_sets:
            selected = request.original_target_handles
        elif stop_sets:
            selected = min(stop_sets)
        else:
            raise UnsupportedCapability(
                "canonical Dualcaster/Twinflame loop cannot stop on a legal non-Dualcaster target"
            )
        strategy = "STOP_BOUNDED_DUALCASTER_LOOP"

    diagnostics: dict[str, Any] = {
        "adjudicator": DUALCASTER_LOOP_ADJUDICATOR,
        "strategy": strategy,
        "token_count": token_count,
        "required_tokens": required_tokens,
        "visible_opponent_life": dict(sorted(opponent_life.items())),
        "visible_opponent_blockers": visible_opponent_blockers,
        "maximum_tokens": MAX_DUALCASTER_LOOP_TOKENS,
    }
    return selected, diagnostics


class PolicyStrategicChoiceProvider:
    """Make deterministic choices from a frozen policy and evaluator snapshot."""

    def __init__(self, bundle: PolicyBundle, evaluator: ContextualEvaluator) -> None:
        self.bundle = bundle
        self.evaluator = evaluator

    @property
    def evaluator_id(self) -> str:
        return self.evaluator.config.evaluator_id

    @property
    def evaluator_sha256(self) -> str:
        return self.evaluator.config.config_sha256

    def choose_cards(self, request: CardSelectionRequest) -> CardSelection:
        if request.minimum < 0 or request.maximum < request.minimum:
            raise ValueError("strategic card-selection bounds are invalid")
        if request.maximum > len(request.candidates):
            raise ValueError("strategic card-selection maximum exceeds candidates")
        evaluations = {
            card.handle: self.evaluator.evaluate_pile((card,), request.observation).score
            for card in request.candidates
        }
        if request.purpose == "DISCARD":
            ordered = sorted(
                request.candidates,
                key=lambda card: (evaluations[card.handle], card.identity, card.handle),
            )
            selected = tuple(card.handle for card in ordered[: request.minimum])
        elif request.purpose == "UNTAP_LANDS":
            selected = tuple(
                card.handle
                for card in sorted(
                    request.candidates,
                    key=lambda card: (
                        -evaluations[card.handle],
                        card.identity,
                        card.handle,
                    ),
                )[: request.maximum]
            )
        elif request.purpose == "LOOK_SELECT":
            if request.minimum != request.maximum:
                raise UnsupportedCapability("LOOK_SELECT requires one exact legal selection count")
            ordered = sorted(
                request.candidates,
                key=lambda card: (
                    -evaluations[card.handle],
                    card.identity,
                    card.handle,
                ),
            )
            selected = tuple(card.handle for card in ordered[: request.minimum])
        elif request.purpose == "ORDER_LIBRARY_BOTTOM":
            if request.minimum != request.maximum or request.minimum != len(request.candidates):
                raise UnsupportedCapability(
                    "ORDER_LIBRARY_BOTTOM requires an exact ordering of every public candidate"
                )
            ordered = sorted(
                request.candidates,
                key=lambda card: (
                    evaluations[card.handle],
                    card.identity,
                    card.handle,
                ),
            )
            selected = tuple(card.handle for card in ordered)
        elif request.purpose.startswith("TUTOR_"):
            # Search effects expose only the rules-eligible candidate set through
            # opaque handles. Rank those candidates with the same frozen tutor
            # preference and contextual evaluator used by choose_tutor(). Hidden
            # object IDs/library positions never cross the policy boundary.
            priority_name = str(self.bundle.value("tutor_priority"))
            priority_order = self.evaluator.config.tutor_priority_orders.get(priority_name, ())
            rank = {name: len(priority_order) - index for index, name in enumerate(priority_order)}
            ordered = sorted(
                request.candidates,
                key=lambda card: (
                    -rank.get(card.identity, 0),
                    -evaluations[card.handle],
                    card.identity,
                    card.handle,
                ),
            )
            # A hidden-zone search may legally fail to find when minimum is zero,
            # but the frozen maximizing policy chooses the best eligible card when
            # one exists. Exact-minimum searches (Long-Term Plans) remain exact.
            choose_count = (
                request.minimum if request.minimum == request.maximum else request.maximum
            )
            selected = tuple(card.handle for card in ordered[:choose_count])
        else:
            raise UnsupportedCapability(
                f"policy card-selection purpose is unsupported: {request.purpose}"
            )
        return CardSelection(
            selected,
            self.evaluator_id,
            self.evaluator_sha256,
            {
                "policy_config_id": self.bundle.policy_config_id,
                "purpose": request.purpose,
                "candidate_evaluation_microunits": {
                    handle: score_to_microunits(value) for handle, value in evaluations.items()
                },
            },
        )

    def choose_tutor(self, request: TutorChoiceRequest) -> TutorChoiceSelection:
        candidates = tuple(request.eligible_cards)
        if not candidates:
            selected = "FAIL_TO_FIND"
            evaluations: dict[str, float] = {}
        else:
            priority_name = str(self.bundle.value("tutor_priority"))
            order = self.evaluator.config.tutor_priority_orders.get(priority_name, ())
            rank = {name: len(order) - index for index, name in enumerate(order)}
            scored = []
            evaluations = {}
            for card in candidates:
                value = self.evaluator.evaluate_pile((card,), request.observation).score
                evaluations[card.identity] = max(evaluations.get(card.identity, value), value)
                scored.append((value, rank.get(card.identity, 0), card.identity))
            selected = max(scored)[2]
        return TutorChoiceSelection(
            selected,
            self.evaluator_id,
            self.evaluator_sha256,
            {
                "policy_config_id": self.bundle.policy_config_id,
                "tutor_priority": self.bundle.value("tutor_priority"),
                "eligible_identities": list(request.eligible_identities),
                "candidate_evaluation_microunits": {
                    name: score_to_microunits(value) for name, value in evaluations.items()
                },
            },
        )

    def choose_fact_or_fiction(self, request: FactOrFictionRequest) -> FactOrFictionSelection:
        if self.evaluator.config.opponent_choice_mode != "PERFECT_MINIMIZER":
            raise ValueError("unsupported opponent Fact or Fiction choice mode")
        cards = {card.handle: card for card in request.revealed_cards}
        candidates: list[tuple[tuple[Any, ...], int, Any, Any]] = []
        for split in request.legal_splits:
            pile_a = [cards[handle] for handle in split.pile_a_handles]
            pile_b = [cards[handle] for handle in split.pile_b_handles]
            eval_a = self.evaluator.evaluate_pile(pile_a, request.observation)
            eval_b = self.evaluator.evaluate_pile(pile_b, request.observation)
            key = (
                max(eval_a.score, eval_b.score),
                abs(eval_a.score - eval_b.score),
                tuple(sorted(split.pile_a_handles)),
                tuple(sorted(split.pile_b_handles)),
            )
            candidates.append((key, split.split_index, eval_a, eval_b))
        _, split_index, eval_a, eval_b = min(candidates, key=lambda item: item[0])
        chosen = (
            "A"
            if (
                eval_a.score,
                len(request.legal_splits[split_index].pile_a_handles),
                tuple(sorted(request.legal_splits[split_index].pile_a_handles)),
            )
            >= (
                eval_b.score,
                len(request.legal_splits[split_index].pile_b_handles),
                tuple(sorted(request.legal_splits[split_index].pile_b_handles)),
            )
            else "B"
        )
        return FactOrFictionSelection(
            split_index,
            chosen,
            self.evaluator_id,
            self.evaluator_sha256,
            {
                "policy_config_id": self.bundle.policy_config_id,
                "opponent_choice_mode": self.evaluator.config.opponent_choice_mode,
                "pile_a_evaluation": eval_a.to_dict(),
                "pile_b_evaluation": eval_b.to_dict(),
                "candidate_split_count": len(candidates),
            },
        )

    def choose_spell_copy_targets(
        self, request: SpellCopyTargetRequest
    ) -> SpellCopyTargetSelection:
        selected = request.original_target_handles
        diagnostics: dict[str, Any] = {
            "policy_config_id": self.bundle.policy_config_id,
            "strategy": "RETAIN_ORIGINAL_TARGETS",
        }
        if (
            request.source_identity == "Dualcaster Mage"
            and request.copied_spell_identity == "Twinflame"
        ):
            if not dualcaster_loop_adjudication_supported(self.evaluator.config):
                raise UnsupportedCapability(
                    "canonical Dualcaster/Twinflame loop adjudication is not implemented "
                    "for the selected evaluator mode"
                )
            selected, loop_diagnostics = _dualcaster_loop_selection(request)
            diagnostics.update(loop_diagnostics)
        if (
            selected != request.original_target_handles
            and selected not in request.legal_target_sets
        ):
            raise ValueError("policy selected a copy target set outside the legal choices")
        return SpellCopyTargetSelection(
            selected,
            self.evaluator_id,
            self.evaluator_sha256,
            diagnostics,
        )

    def choose_optional_trigger(self, request: OptionalTriggerRequest) -> OptionalTriggerSelection:
        if (request.ability_id, request.effect_kind) not in _SUPPORTED_OPTIONAL_TRIGGERS:
            raise UnsupportedCapability(
                "optional trigger policy is unsupported for ability/effect: "
                f"{request.ability_id}/{request.effect_kind}"
            )
        return OptionalTriggerSelection(
            True,
            self.evaluator_id,
            self.evaluator_sha256,
            {
                "policy_config_id": self.bundle.policy_config_id,
                "strategy": "TAKE_REVIEWED_OPTIONAL_TRIGGER",
                "ability_id": request.ability_id,
                "effect_kind": request.effect_kind,
            },
        )


def bind_policy_strategic_choices(
    executor: GameExecutor,
    bundle: PolicyBundle,
    evaluator: ContextualEvaluator,
) -> PolicyStrategicChoiceProvider:
    """Attach one frozen policy/evaluator snapshot to the shared executor."""

    provider = PolicyStrategicChoiceProvider(bundle, evaluator)
    executor.bind_strategic_choice_provider(provider)
    return provider
