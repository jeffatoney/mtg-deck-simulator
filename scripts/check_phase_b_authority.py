#!/usr/bin/env python3
"""Validate the active Phase B authority map and execution locks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "automation/phase-b-authority-map.json"


def _strings(value: object, field: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{field} must be a list of strings")
        return []
    return list(value)


def main() -> int:
    errors: list[str] = []
    try:
        data: dict[str, Any] = json.loads(MAP.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Phase B authority check failed: {exc}")
        return 1
    if data.get("schema_version") != "phase-b-authority-v1" or data.get("phase") != "B":
        errors.append("unexpected Phase B authority schema or phase")
    if data.get("only_acceptance_evidence_label") != "CLEAN_ENGINE_PRODUCTION_PATH":
        errors.append("Phase B acceptance evidence label is not clean production path")
    active = _strings(data.get("active_binding"), "active_binding", errors)
    decisions = _strings(data.get("architecture_decisions"), "architecture_decisions", errors)
    standing_gates = _strings(data.get("standing_gates"), "standing_gates", errors)
    archival = _strings(data.get("archival_reference_only"), "archival_reference_only", errors)
    forbidden = _strings(data.get("forbidden_active_paths"), "forbidden_active_paths", errors)
    locked = _strings(data.get("locked_commands"), "locked_commands", errors)
    blockers = _strings(data.get("blocking_requirement_ids"), "blocking_requirement_ids", errors)
    for relative in active + decisions + standing_gates:
        if not (ROOT / relative).is_file():
            errors.append(f"missing active Phase B authority file: {relative}")
    if set(standing_gates) != {"scripts/check_policy_information_boundary.py"}:
        errors.append("Phase B standing policy-information gate is missing or changed")
    for relative in forbidden:
        if (ROOT / relative).exists():
            errors.append(f"forbidden active path exists: {relative}")
    if set(active).intersection(archival):
        errors.append("Phase B paths are classified as both active and archival")
    expected_locked = {
        "4800 evaluator discovery comparisons",
        "1000 evaluator validation examples",
        "500 standard pilot games",
        "200 exploratory pilot games",
        "20000 standard study games",
        "5000 exploratory study games",
    }
    if set(locked) != expected_locked:
        errors.append("pilot/full-study command locks drifted")
    expected_blockers = {
        "B-SOURCE-001",
        "B-COVERAGE-001",
        "B-DECK-001",
        "B-RULES-001",
        "B-LEGALITY-001",
        "B-HIDDEN-001",
        "B-OPPONENT-001",
        "B-POLICY-001",
        "B-EVALUATOR-001",
        "B-COMBO-001",
        "B-SEARCH-001",
        "B-MEASURE-001",
        "B-REPLAY-001",
        "B-MANIFEST-001",
        "B-TRANSCRIPT-001",
        "B-PHASE-A-001",
        "B-PILOT-LOCK-001",
    }
    if set(blockers) != expected_blockers:
        errors.append("blocking Phase B requirement set is incomplete or changed")
    if errors:
        print("Phase B authority check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "schema_version": data["schema_version"],
                "active_binding_count": len(active),
                "architecture_decision_count": len(decisions),
                "standing_gate_count": len(standing_gates),
                "blocking_requirement_count": len(blockers),
                "pilot_and_study_locked": True,
                "acceptance_evidence_label": data["only_acceptance_evidence_label"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
