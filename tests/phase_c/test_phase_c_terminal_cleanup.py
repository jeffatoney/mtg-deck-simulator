from __future__ import annotations

from mtg_runs.phase_c_runner import run_phase_c_game_execution


def test_700_diagnostic_terminal_cleanup_seed_stops_cleanly() -> None:
    execution = run_phase_c_game_execution(
        seed=391730338978874520,
        mode="STANDARD",
        through_turn=10,
        validate_fresh_replay=True,
        policy_actions=True,
    )

    assert execution.technical_game.terminal_status == "TERMINAL"
    assert 0 < execution.technical_game.controlled_turns_completed <= 10
    assert (
        execution.technical_game.fresh_replay_state_hash
        == execution.technical_game.final_state_hash
    )
