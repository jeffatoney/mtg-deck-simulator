from __future__ import annotations

import json

import pytest

from .reference_adapter import ROOT, assert_causally_live, assert_predicates, run_scenario

SCENARIOS = json.loads((ROOT / "automation/reference-scenarios.json").read_text())["scenarios"]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item["scenario_id"])
def test_forced_scenario(scenario: dict[str, object]) -> None:
    result = run_scenario(scenario)
    assert_causally_live(result)
    oracle = scenario["referee_oracle"]
    assert_predicates(result, oracle["expected_state_transition_predicates"])
    assert_predicates(result, oracle["expected_final_state_predicates"])
