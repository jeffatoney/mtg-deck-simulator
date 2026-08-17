from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[2]
SLOW_PROBE = ROOT / "tests/000_stage3_probe/test_stage3_probe.py"


def _load_probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location("stage3_repaired_witness", SLOW_PROBE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_repaired_391_production_witness_probe() -> None:
    probe = _load_probe()
    state, seed_text, snapshot = probe._capture_first_access(
        "repaired-391",
        391730338978874520,
        legacy=False,
    )
    executor, steps = probe.contract._produce_witness(state, seed_text)
    probe.contract._assert_replays(state, seed_text, executor)
    payload = {
        "schema_version": "pr100-stage3-repaired391-witness-v1",
        "source_private_state_hash": probe.state_hash(state),
        "tracker_snapshot": snapshot,
        "terminal_status": executor.state.terminal.status,
        "winner_ids": list(executor.state.terminal.winners),
        "loser_ids": list(executor.state.terminal.losers),
        "final_private_state_hash": probe.state_hash(executor.state),
        "same_process_replay": True,
        "fresh_replay": True,
        "action_count": len(steps),
        "glint_horn_activation_count": sum(
            step["kind"] == "ACTIVATE"
            and step["identity"] == probe.GLINT
            for step in steps
        ),
        "treasure_activation_count": sum(
            step["kind"] == "ACTIVATE"
            and step["identity"] == "Treasure"
            for step in steps
        ),
        "steps": steps,
    }
    pytest.exit(
        "STAGE3_REPAIRED391_WITNESS="
        + json.dumps(payload, sort_keys=True, separators=(",", ":")),
        returncode=1,
    )
