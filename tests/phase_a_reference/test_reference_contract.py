from __future__ import annotations

import json

import pytest

from .reference_adapter import ROOT, assert_acceptance, load_scenario, run_scenario

MANIFEST = json.loads((ROOT / "automation/phase-a-reference-manifest.json").read_text())


@pytest.mark.parametrize("mapping", MANIFEST["mappings"], ids=lambda item: item["acceptance_id"])
def test_acceptance_contract(mapping: dict[str, object]) -> None:
    scenario = load_scenario(str(mapping["scenario_id"]))
    result = run_scenario(scenario)
    assert_acceptance(result, mapping, scenario)
