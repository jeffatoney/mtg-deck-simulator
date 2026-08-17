from __future__ import annotations

import json

import pytest

from mtg_kernel.hashing import state_hash
from mtg_kernel.replay import transcript, validate_replay
from mtg_runs.replay_audit import replay_in_fresh_process
from tests.phase_c import test_malcolm_glint_horn_witness_contract as contract


def test_stage3_witness_extract() -> None:
    result = {}
    for label, seed, legacy in (
        ("repaired-391", 391730338978874520, False),
        ("legacy-391", 391730338978874520, True),
        ("legacy-101", 101, True),
    ):
        patch = pytest.MonkeyPatch()
        state, seed_text, snapshot = contract._capture_first_access(
            patch,
            label=label,
            seed=seed,
            legacy=legacy,
        )
        witness, steps = contract._produce_witness(state, seed_text)
        body = transcript(witness.state, seed=seed_text)
        same_process = validate_replay(body)
        fresh = replay_in_fresh_process(body, cwd=contract.ROOT)
        result[label] = {
            "first_state_hash": state_hash(state),
            "tracker_snapshot": snapshot,
            "terminal_status": witness.state.terminal.status,
            "winners": list(witness.state.terminal.winners),
            "losers": list(witness.state.terminal.losers),
            "final_state_hash": state_hash(witness.state),
            "same_process_replay_hash": state_hash(same_process),
            "fresh_replay_hash": fresh.state_hash,
            "step_count": len(steps),
            "steps": steps,
        }
    pytest.exit(
        "STAGE3_WITNESS_EXTRACT="
        + json.dumps(result, sort_keys=True, separators=(",", ":")),
        returncode=1,
    )
