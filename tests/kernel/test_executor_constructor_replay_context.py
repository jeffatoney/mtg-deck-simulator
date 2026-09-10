"""Class invariants for constructor replay execution-context synchronization."""

from __future__ import annotations

from copy import deepcopy

import pytest

from mtg_kernel.engine import GameExecutor
from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import new_game
from mtg_kernel.serialization import state_to_data

PLAYERS = ("P0", "P1", "P2", "P3")
_RECORDED_COMMAND = {"operation": "test-only-recorded-command", "arguments": {}}


def _state_with_existing_replay_snapshot(seed: str) -> tuple[object, object]:
    state, setup = new_game(PLAYERS, seed)
    snapshot = state_to_data(state)
    assert "execution_context" not in snapshot
    state.replay_initial_state = snapshot
    return state, setup


def test_constructor_synchronizes_existing_snapshot_for_explicit_no_known_colors() -> None:
    state, setup = _state_with_existing_replay_snapshot(
        "kernel-constructor-replay-context-no-known-colors"
    )

    executor = GameExecutor(
        state,
        setup.seed,
        opponent_mana_profile="no_known_colors",
    )

    assert executor.opponent_mana_profile == "no_known_colors"
    assert state.replay_initial_state is not None
    assert state.replay_initial_state["execution_context"] == {
        "opponent_mana_profile": "no_known_colors"
    }


def test_constructor_default_profile_does_not_add_execution_context() -> None:
    state, setup = _state_with_existing_replay_snapshot("kernel-constructor-replay-context-default")

    executor = GameExecutor(
        state,
        setup.seed,
        opponent_mana_profile="blue_red_available",
    )

    assert executor.opponent_mana_profile == "blue_red_available"
    assert state.replay_initial_state is not None
    assert "execution_context" not in state.replay_initial_state


def test_constructor_malformed_existing_execution_context_fails_closed() -> None:
    state, setup = _state_with_existing_replay_snapshot(
        "kernel-constructor-replay-context-malformed"
    )
    assert state.replay_initial_state is not None
    state.replay_initial_state["execution_context"] = ["no_known_colors"]

    with pytest.raises(IllegalAction, match="replay execution context is malformed"):
        GameExecutor(
            deepcopy(state),
            setup.seed,
            opponent_mana_profile="no_known_colors",
        )


def test_constructor_matching_recorded_history_restores_without_setter() -> None:
    state, setup = _state_with_existing_replay_snapshot(
        "kernel-constructor-replay-context-matching-history"
    )
    assert state.replay_initial_state is not None
    state.replay_initial_state["execution_context"] = {"opponent_mana_profile": "no_known_colors"}
    state.replay_commands.append(dict(_RECORDED_COMMAND))

    executor = GameExecutor(
        state,
        setup.seed,
        opponent_mana_profile="no_known_colors",
    )

    assert executor.opponent_mana_profile == "no_known_colors"
    assert state.replay_initial_state["execution_context"] == {
        "opponent_mana_profile": "no_known_colors"
    }
    with pytest.raises(
        IllegalAction,
        match="opponent mana profile cannot change after replay recording begins",
    ):
        executor.opponent_mana_profile = "blue_red_available"


@pytest.mark.parametrize(
    ("recorded_profile", "constructor_profile"),
    (
        (None, "no_known_colors"),
        ("no_known_colors", "blue_red_available"),
    ),
)
def test_constructor_conflicting_recorded_history_fails_closed(
    recorded_profile: str | None,
    constructor_profile: str,
) -> None:
    state, setup = _state_with_existing_replay_snapshot(
        f"kernel-constructor-replay-context-conflict-{constructor_profile}"
    )
    assert state.replay_initial_state is not None
    if recorded_profile is not None:
        state.replay_initial_state["execution_context"] = {
            "opponent_mana_profile": recorded_profile
        }
    state.replay_commands.append(dict(_RECORDED_COMMAND))

    with pytest.raises(
        IllegalAction,
        match="opponent mana profile cannot change after replay recording begins",
    ):
        GameExecutor(
            deepcopy(state),
            setup.seed,
            opponent_mana_profile=constructor_profile,
        )
    if recorded_profile is None:
        assert "execution_context" not in state.replay_initial_state
    else:
        assert state.replay_initial_state["execution_context"] == {
            "opponent_mana_profile": recorded_profile
        }
