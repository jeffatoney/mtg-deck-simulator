from __future__ import annotations
import json
from pathlib import Path
import pytest
from .reference_adapter import run_scenario

ROOT = Path(__file__).resolve().parents[2]
INVARIANTS = json.loads((ROOT / "automation/trace-invariants.json").read_text())["invariants"]


@pytest.mark.parametrize("seed", range(200))
def test_random_trace_invariants(seed: int) -> None:
    result = run_scenario({"scenario_id": "random-trace", "scenario_version": 1, "seed": seed})
    checks = result.get("trace_invariants", {})
    assert set(INVARIANTS) <= checks.keys()
    assert all(checks[name] is True for name in INVARIANTS)
