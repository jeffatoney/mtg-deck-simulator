from __future__ import annotations

import pytest

from mtg_runs.phase_c_runner import run_phase_c_game_execution


@pytest.mark.parametrize(
    "seed",
    (
        11627205193075648585,  # cleanup repeat requires explicit discard selection
        8879319235128030159,  # stale target/reference path
        7279401347159399121,  # copied spell retains an originally chosen target
        9880129530406887857,  # optional triggered effect choice
    ),
)
def test_700_diagnostic_technical_failure_seed_completes_with_fresh_replay(seed: int) -> None:
    execution = run_phase_c_game_execution(
        seed=seed,
        mode="STANDARD",
        through_turn=10,
        validate_fresh_replay=True,
        policy_actions=True,
    )

    assert execution.technical_game.controlled_turns_completed == 10
    assert execution.technical_game.fresh_replay_state_hash == execution.technical_game.final_state_hash
