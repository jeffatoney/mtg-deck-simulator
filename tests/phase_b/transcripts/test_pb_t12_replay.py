from pathlib import Path

import pytest

from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import Zone
from mtg_kernel.replay import transcript
from mtg_measure import (
    CardMeasurement,
    ComboMeasurement,
    GameMeasurement,
    OpeningHandMeasurement,
    measurement_digest,
)
from mtg_runs import replay_in_fresh_process, verify_worker_invariance
from mtg_verify.transcript_evidence import audit_event, record_audit_evidence
from tests.phase_b.transcripts.support import funded_game

ROOT = Path(__file__).resolve().parents[3]


def test_pb_t12_replay_measurement_worker_evidence() -> None:
    state, executor, specs = funded_game("golden-t12", ("P0", "P1"))
    state.replay_initial_state = state.audit_dict()
    state.players["P1"].life = 1
    malcolm = add_card(executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD)
    state.replay_initial_state = state.audit_dict()
    executor.deal_damage_to_player(malcolm.object_id, "P1", 1, combat=True)
    assert state.terminal.status == "TERMINAL"
    event_count = len(state.events)
    with pytest.raises(IllegalAction, match="game is terminal") as terminal_error:
        executor.pass_priority("P0")
    assert len(state.events) == event_count
    replay = replay_in_fresh_process(transcript(state, seed="golden-t12"), cwd=ROOT)
    original_hash = state_hash(state)
    assert replay.state_hash == original_hash
    measurement = GameMeasurement(
        schema_version="phase-b-game-measurement-v1",
        game_index=1,
        seed=11,
        mode="AUDIT_ONLY",
        policy_config_id="anchor_balanced",
        opening_hands=(OpeningHandMeasurement(1, 7, ("Island",) * 7, True),),
        kept_at=7,
        checkpoint_table_win_access={5: False, 6: False, 8: False, 10: True},
        failure_labels={5: ("mana_shortage",), 6: (), 8: (), 10: ()},
        primary_failure={5: "mana_shortage", 6: None, 8: None, 10: None},
        combo_records=(
            ComboMeasurement(
                "malcolm_glint_horn", 10, True, True, False, False, True, True, True, False
            ),
        ),
        earliest_legal_attempt_turn=10,
        actual_first_attempt_turn=10,
        attempt_package="malcolm_glint_horn",
        attempt_timing="IMMEDIATE",
        usable_protection_count=0,
        protection_in_hand_not_payable=False,
        protection_category_mismatch=False,
        independent_second_line_available=False,
        card_records=(CardMeasurement("Malcolm, Keen-Eyed Navigator", drawn=0, cast=1),),
        terminal_status="WIN",
        terminal_turn=10,
    )
    digest = measurement_digest((measurement,))
    assert measurement_digest((measurement,)) == digest
    raw = ({"game_index": 1, "seed": 11, "measurement_sha256": digest},)
    workers_a = verify_worker_invariance({1: raw, 4: tuple(reversed(raw))})
    workers_b = verify_worker_invariance({2: raw})
    assert workers_a == workers_b
    damage_event = next(event for event in state.events if event.kind == "DAMAGE_DEALT")
    terminal_event = next(event for event in state.events if event.kind == "GAME_TERMINATED")
    record_audit_evidence(
        "PB-T12-replay-invariance",
        (
            audit_event("DAMAGE_DEALT", event_id=damage_event.event_id),
            audit_event("GAME_TERMINATED", event_id=terminal_event.event_id),
            audit_event("POST_TERMINAL_ACTION_REJECTED", reason=str(terminal_error.value)),
            audit_event(
                "REPLAY_STATE_HASH_VALIDATED",
                original=original_hash,
                replayed=replay.state_hash,
            ),
            audit_event("MEASUREMENT_DIGEST_VALIDATED", sha256=digest),
            audit_event("WORKER_INVARIANCE_VALIDATED", canonical_digest=workers_a),
        ),
        facts={"thread_safety_claimed": False, "worker_configurations": [1, 2, 4]},
    )
