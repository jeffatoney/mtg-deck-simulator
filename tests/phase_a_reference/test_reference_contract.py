from __future__ import annotations

import json
from pathlib import Path

import pytest

from .reference_adapter import assert_causally_live, run_scenario

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((ROOT / "automation/phase-a-reference-manifest.json").read_text())
SCENARIOS = {
    item["scenario_id"]: item
    for item in json.loads((ROOT / "automation/reference-scenarios.json").read_text())[
        "forced_scenarios"
    ]
}


@pytest.mark.parametrize("mapping", MANIFEST["mappings"], ids=lambda item: item["acceptance_id"])
def test_acceptance_contract(mapping: dict[str, object]) -> None:
    result = run_scenario(SCENARIOS[str(mapping["scenario_id"])])
    assert_causally_live(result)
    observed = set(result.get("satisfied_acceptance_ids", []))
    assert mapping["acceptance_id"] in observed
    assert result.get("production_entrypoint") == mapping["required_production_entrypoint"]
