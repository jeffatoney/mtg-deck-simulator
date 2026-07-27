#!/usr/bin/env python3
"""Validate a referee-owned call trace correlated with a raw game transcript."""

from __future__ import annotations

import json
import sys
from pathlib import Path


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
    contracts = data.get("_referee_call_contract", [])
    for contract in contracts:
        canonical = [
            call
            for call in beneath
            if call.get("module") == contract.get("module")
            and call.get("qualname") == contract.get("qualname")
        ]
        if not canonical:
            errors.append(
                "canonical call not observed beneath executor: "
                f"{contract.get('module')}.{contract.get('qualname')}"
            )
        event_type = contract.get("causal_event_type")
        if event_type and not any(event.get("event_type") == event_type for event in events):
            errors.append(f"canonical call lacks causal transition: {event_type}")
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
            and any(
                c.get("module") == contract.get("module")
                and c.get("qualname") == contract.get("qualname")
                for contract in contracts
            )
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
