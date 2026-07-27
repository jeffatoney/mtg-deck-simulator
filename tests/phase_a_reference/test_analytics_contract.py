from __future__ import annotations

from .reference_adapter import _validate_analytics, load_scenario, run_scenario


def test_simulation_analytics_contract() -> None:
    result = run_scenario(load_scenario("sol-ring"))
    _validate_analytics(result)
