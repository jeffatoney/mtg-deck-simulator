"""Frozen construction adapter for the public Phase A executor path.

This module deliberately imports candidate packages only inside call sites so the
protected suite can be collected before the candidate kernel exists.
"""

from __future__ import annotations

from typing import Any

ENTRYPOINT = "mtg_kernel.executor.GameExecutor.run"


def run_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    from mtg_kernel.executor import GameExecutor

    factory = getattr(GameExecutor, "from_reference_scenario", None)
    if not callable(factory):
        raise AssertionError(
            "GameExecutor.from_reference_scenario is required by the frozen adapter"
        )
    executor = factory(scenario)
    result = executor.run()
    if not isinstance(result, dict):
        raise AssertionError("GameExecutor.run must return the frozen evidence mapping")
    if result.get("scenario_id") != scenario["scenario_id"]:
        raise AssertionError("executor returned evidence for the wrong scenario")
    return result


def assert_causally_live(result: dict[str, Any]) -> None:
    services = {receipt.get("service") for receipt in result.get("receipts", [])}
    required = {
        "ActionGenerator",
        "ActionValidator",
        "CostService",
        "StackService",
        "PriorityEngine",
        "ResolutionEngine",
        "TargetValidator",
        "ZoneService",
        "StateBasedActions",
        "TriggerEngine",
        "TurnEngine",
        "ExternalZoneLedger",
        "ReplayEngine",
    }
    assert required <= services
    for receipt in result.get("receipts", []):
        assert {
            "run_id",
            "game_id",
            "action_id",
            "service",
            "operation",
            "pre_state_hash",
            "post_state_hash",
            "causal_event_ids",
        } <= receipt.keys()
