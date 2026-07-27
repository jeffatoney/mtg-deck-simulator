from __future__ import annotations
import json
from pathlib import Path
import pytest
from .reference_adapter import assert_causally_live, run_scenario

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = json.loads((ROOT / "automation/reference-scenarios.json").read_text())[
    "forced_scenarios"
]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item["scenario_id"])
def test_forced_scenario(scenario: dict[str, object]) -> None:
    result = run_scenario(scenario)
    assert_causally_live(result)
    assert all(
        result.get("postconditions", {}).get(name) is value
        for name, value in scenario["expected_postconditions"].items()
    )
