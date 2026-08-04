"""Fresh-process replay and worker invariance tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from mtg_kernel.factory import new_game
from mtg_kernel.replay import transcript
from mtg_runs import replay_in_fresh_process, verify_worker_invariance

ROOT = Path(__file__).resolve().parents[2]


def test_replay_runs_in_a_fresh_process_without_policy_decision_code() -> None:
    state, executor = new_game(("P0", "P1"))
    state.replay_initial_state = state.audit_dict()
    executor.pass_priority("P0")
    replay = replay_in_fresh_process(transcript(state), cwd=ROOT)
    assert len(replay.state_hash) == 64
    assert len(replay.transcript_sha256) == 64


def test_worker_count_does_not_change_canonical_raw_records() -> None:
    records = ({"game_index": 1, "seed": 11}, {"game_index": 2, "seed": 12})
    assert len(verify_worker_invariance({1: records, 4: tuple(reversed(records))})) == 64
    with pytest.raises(ValueError, match="diverge"):
        verify_worker_invariance({1: records, 2: ({"game_index": 1, "seed": 99},)})
