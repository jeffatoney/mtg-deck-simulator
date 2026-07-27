from __future__ import annotations

import json

import pytest

from .reference_adapter import (
    ROOT,
    assert_causally_live,
    assert_trace_invariants,
    load_scenario,
    run_scenario,
    validate_raw_artifact,
)

SEEDS = json.loads((ROOT / "automation/trace-invariants.json").read_text())["seed_schedule"]


@pytest.mark.parametrize("seed", SEEDS)
def test_random_trace_invariants(seed: int) -> None:
    scenario = load_scenario("random-trace")
    scenario["candidate_input"]["rng_streams"] = {"game": seed, "policy": seed ^ 0x5A5A}
    scenario["scenario_id"] = f"random-trace-{seed}"
    scenario["candidate_input"]["initial_state"]["game_id"] = scenario["scenario_id"]
    result = run_scenario(scenario)
    validate_raw_artifact(result, scenario)
    assert_causally_live(result)
    assert_trace_invariants(result)
    assert result["run_manifest"]["game_id"] == f"random-trace-{seed}"
    assert result["rng_streams"] == scenario["candidate_input"]["rng_streams"]
