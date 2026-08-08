#!/usr/bin/env python3
"""Build the cross-lane interaction coverage summary for the frozen exact deck."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.audit_policy_choice_replay_conformance import audit_conformance
    from scripts.build_interaction_coverage_manifest import build_manifest
except ModuleNotFoundError:
    from audit_policy_choice_replay_conformance import audit_conformance  # type: ignore[no-redef]
    from build_interaction_coverage_manifest import build_manifest  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "automation/strategic-choice-conformance.json"
LEDGER_PATH = ROOT / "automation/interaction-integration-coverage.json"
_NON_STRATEGIC_POLICY_CLASSES = {"NONE", "MANDATORY_DETERMINISTIC"}


def _route_matches(choice: dict[str, Any], route: dict[str, Any]) -> bool:
    if str(route.get("timing", "")) != str(choice.get("timing", "")):
        return False
    purpose = str(choice.get("purpose", ""))
    route_purpose = str(route.get("purpose", ""))
    if route_purpose.endswith("*"):
        if not purpose.startswith(route_purpose[:-1]):
            return False
    elif route_purpose != purpose:
        return False
    policy_class = route.get("policy_class")
    return policy_class in {None, "*", str(choice.get("policy_class", ""))}


def _pattern_matches(pattern: str, supported: str) -> bool:
    if supported.endswith("*"):
        prefix = supported[:-1]
        if pattern.endswith("*"):
            return pattern[:-1].startswith(prefix) or prefix.startswith(pattern[:-1])
        return pattern.startswith(prefix)
    if pattern.endswith("*"):
        return False
    return pattern == supported


def _is_strategic(choice: dict[str, Any]) -> bool:
    return str(choice.get("policy_class", "")) not in _NON_STRATEGIC_POLICY_CLASSES


def _current_route_support(
    record: dict[str, Any],
    route: dict[str, Any],
    audit: dict[str, Any],
) -> tuple[bool, str | None]:
    runtime_purpose = route.get("runtime_purpose")
    if runtime_purpose:
        supported_patterns = tuple(str(value) for value in audit["production_policy_patterns"])
        if not any(
            _pattern_matches(str(runtime_purpose), supported) for supported in supported_patterns
        ):
            return False, f"runtime purpose unsupported: {runtime_purpose}"

    if route.get("mechanism") == "PROTOCOL_METHOD":
        method = str(route.get("protocol_method", ""))
        if method not in audit["production_policy_methods"]:
            return False, f"production protocol method missing: {method}"
        if method not in audit["recorded_replay_methods"]:
            return False, f"recorded replay protocol method missing: {method}"

    if route.get("timing") == "TRIGGER_STACKING" and route.get("purpose") == "TARGET_SELECTION":
        effect = record.get("effect", {})
        effect_kind = str(effect.get("kind", "")) if isinstance(effect, dict) else ""
        if effect_kind and effect_kind not in audit["trigger_policy_effects"]:
            return False, f"trigger target effect unsupported: {effect_kind}"

    return True, None


def build_integration_coverage() -> dict[str, Any]:
    manifest = build_manifest()
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    audit = audit_conformance()
    routes = [item for item in registry.get("canonical_routes", []) if isinstance(item, dict)]

    strategic_record_count = 0
    strategic_choice_occurrence_count = 0
    reviewed_route_occurrence_count = 0
    currently_supported_occurrence_count = 0
    route_complete_record_count = 0
    current_support_complete_record_count = 0
    record_route_gaps: list[dict[str, Any]] = []

    records = [item for item in manifest.get("records", []) if isinstance(item, dict)]
    for record in records:
        choices = [
            choice
            for choice in record.get("choices", [])
            if isinstance(choice, dict) and _is_strategic(choice)
        ]
        if not choices:
            continue
        strategic_record_count += 1
        strategic_choice_occurrence_count += len(choices)
        route_complete = True
        current_complete = True
        gaps: list[dict[str, str]] = []

        for choice in choices:
            route = next((item for item in routes if _route_matches(choice, item)), None)
            if route is None:
                route_complete = False
                current_complete = False
                gaps.append(
                    {
                        "timing": str(choice.get("timing", "")),
                        "purpose": str(choice.get("purpose", "")),
                        "policy_class": str(choice.get("policy_class", "")),
                        "reason": "no reviewed policy/replay route",
                    }
                )
                continue

            reviewed_route_occurrence_count += 1
            supported, reason = _current_route_support(record, route, audit)
            if supported:
                currently_supported_occurrence_count += 1
            else:
                current_complete = False
                gaps.append(
                    {
                        "timing": str(choice.get("timing", "")),
                        "purpose": str(choice.get("purpose", "")),
                        "policy_class": str(choice.get("policy_class", "")),
                        "reason": str(reason),
                    }
                )

        if route_complete:
            route_complete_record_count += 1
        if current_complete:
            current_support_complete_record_count += 1
        if gaps:
            record_route_gaps.append(
                {
                    "record_id": str(record.get("record_id", "")),
                    "gaps": gaps,
                }
            )

    total_records = int(manifest["record_count"])
    no_strategic_policy_required = total_records - strategic_record_count
    policy_ready_or_not_required = (
        no_strategic_policy_required + current_support_complete_record_count
    )

    engine_evidence = sum(
        bool(record.get("implementation", {}).get("engine_handler")) for record in records
    )
    policy_evidence = sum(
        bool(record.get("implementation", {}).get("policy_handler")) for record in records
    )
    replay_evidence = sum(
        bool(record.get("implementation", {}).get("replay_handler")) for record in records
    )
    direct_test_evidence = sum(
        bool(record.get("evidence", {}).get("positive_tests")) for record in records
    )
    proven_records = sum(record.get("status") == "PROVEN" for record in records)

    return {
        "schema_version": "interaction-integration-derived-v1",
        "status": "PASS" if proven_records == total_records else "BLOCKED_NOT_PROVEN",
        "surface": {
            "record_count": total_records,
            "card_composition_record_count": int(manifest["card_composition_record_count"]),
            "card_effect_record_count": int(manifest["card_effect_record_count"]),
            "global_rule_record_count": int(manifest["global_rule_record_count"]),
            "manifest_sha256": str(manifest["manifest_sha256"]),
        },
        "record_level_evidence": {
            "engine_handler_attached": engine_evidence,
            "policy_handler_attached": policy_evidence,
            "replay_handler_attached": replay_evidence,
            "positive_test_evidence_attached": direct_test_evidence,
            "proven_records": proven_records,
        },
        "strategic_policy_replay": {
            "records_requiring_strategic_policy": strategic_record_count,
            "records_requiring_no_strategic_policy": no_strategic_policy_required,
            "strategic_choice_occurrences": strategic_choice_occurrence_count,
            "reviewed_route_occurrences": reviewed_route_occurrence_count,
            "currently_supported_occurrences": currently_supported_occurrence_count,
            "route_complete_records": route_complete_record_count,
            "current_support_complete_records": current_support_complete_record_count,
            "policy_ready_or_not_required_records": policy_ready_or_not_required,
            "records_with_policy_replay_gaps": total_records - policy_ready_or_not_required,
            "unique_strategic_choice_classes": int(audit["strategic_surface_choice_count"]),
            "unrouted_strategic_choice_classes": len(audit["unrouted_surface_choices"]),
            "protocol_methods_required": len(audit["protocol_methods"]),
            "protocol_methods_in_production_provider": len(
                set(audit["protocol_methods"]) & set(audit["production_policy_methods"])
            ),
            "protocol_methods_in_recorded_replay_provider": len(
                set(audit["protocol_methods"]) & set(audit["recorded_replay_methods"])
            ),
            "missing_trigger_policy_effects": list(audit["missing_trigger_policy_effects"]),
            "audit_violation_messages": len(audit["violations"]),
        },
        "record_route_gaps": record_route_gaps,
    }


def _check_ledger(report: dict[str, Any]) -> bool:
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    expected = {
        "requirements": report["surface"]["record_count"],
        "inventory_mapped": report["surface"]["record_count"],
        "record_level_proven": report["record_level_evidence"]["proven_records"],
        "record_level_engine_evidence_attached": report["record_level_evidence"][
            "engine_handler_attached"
        ],
        "record_level_policy_evidence_attached": report["record_level_evidence"][
            "policy_handler_attached"
        ],
        "record_level_replay_evidence_attached": report["record_level_evidence"][
            "replay_handler_attached"
        ],
        "record_level_direct_test_evidence_attached": report["record_level_evidence"][
            "positive_test_evidence_attached"
        ],
        "records_requiring_strategic_policy": report["strategic_policy_replay"][
            "records_requiring_strategic_policy"
        ],
        "policy_ready_or_not_required_records": report["strategic_policy_replay"][
            "policy_ready_or_not_required_records"
        ],
        "records_with_policy_replay_gaps": report["strategic_policy_replay"][
            "records_with_policy_replay_gaps"
        ],
        "strategic_choice_occurrences": report["strategic_policy_replay"][
            "strategic_choice_occurrences"
        ],
        "reviewed_route_occurrences": report["strategic_policy_replay"][
            "reviewed_route_occurrences"
        ],
        "currently_supported_occurrences": report["strategic_policy_replay"][
            "currently_supported_occurrences"
        ],
        "strategic_choice_classes_required": report["strategic_policy_replay"][
            "unique_strategic_choice_classes"
        ],
        "strategic_choice_classes_unrouted": report["strategic_policy_replay"][
            "unrouted_strategic_choice_classes"
        ],
    }
    actual = ledger.get("coverage", {})
    mismatches = {
        key: {"expected": value, "actual": actual.get(key)}
        for key, value in expected.items()
        if actual.get(key) != value
    }
    if mismatches:
        print(json.dumps({"status": "FAIL", "mismatches": mismatches}, indent=2, sort_keys=True))
        return False
    print(json.dumps({"status": "PASS", "checked": expected}, indent=2, sort_keys=True))
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-ledger", action="store_true")
    args = parser.parse_args()

    report = build_integration_coverage()
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    if args.check_ledger and not _check_ledger(report):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
