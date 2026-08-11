from __future__ import annotations

import pytest

from mtg_runs.phase_c_runner import run_phase_c_game_execution


@pytest.mark.parametrize(
    "seed",
    (
        15389282713444976856,  # counter-unless-pay self-interaction family
        12160543159459390667,  # Commit self-target commander replacement family
    ),
)
def test_no_opponent_policy_representative_seed_completes_with_fresh_replay(seed: int) -> None:
    execution = run_phase_c_game_execution(
        seed=seed,
        mode="STANDARD",
        through_turn=10,
        validate_fresh_replay=True,
        policy_actions=True,
    )

    assert execution.technical_game.controlled_turns_completed == 10
    assert (
        execution.technical_game.fresh_replay_state_hash
        == execution.technical_game.final_state_hash
    )
