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
    run_call = min((c for c in run if c["kind"] == "call"), key=lambda c: c["order"])
    run_call_id = run_call.get("call_id")
    by_call_id = {c.get("call_id"): c for c in calls if c.get("kind") == "call"}

    def descends_from_run(call: dict) -> bool:
        parent = call.get("parent_call_id")
        seen: set[object] = set()
        while parent is not None and parent not in seen:
            if parent == run_call_id:
                return True
            seen.add(parent)
            parent = by_call_id.get(parent, {}).get("parent_call_id")
        return False

    beneath = [c for c in calls if c.get("kind") == "call" and descends_from_run(c)]
    contracts = data.get("_referee_call_contract", [])
    for contract in contracts:
        canonical = [
            call
            for call in beneath
            if call.get("module") == contract.get("module")
            and call.get("qualname") == contract.get("qualname")
        ]
        operation = contract.get("operation")
        if operation and not str(contract.get("qualname", "")).endswith(f".{operation}"):
            errors.append(f"call contract operation mismatch: {operation}")
        if not canonical:
            errors.append(
                "canonical call not observed beneath executor: "
                f"{contract.get('module')}.{contract.get('qualname')}"
            )
        event_type = contract.get("causal_event_type")
        causal_events = [event for event in events if event.get("event_type") == event_type]
        correlated = [
            (call, event)
            for call in canonical
            for event in causal_events
            if call.get("game_id") == event.get("game_id")
            and call.get("action_id") == event.get("parent_action_id")
            and event.get("pre_state_hash") != event.get("post_state_hash")
        ]
        if event_type and not correlated:
            errors.append(f"canonical call lacks causal transition: {event_type}")
        for call, event in correlated:
            matching_receipt = any(
                receipt.get("operation") == operation
                and receipt.get("game_id") == call.get("game_id")
                and receipt.get("action_id") == call.get("action_id")
                and event.get("event_id") in receipt.get("causal_event_ids", [])
                and receipt.get("pre_state_hash") == event.get("pre_state_hash")
                and receipt.get("post_state_hash") == event.get("post_state_hash")
                for receipt in receipts
            )
            if not matching_receipt:
                errors.append(f"canonical call lacks exact receipt/event correlation: {event_type}")
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
            and c.get("game_id") == receipt.get("game_id")
            and any(
                c.get("module") == contract.get("module")
                and c.get("qualname") == contract.get("qualname")
                and receipt.get("operation") == contract.get("operation")
                for contract in contracts
            )
            for c in beneath
        )
        causal_events = {
            event.get("event_id")
            for event in events
            if event.get("parent_action_id") == receipt.get("action_id")
        }
        causal_ids = set(receipt.get("causal_event_ids", []))
        if triple not in transitions or not correlated_call or not causal_ids <= causal_events:
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
