#!/usr/bin/env python3
"""Build the cross-lane interaction coverage summary for the exact deck."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

try:
    from scripts.audit_policy_choice_replay_conformance import audit_conformance
    from scripts.build_interaction_coverage_manifest import build_manifest
except ModuleNotFoundError:
    from audit_policy_choice_replay_conformance import audit_conformance  # type: ignore[no-redef]
    from build_interaction_coverage_manifest import build_manifest  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "automation/strategic-choice-conformance.json"
LEDGER_PATH = ROOT / "automation/interaction-integration-coverage.json"
AGENT_A_INVENTORY_DIR = ROOT / "automation/agent-a-deck-interaction-manifest"
AGENT_A_ADJUDICATION_PATH = ROOT / "automation/agent-a-findings-adjudication.json"
_NON_STRATEGIC_POLICY_CLASSES = {"NONE", "MANDATORY_DETERMINISTIC"}
_AGENT_A_COMPLETE_STATUSES = {
    "IMPLEMENTED_VERIFIED",
    "MAPPED_TO_EXISTING_VERIFIED_RECORD",
    "REJECTED_WITH_RULES_AUTHORITY",
}
_ENGINE_BLOCKERS = (
    "hybrid and exact/generic mana-payment configuration",
    "simultaneous same-controller trigger ordering",
    "optional-trigger decision timing",
    "general replacement-effect ordering",
    "cleanup re-entry discard selection",
    "legend-rule keep choice",
    "Commander hand/library replacement choice",
    "generic resolution-time scry choice ownership",
    "compound retarget metadata for copied Prismari Command spells",
    "global attack destinations beyond opponent players",
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _sha256_value(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


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


def _load_agent_a() -> dict[str, Any]:
    chunks = sorted(AGENT_A_INVENTORY_DIR.glob("part-*.b64"))
    if not chunks:
        raise ValueError("Agent A interaction inventory artifact chunks are missing")
    encoded = "".join(path.read_text(encoding="ascii").strip() for path in chunks)
    inventory = json.loads(gzip.decompress(base64.b64decode(encoded)).decode("utf-8"))
    adjudication = json.loads(AGENT_A_ADJUDICATION_PATH.read_text(encoding="utf-8"))

    if inventory.get("metadata", {}).get("schema_version") != (
        "agent-a-deck-interaction-inventory-v1"
    ):
        raise ValueError("unsupported Agent A interaction inventory schema")
    expected_digest = str(inventory.get("agent_a_manifest_sha256", ""))
    digest_input = dict(inventory)
    digest_input.pop("agent_a_manifest_sha256", None)
    actual_digest = _sha256_value(digest_input)
    if actual_digest != expected_digest:
        raise ValueError(
            f"Agent A interaction inventory digest mismatch: {actual_digest} != {expected_digest}"
        )
    if adjudication.get("agent_a_artifact_sha256") != expected_digest:
        raise ValueError("Agent A adjudication is not bound to the imported inventory digest")

    inventory_findings = {
        str(item.get("id", ""))
        for item in inventory.get("blocking_findings", [])
        if isinstance(item, dict)
    }
    adjudicated = {
        str(item.get("id", "")): item
        for item in adjudication.get("findings", [])
        if isinstance(item, dict)
    }
    if "" in inventory_findings or "" in adjudicated:
        raise ValueError("Agent A findings require nonempty stable IDs")
    if set(adjudicated) != inventory_findings:
        raise ValueError(
            "Agent A adjudication finding IDs do not exactly match the imported inventory"
        )

    pending = sorted(
        finding_id
        for finding_id, item in adjudicated.items()
        if str(item.get("implementation_status", "")) not in _AGENT_A_COMPLETE_STATUSES
    )
    accepted = sorted(
        finding_id
        for finding_id, item in adjudicated.items()
        if str(item.get("disposition", "")) == "ACCEPTED"
    )
    complete = sorted(inventory_findings - set(pending))
    return {
        "artifact_sha256": expected_digest,
        "finding_count": len(inventory_findings),
        "accepted_findings": accepted,
        "complete_findings": complete,
        "pending_findings": pending,
        "pending_count": len(pending),
        "adjudication_status": str(adjudication.get("status", "")),
    }


def _unsupported_runtime_purposes(audit: dict[str, Any]) -> list[str]:
    supported_patterns = tuple(str(value) for value in audit["production_policy_patterns"])
    return sorted(
        str(pattern)
        for pattern in audit["runtime_purpose_patterns"]
        if not any(_pattern_matches(str(pattern), supported) for supported in supported_patterns)
    )


def build_integration_coverage() -> dict[str, Any]:
    manifest = build_manifest()
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    audit = audit_conformance()
    agent_a = _load_agent_a()
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

    unique_choice_classes = int(audit["strategic_surface_choice_count"])
    unrouted_choice_classes = len(audit["unrouted_surface_choices"])
    reviewed_choice_classes = unique_choice_classes - unrouted_choice_classes
    unsupported_runtime_purposes = _unsupported_runtime_purposes(audit)
    missing_trigger_policy_effects = list(audit["missing_trigger_policy_effects"])
    live_policy_defect_count = len(unsupported_runtime_purposes) + len(
        missing_trigger_policy_effects
    )

    if agent_a["pending_count"]:
        status = "BLOCKED_PROVISIONAL_SURFACE"
        candidate_status = "PROVISIONAL_PENDING_AGENT_A_INTEGRATION"
    elif (
        proven_records == total_records
        and not _ENGINE_BLOCKERS
        and not record_route_gaps
        and live_policy_defect_count == 0
    ):
        status = "PASS"
        candidate_status = "FROZEN_REVIEWED"
    else:
        status = "BLOCKED_NOT_PROVEN"
        candidate_status = "FROZEN_REVIEWED"

    return {
        "schema_version": "interaction-integration-derived-v2",
        "status": status,
        "surface": {
            "candidate_status": candidate_status,
            "record_count": total_records,
            "card_composition_record_count": int(manifest["card_composition_record_count"]),
            "card_effect_record_count": int(manifest["card_effect_record_count"]),
            "global_rule_record_count": int(manifest["global_rule_record_count"]),
            "manifest_sha256": str(manifest["manifest_sha256"]),
        },
        "agent_a": agent_a,
        "record_level_evidence": {
            "engine_handler_attached": engine_evidence,
            "policy_handler_attached": policy_evidence,
            "replay_handler_attached": replay_evidence,
            "positive_test_evidence_attached": direct_test_evidence,
            "proven_records": proven_records,
        },
        "engine_rules": {
            "blocker_families": list(_ENGINE_BLOCKERS),
            "blocker_family_count": len(_ENGINE_BLOCKERS),
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
            "unique_strategic_choice_classes": unique_choice_classes,
            "reviewed_strategic_choice_classes": reviewed_choice_classes,
            "unrouted_strategic_choice_classes": unrouted_choice_classes,
            "protocol_methods_required": len(audit["protocol_methods"]),
            "protocol_methods_in_production_provider": len(
                set(audit["protocol_methods"]) & set(audit["production_policy_methods"])
            ),
            "protocol_methods_in_recorded_replay_provider": len(
                set(audit["protocol_methods"]) & set(audit["recorded_replay_methods"])
            ),
            "unsupported_runtime_purposes": unsupported_runtime_purposes,
            "missing_trigger_policy_effects": missing_trigger_policy_effects,
            "live_policy_defect_count": live_policy_defect_count,
            "audit_violation_messages": len(audit["violations"]),
        },
        "record_route_gaps": record_route_gaps,
    }


def _path_value(value: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _ledger_expectations(report: dict[str, Any]) -> dict[tuple[str, ...], Any]:
    policy = report["strategic_policy_replay"]
    evidence = report["record_level_evidence"]
    agent_a = report["agent_a"]
    surface = report["surface"]
    return {
        ("status",): report["status"],
        ("surface", "candidate_status"): surface["candidate_status"],
        ("surface", "record_count"): surface["record_count"],
        ("surface", "card_composition_record_count"): surface[
            "card_composition_record_count"
        ],
        ("surface", "card_effect_record_count"): surface["card_effect_record_count"],
        ("surface", "global_rule_record_count"): surface["global_rule_record_count"],
        ("surface", "manifest_sha256"): surface["manifest_sha256"],
        ("source_lanes", "agent_a", "artifact_sha256"): agent_a["artifact_sha256"],
        ("coverage", "requirements"): surface["record_count"],
        ("coverage", "inventory_mapped"): surface["record_count"],
        ("coverage", "record_level_proven"): evidence["proven_records"],
        ("coverage", "record_level_engine_evidence_attached"): evidence[
            "engine_handler_attached"
        ],
        ("coverage", "record_level_policy_evidence_attached"): evidence[
            "policy_handler_attached"
        ],
        ("coverage", "record_level_replay_evidence_attached"): evidence[
            "replay_handler_attached"
        ],
        ("coverage", "record_level_direct_test_evidence_attached"): evidence[
            "positive_test_evidence_attached"
        ],
        ("coverage", "records_requiring_strategic_policy"): policy[
            "records_requiring_strategic_policy"
        ],
        ("coverage", "records_requiring_no_strategic_policy"): policy[
            "records_requiring_no_strategic_policy"
        ],
        ("coverage", "policy_ready_or_not_required_records"): policy[
            "policy_ready_or_not_required_records"
        ],
        ("coverage", "records_with_policy_replay_gaps"): policy[
            "records_with_policy_replay_gaps"
        ],
        ("coverage", "strategic_choice_occurrences"): policy[
            "strategic_choice_occurrences"
        ],
        ("coverage", "reviewed_route_occurrences"): policy["reviewed_route_occurrences"],
        ("coverage", "currently_supported_occurrences"): policy[
            "currently_supported_occurrences"
        ],
        ("coverage", "strategic_choice_classes_required"): policy[
            "unique_strategic_choice_classes"
        ],
        ("coverage", "strategic_choice_classes_with_reviewed_routes"): policy[
            "reviewed_strategic_choice_classes"
        ],
        ("coverage", "strategic_choice_classes_unrouted"): policy[
            "unrouted_strategic_choice_classes"
        ],
        ("coverage", "strategic_protocol_methods_required"): policy[
            "protocol_methods_required"
        ],
        ("coverage", "strategic_protocol_methods_in_production_provider"): policy[
            "protocol_methods_in_production_provider"
        ],
        ("coverage", "strategic_protocol_methods_in_recorded_replay_provider"): policy[
            "protocol_methods_in_recorded_replay_provider"
        ],
        ("coverage", "engine_blocker_families"): report["engine_rules"][
            "blocker_family_count"
        ],
        ("coverage", "live_policy_defects"): policy["live_policy_defect_count"],
        ("coverage", "agent_a_findings_total"): agent_a["finding_count"],
        ("coverage", "agent_a_findings_complete"): len(agent_a["complete_findings"]),
        ("coverage", "agent_a_findings_pending"): agent_a["pending_count"],
        ("remaining_engine_blockers",): report["engine_rules"]["blocker_families"],
        ("remaining_policy_replay_findings", "records_requiring_strategic_policy"): policy[
            "records_requiring_strategic_policy"
        ],
        ("remaining_policy_replay_findings", "records_currently_complete"): policy[
            "current_support_complete_records"
        ],
        ("remaining_policy_replay_findings", "records_with_policy_replay_gaps"): policy[
            "records_with_policy_replay_gaps"
        ],
        ("remaining_policy_replay_findings", "unrouted_strategic_choice_classes"): policy[
            "unrouted_strategic_choice_classes"
        ],
        ("remaining_policy_replay_findings", "runtime_policy_handler_missing"): policy[
            "unsupported_runtime_purposes"
        ],
        ("remaining_policy_replay_findings", "trigger_target_effect_policy_missing"): policy[
            "missing_trigger_policy_effects"
        ],
        ("agent_a_findings", "artifact_sha256"): agent_a["artifact_sha256"],
        ("agent_a_findings", "total"): agent_a["finding_count"],
        ("agent_a_findings", "complete"): agent_a["complete_findings"],
        ("agent_a_findings", "pending"): agent_a["pending_findings"],
    }


def check_ledger(
    report: dict[str, Any],
    *,
    ledger_path: Path = LEDGER_PATH,
    emit: bool = True,
) -> bool:
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    expected = _ledger_expectations(report)
    mismatches = {
        ".".join(path): {"expected": wanted, "actual": _path_value(ledger, path)}
        for path, wanted in expected.items()
        if _path_value(ledger, path) != wanted
    }

    expected_coverage_keys = {path[-1] for path in expected if path[:1] == ("coverage",)}
    actual_coverage = ledger.get("coverage", {})
    if not isinstance(actual_coverage, dict):
        mismatches["coverage"] = {"expected": "object", "actual": type(actual_coverage).__name__}
    elif set(actual_coverage) != expected_coverage_keys:
        mismatches["coverage.keys"] = {
            "expected": sorted(expected_coverage_keys),
            "actual": sorted(actual_coverage),
        }

    result = {
        "status": "FAIL" if mismatches else "PASS",
        "checked_field_count": len(expected),
        "mismatches": mismatches,
    }
    if emit:
        print(json.dumps(result, indent=2, sort_keys=True))
    return not mismatches


def _check_ledger(report: dict[str, Any]) -> bool:
    """Backward-compatible wrapper for callers that used the original private helper."""

    return check_ledger(report)


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
    if args.check_ledger and not check_ledger(report):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
