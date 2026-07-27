#!/usr/bin/env python3
"""Validate a referee-owned call trace correlated with a raw game transcript."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED = {
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


def validate(data: dict) -> list[str]:
    errors: list[str] = []
    if any(
        key in data
        for key in (
            "referee_observations",
            "satisfied_acceptance_ids",
            "postconditions",
            "trace_invariants",
        )
    ):
        errors.append("candidate-controlled verdict or referee observation field")
    calls = data.get("_referee_calls", [])
    events = data.get("events", [])
    receipts = data.get("receipts", [])
    run = [
        c
        for c in calls
        if c.get("module") == "mtg_kernel.executor"
        and str(c.get("qualname", "")).endswith("GameExecutor.run")
    ]
    if not run:
        return [*errors, "no referee-observed GameExecutor.run call"]
    start = min(c["order"] for c in run if c["kind"] == "call")
    end = max(c["order"] for c in run if c["kind"] in {"return", "exception"})
    beneath = [c for c in calls if start < c["order"] < end and c.get("kind") == "call"]
    services = {str(c.get("qualname", "")).split(".")[0] for c in beneath}
    if missing := REQUIRED - services:
        errors.append(f"services not observed beneath executor: {sorted(missing)}")
    transitions = {
        (e.get("parent_action_id"), e.get("pre_state_hash"), e.get("post_state_hash"))
        for e in events
    }
    for receipt in receipts:
        triple = (
            receipt.get("action_id"),
            receipt.get("pre_state_hash"),
            receipt.get("post_state_hash"),
        )
        correlated_call = any(
            c.get("action_id") == receipt.get("action_id")
            and str(c.get("qualname", "")).startswith(str(receipt.get("service")) + ".")
            for c in beneath
        )
        if triple not in transitions or not correlated_call:
            errors.append(f"uncorrelated receipt: {receipt.get('service')}")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_kernel_liveness.py REFEREE_TRACE.json")
        return 2
    errors = validate(json.loads(Path(sys.argv[1]).read_text()))
    print(f"Causal liveness: {'FAIL' if errors else 'PASS'}")
    for error in errors:
        print(f"- {error}")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
