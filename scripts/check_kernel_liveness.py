#!/usr/bin/env python3
"""Frozen causal-attestation contract checker for Phase A game traces."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_SERVICES = {
    "ActionGenerator",
    "ActionValidator",
    "CostService",
    "StackService",
    "PriorityEngine",
    "ResolutionEngine",
    "ZoneService",
    "StateBasedActions",
    "TriggerEngine",
    "TurnEngine",
    "ExternalZoneLedger",
    "ReplayEngine",
}
RECEIPT_FIELDS = {
    "run_id",
    "game_id",
    "action_id",
    "service",
    "operation",
    "pre_state_hash",
    "post_state_hash",
    "causal_event_ids",
}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_kernel_liveness.py TRACE.json")
        return 2
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    receipts = data.get("receipts", [])
    missing_fields = [
        index for index, item in enumerate(receipts) if not RECEIPT_FIELDS <= item.keys()
    ]
    services = {item.get("service") for item in receipts}
    independent = data.get("referee_observations", {})
    ok = (
        not missing_fields
        and REQUIRED_SERVICES <= services
        and all(
            independent.get(key)
            for key in ("call_trees", "state_transitions", "receipt_correlations")
        )
    )
    print(f"Causal liveness: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
