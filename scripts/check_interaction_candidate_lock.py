#!/usr/bin/env python3
"""Validate the provisional or reviewed interaction-surface lock explicitly."""

from __future__ import annotations

import json
from pathlib import Path

try:
    from scripts.build_interaction_coverage_manifest import build_manifest
except ModuleNotFoundError:
    from build_interaction_coverage_manifest import build_manifest  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "automation/interaction-coverage-lock.json"
ZERO_DIGEST = "sha256:" + ("0" * 64)


def validate_lock() -> dict[str, object]:
    manifest = build_manifest()
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    status = str(lock.get("status", ""))

    expected_counts = {
        "record_count": int(manifest["record_count"]),
        "card_composition_record_count": int(manifest["card_composition_record_count"]),
        "card_effect_record_count": int(manifest["card_effect_record_count"]),
        "global_rule_record_count": int(manifest["global_rule_record_count"]),
        "physical_card_count": int(manifest["physical_card_count"]),
        "card_definition_count": int(manifest["card_definition_count"]),
    }
    mismatches: dict[str, dict[str, object]] = {
        key: {"expected": value, "actual": lock.get(key)}
        for key, value in expected_counts.items()
        if lock.get(key) != value
    }

    manifest_digest = str(manifest["manifest_sha256"])
    if status == "PROVISIONAL_PENDING_AGENT_A_INTEGRATION":
        expected_fields = {
            "candidate_manifest_sha256": manifest_digest,
            "manifest_sha256": ZERO_DIGEST,
        }
    elif status == "FROZEN_REVIEWED":
        expected_fields = {
            "candidate_manifest_sha256": manifest_digest,
            "manifest_sha256": manifest_digest,
        }
    else:
        expected_fields = {}
        mismatches["status"] = {
            "expected": [
                "PROVISIONAL_PENDING_AGENT_A_INTEGRATION",
                "FROZEN_REVIEWED",
            ],
            "actual": status,
        }

    for key, value in expected_fields.items():
        if lock.get(key) != value:
            mismatches[key] = {"expected": value, "actual": lock.get(key)}

    return {
        "status": "FAIL" if mismatches else "PASS",
        "lock_status": status,
        "candidate_manifest_sha256": manifest_digest,
        "record_count": int(manifest["record_count"]),
        "mismatches": mismatches,
    }


def main() -> int:
    result = validate_lock()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
