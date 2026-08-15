from __future__ import annotations

import pytest

from mtg_runs.phase_c_exploratory_v2 import run_exploratory_v2_game_execution
from mtg_search.directed_v2 import ARM_IDS


@pytest.mark.parametrize("arm_id", sorted(ARM_IDS))
def test_v2_one_turn_clean_engine_smoke_replays_and_persists_evidence(arm_id: str) -> None:
    execution = run_exploratory_v2_game_execution(
        seed=810001,
        arm_id=arm_id,
        exploration_seed=910001,
        game_index=1,
        through_turn=1,
        validate_fresh_replay=False,
    )
    game = execution.technical_game
    assert game.artifact_classification == "NON_AUTHORIZED_DIAGNOSTIC"
    assert game.pilot_result is False
    assert game.authorized_pilot_result is False
    assert game.final_state_hash == game.fresh_replay_state_hash
    assert game.baseline_candidate_retained == game.baseline_candidate_required
    assert game.candidate_score_vectors_persisted == game.candidate_score_vectors_required
    assert game.land_guardrail_compliant == game.land_guardrail_applicable
    assert game.decision_evidence_sha256
