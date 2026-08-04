"""Bounded exploratory search acceptance tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from mtg_policy.broker import ObservedAction
from mtg_search import BoundedExplorer, SearchEvaluation, SearchPosition


def action(handle: str, value: int) -> ObservedAction:
    return ObservedAction(handle, "TEST", None, 0, (f"VALUE_{value}",), 0, {"value": value})


def position(actions: tuple[ObservedAction, ...], value: int = 0, turns: int = 0) -> SearchPosition:
    return SearchPosition(
        observation={"generation": 1, "turn": {"number": turns + 1}, "public_value": value},
        actions=actions,
        evaluation=SearchEvaluation(cards_accessed=value),
        player_turns_elapsed=turns,
    )


def test_bounded_search_enforces_frozen_limits_and_expected_value() -> None:
    root_actions = tuple(action(f"a{index:02d}", index) for index in range(15))
    root = position(root_actions)

    def expand(parent: SearchPosition, selected: ObservedAction, seed: int) -> SearchPosition:
        value = int(selected.metadata["value"]) + (seed % 2)
        next_actions = tuple(
            action(f"{selected.handle}-{index}", value + index) for index in range(10)
        )
        return position(next_actions, value, min(3, parent.player_turns_elapsed + 1))

    result = BoundedExplorer().choose(root, belief_sample_seeds=(11, 12), expand=expand)
    assert result.selected_action == "a11"
    assert result.log.candidate_count == 15
    assert result.log.branches_searched == 12
    assert result.log.nodes_evaluated <= 5_000
    assert result.log.depth_reached <= 3
    assert set(result.log.pruning_reasons) >= {"candidate_cap", "beam_width", "depth_cap"}
    assert result.log.actual_hidden_future_inaccessible is True
    assert result.log.post_result_replay_attempts == 0


def test_search_rejects_hidden_future_fields_and_more_than_eight_samples() -> None:
    with pytest.raises(ValueError, match="forbidden hidden field"):
        SearchPosition(
            {"generation": 1, "turn": {}, "library_order": ["A"]},
            (action("a", 1),),
            SearchEvaluation(),
        )
    root = position((action("a", 1),))
    with pytest.raises(ValueError, match="maximum of eight"):
        BoundedExplorer().choose(
            root,
            belief_sample_seeds=tuple(range(9)),
            expand=lambda parent, selected, seed: replace(parent, player_turns_elapsed=1),
        )


def test_node_budget_is_cumulative_across_major_decisions_in_one_game() -> None:
    root_actions = tuple(action(f"a{index:02d}", index) for index in range(12))
    root = position(root_actions)

    def expand(parent: SearchPosition, selected: ObservedAction, seed: int) -> SearchPosition:
        value = int(selected.metadata["value"]) + (seed % 2)
        next_actions = tuple(
            action(f"{selected.handle}-{index}", value + index) for index in range(12)
        )
        return position(next_actions, value, min(3, parent.player_turns_elapsed + 1))

    explorer = BoundedExplorer()
    latest = None
    for _ in range(4):
        latest = explorer.choose(root, belief_sample_seeds=tuple(range(8)), expand=expand)
    assert latest is not None
    assert latest.log.game_nodes_used == 5_000
    assert explorer.game_nodes_used == 5_000
    with pytest.raises(ValueError, match="node budget is exhausted"):
        explorer.choose(root, belief_sample_seeds=(1,), expand=expand)

    explorer.begin_game()
    reset = explorer.choose(root, belief_sample_seeds=(1,), expand=expand)
    assert 0 < reset.log.game_nodes_used < 5_000
