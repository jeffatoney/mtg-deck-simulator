#!/usr/bin/env python3
"""Execute the protected Phase A semantic near-miss matrix.

This setup-time harness exercises the data-driven assertion plan for every
acceptance clause without importing a candidate kernel.  The future isolated
suite additionally evaluates real candidate transcripts through the same plans.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _adapter():
    path = ROOT / "tests/phase_a_acceptance/reference_adapter.py"
    spec = importlib.util.spec_from_file_location("phase_a_reference_adapter", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _baseline(plan: dict[str, Any]) -> dict[str, Any]:
    object_id = "protected:object:1"
    events = []
    for sequence, event_type in enumerate(plan["ordered_event_types"], 1):
        events.append(
            {
                "sequence": sequence,
                "event_type": event_type,
                "source_object_ids": [object_id],
                "target_object_ids": [],
                "pre_state_hash": f"state:{sequence - 1}",
                "post_state_hash": f"state:{sequence}",
            }
        )
    return {
        "events": events,
        "objects": [{"object_id": object_id}],
        "card_instances": [],
    }


def mutate_reverse_required_event_order(artifact: dict[str, Any]) -> None:
    artifact["events"][0], artifact["events"][-1] = (
        artifact["events"][-1],
        artifact["events"][0],
    )


def mutate_erase_required_state_transition(artifact: dict[str, Any]) -> None:
    artifact["events"][0]["post_state_hash"] = artifact["events"][0]["pre_state_hash"]


def mutate_replace_registered_object_reference(artifact: dict[str, Any]) -> None:
    artifact["events"][0]["source_object_ids"] = ["unregistered:object"]


MUTATIONS = {
    "reverse_required_event_order": mutate_reverse_required_event_order,
    "replace_registered_object_reference": mutate_replace_registered_object_reference,
    "erase_required_state_transition": mutate_erase_required_state_transition,
}


def execute(root: Path = ROOT) -> tuple[int, list[str]]:
    adapter = _adapter()
    scenarios = {
        item["referee_oracle"]["acceptance_requirement"]: item
        for item in json.loads((root / "automation/reference-scenarios.json").read_text())[
            "scenarios"
        ]
    }
    families = json.loads((root / "automation/phase-a-semantic-mutation-matrix.json").read_text())[
        "families"
    ]
    errors: list[str] = []
    executed = 0
    for family in families:
        acceptance_id = family["acceptance_id"]
        plan = scenarios[acceptance_id]["referee_oracle"]["semantic_assertion_plan"]
        baseline = _baseline(plan)
        try:
            adapter._assert_semantic_plan(baseline, plan)
        except AssertionError as exc:
            errors.append(f"{acceptance_id}: baseline failed: {exc}")
            continue
        for case in family["near_misses"]:
            mutation_id = case["mutation_function_id"]
            mutation = MUTATIONS.get(mutation_id)
            if mutation is None:
                errors.append(f"{acceptance_id}: unknown mutation {mutation_id}")
                continue
            near_miss = copy.deepcopy(baseline)
            mutation(near_miss)
            executed += 1
            try:
                adapter._assert_semantic_plan(near_miss, plan)
            except AssertionError:
                pass
            else:
                errors.append(f"{acceptance_id}: accepted {mutation_id}")
    return executed, errors


def main() -> int:
    executed, errors = execute()
    for error in errors:
        print(error)
    print(
        f"Phase A Semantic Mutation Matrix: {'FAIL' if errors else 'PASS'} ({executed} near misses)"
    )
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
