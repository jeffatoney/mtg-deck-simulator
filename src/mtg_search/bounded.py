"""Frozen bounded search over policy-visible observations and legal action descriptions."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from mtg_policy.broker import ObservedAction

_FORBIDDEN_KEYS = {
    "library_order",
    "future_events",
    "future_random_outcomes",
    "card_instance_ids",
    "object_ids",
    "replay_commands",
    "rng_streams",
}


def _assert_public(value: Any, path: str = "observation") -> None:
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key)
            if (
                key in _FORBIDDEN_KEYS
                or key.endswith("_object_id")
                or key.endswith("_card_instance_id")
            ):
                raise ValueError(f"search input exposes forbidden hidden field: {path}.{key}")
            _assert_public(item, f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _assert_public(item, f"{path}[{index}]")


@dataclass(frozen=True)
class SearchLimits:
    """The exact frozen Phase B search limits."""

    maximum_branches: int = 12
    maximum_player_turns: int = 3
    maximum_nodes: int = 5_000
    beam_width: int = 8
    maximum_belief_samples: int = 8

    def __post_init__(self) -> None:
        expected = (12, 3, 5_000, 8, 8)
        actual = (
            self.maximum_branches,
            self.maximum_player_turns,
            self.maximum_nodes,
            self.beam_width,
            self.maximum_belief_samples,
        )
        if actual != expected:
            raise ValueError(f"Phase B search limits are frozen at {expected}, received {actual}")


@dataclass(frozen=True)
class SearchEvaluation:
    """Integer-only values in the frozen lexicographic ranking order."""

    immediate_legal_table_win: bool = False
    protected_table_win: bool = False
    expected_win_turn: int = 99
    independent_second_lines: int = 0
    cards_accessed: int = 0
    net_usable_mana: int = 0
    resilient_board: int = 0

    def __post_init__(self) -> None:
        if self.expected_win_turn < 0:
            raise ValueError("expected win turn cannot be negative")
        for value in (
            self.independent_second_lines,
            self.cards_accessed,
            self.net_usable_mana,
            self.resilient_board,
        ):
            if value < 0:
                raise ValueError("search evaluation counts cannot be negative")

    def totals(self) -> tuple[int, int, int, int, int, int, int]:
        return (
            int(self.immediate_legal_table_win),
            int(self.protected_table_win),
            self.expected_win_turn,
            self.independent_second_lines,
            self.cards_accessed,
            self.net_usable_mana,
            self.resilient_board,
        )


@dataclass(frozen=True)
class SearchPosition:
    """One search node containing only public observation and legal descriptions."""

    observation: Mapping[str, Any]
    actions: tuple[ObservedAction, ...]
    evaluation: SearchEvaluation
    player_turns_elapsed: int = 0

    def __post_init__(self) -> None:
        _assert_public(self.observation)
        if self.player_turns_elapsed < 0:
            raise ValueError("player_turns_elapsed cannot be negative")
        for action in self.actions:
            _assert_public(action.metadata, f"action[{action.handle}].metadata")
            if not action.handle:
                raise ValueError("search actions require opaque handles")


@dataclass(frozen=True)
class SearchDecisionLog:
    candidate_count: int
    branches_searched: int
    nodes_evaluated: int
    depth_reached: int
    pruning_reasons: tuple[str, ...]
    belief_state_sample_seeds: tuple[int, ...]
    selected_action: str
    actual_hidden_future_inaccessible: bool
    post_result_replay_attempts: int
    future_information_rejections: int
    post_result_optimization_rejections: int


@dataclass(frozen=True)
class SearchResult:
    selected_action: str
    log: SearchDecisionLog


Expand = Callable[[SearchPosition, ObservedAction, int], SearchPosition]


@dataclass(frozen=True)
class _FrontierNode:
    root_handle: str
    position: SearchPosition


def _mean_rank(evaluations: Sequence[SearchEvaluation]) -> tuple[Fraction, ...]:
    if not evaluations:
        raise ValueError("cannot rank an empty evaluation set")
    count = len(evaluations)
    totals = [0] * 7
    for evaluation in evaluations:
        for index, value in enumerate(evaluation.totals()):
            totals[index] += value
    return (
        Fraction(totals[0], count),
        Fraction(totals[1], count),
        Fraction(-totals[2], count),
        Fraction(totals[3], count),
        Fraction(totals[4], count),
        Fraction(totals[5], count),
        Fraction(totals[6], count),
    )


class BoundedExplorer:
    """Apply one frozen search procedure to every eligible exploratory decision."""

    def __init__(self, limits: SearchLimits | None = None) -> None:
        self.limits = limits or SearchLimits()

    def choose(
        self,
        root: SearchPosition,
        *,
        belief_sample_seeds: Sequence[int],
        expand: Expand,
    ) -> SearchResult:
        if not root.actions:
            raise ValueError("exploratory search received no legal actions")
        seeds = tuple(int(value) for value in belief_sample_seeds)
        if not seeds:
            raise ValueError("exploratory search requires precommitted belief sample seeds")
        if len(seeds) > self.limits.maximum_belief_samples:
            raise ValueError("belief sample count exceeds the frozen maximum of eight")
        if len(set(seeds)) != len(seeds):
            raise ValueError("belief sample seeds must be unique")

        pruning: set[str] = set()
        root_actions = tuple(sorted(root.actions, key=lambda action: action.handle))
        if len(root_actions) > self.limits.maximum_branches:
            root_actions = root_actions[: self.limits.maximum_branches]
            pruning.add("candidate_cap")

        evaluations: dict[str, list[SearchEvaluation]] = defaultdict(list)
        frontier: list[_FrontierNode] = []
        nodes = 0
        depth_reached = 0

        for action in root_actions:
            for seed in seeds:
                if nodes >= self.limits.maximum_nodes:
                    pruning.add("node_cap")
                    break
                successor = expand(root, action, seed)
                _assert_public(successor.observation)
                nodes += 1
                depth_reached = max(depth_reached, successor.player_turns_elapsed)
                evaluations[action.handle].append(successor.evaluation)
                frontier.append(_FrontierNode(action.handle, successor))

        depth = 1
        while frontier and depth < self.limits.maximum_player_turns:
            ranked_frontier = sorted(
                frontier,
                key=lambda node: (
                    _mean_rank((node.position.evaluation,)),
                    node.root_handle,
                ),
                reverse=True,
            )
            if len(ranked_frontier) > self.limits.beam_width:
                ranked_frontier = ranked_frontier[: self.limits.beam_width]
                pruning.add("beam_width")
            next_frontier: list[_FrontierNode] = []
            for node in ranked_frontier:
                candidate_actions = tuple(
                    sorted(node.position.actions, key=lambda action: action.handle)
                )
                if len(candidate_actions) > self.limits.maximum_branches:
                    candidate_actions = candidate_actions[: self.limits.maximum_branches]
                    pruning.add("candidate_cap")
                for action in candidate_actions:
                    for seed in seeds:
                        if nodes >= self.limits.maximum_nodes:
                            pruning.add("node_cap")
                            break
                        successor = expand(node.position, action, seed)
                        if successor.player_turns_elapsed > self.limits.maximum_player_turns:
                            pruning.add("depth_cap")
                            continue
                        nodes += 1
                        depth_reached = max(depth_reached, successor.player_turns_elapsed)
                        evaluations[node.root_handle].append(successor.evaluation)
                        next_frontier.append(_FrontierNode(node.root_handle, successor))
                    if nodes >= self.limits.maximum_nodes:
                        break
                if nodes >= self.limits.maximum_nodes:
                    break
            frontier = next_frontier
            depth += 1

        if frontier:
            pruning.add("depth_cap")
        if not evaluations:
            raise ValueError("search bounds prevented every candidate from being evaluated")

        ranked_roots = sorted(
            evaluations,
            key=lambda handle: (_mean_rank(evaluations[handle]), tuple(-ord(c) for c in handle)),
            reverse=True,
        )
        selected = ranked_roots[0]
        log = SearchDecisionLog(
            candidate_count=len(root.actions),
            branches_searched=len(evaluations),
            nodes_evaluated=nodes,
            depth_reached=depth_reached,
            pruning_reasons=tuple(sorted(pruning)),
            belief_state_sample_seeds=seeds,
            selected_action=selected,
            actual_hidden_future_inaccessible=True,
            post_result_replay_attempts=0,
            future_information_rejections=0,
            post_result_optimization_rejections=0,
        )
        return SearchResult(selected, log)
