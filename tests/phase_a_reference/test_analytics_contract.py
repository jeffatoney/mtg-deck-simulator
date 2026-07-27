from __future__ import annotations
from .reference_adapter import run_scenario


def test_simulation_analytics_contract() -> None:
    result = run_scenario({"scenario_id": "sol-ring", "scenario_version": 1})
    assert {
        "events",
        "actions",
        "decisions",
        "card_instances",
        "receipts",
        "replay",
        "run_manifest",
    } <= result.keys()
    assert all(event.get("schema_version") == 1 for event in result["events"])
    assert all(decision.get("future_information_used") is False for decision in result["decisions"])
    forbidden = {
        "combo_access",
        "protection_access",
        "second_line_access",
        "strandedness",
        "strategic_optimality",
    }
    assert not any(forbidden & event.keys() for event in result["events"])
