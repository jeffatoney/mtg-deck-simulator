#!/usr/bin/env python3
"""Verify Phase A authority classification and legacy-pilot quarantine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "automation/phase-a-authority-map.json"
REQUIRED_MAP_REFERENCE = "docs/governance/PHASE_A_AUTHORITY_MAP.md"
REFERENCE_FILES = (
    ROOT / "docs/spec/ENGINE_BUILD_PHASE_A.md",
    ROOT / "prompts/recovery/PHASE_A_ENGINE_BUILD.md",
)


def _load_map() -> dict[str, Any]:
    value = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("authority map must be a JSON object")
    return value


def _string_list(value: object, field: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        errors.append(f"{field} must be a list of strings")
        return []
    return value


def main() -> int:
    errors: list[str] = []
    if not MAP_PATH.is_file():
        print(f"ERROR: missing authority map: {MAP_PATH.relative_to(ROOT)}")
        return 1

    authority = _load_map()
    if authority.get("schema_version") != "phase-a-authority-v1":
        errors.append("unexpected authority-map schema version")
    if authority.get("phase") != "PHASE_A_CLEAN_ENGINE":
        errors.append("authority map is not scoped to PHASE_A_CLEAN_ENGINE")

    active = _string_list(authority.get("active_binding"), "active_binding", errors)
    archival_files = _string_list(
        authority.get("archival_reference_only_files"),
        "archival_reference_only_files",
        errors,
    )
    forbidden = _string_list(
        authority.get("forbidden_active_paths"), "forbidden_active_paths", errors
    )
    required_archival = _string_list(
        authority.get("required_archival_paths"), "required_archival_paths", errors
    )
    labels = _string_list(
        authority.get("required_evidence_labels"), "required_evidence_labels", errors
    )

    for relative in active:
        if not (ROOT / relative).is_file():
            errors.append(f"missing ACTIVE_BINDING file: {relative}")
    for relative in required_archival:
        if not (ROOT / relative).is_file():
            errors.append(f"missing required archival file: {relative}")
    for relative in forbidden:
        if (ROOT / relative).exists():
            errors.append(f"forbidden active path exists: {relative}")

    overlap = sorted(set(active).intersection(archival_files))
    if overlap:
        errors.append(f"files classified as both active and archival: {overlap}")

    required_labels = {
        "CLEAN_ENGINE_PRODUCTION_PATH",
        "SOURCE_VALIDATION_ONLY",
        "LEGACY_REFERENCE_PATH",
    }
    if set(labels) != required_labels:
        errors.append("required evidence labels do not match the frozen Phase A set")
    if (
        authority.get("only_acceptance_evidence_label")
        != "CLEAN_ENGINE_PRODUCTION_PATH"
    ):
        errors.append(
            "only_acceptance_evidence_label is not CLEAN_ENGINE_PRODUCTION_PATH"
        )
    if (
        authority.get("handoff_manifest_semantics")
        != "HISTORICAL_INTEGRITY_ONLY_NOT_CURRENT_AUTHORITY"
    ):
        errors.append("HANDOFF_MANIFEST semantics are not limited to historical integrity")

    for path in REFERENCE_FILES:
        if not path.is_file():
            errors.append(f"missing Phase A reference file: {path.relative_to(ROOT)}")
            continue
        if REQUIRED_MAP_REFERENCE not in path.read_text(encoding="utf-8"):
            errors.append(
                f"{path.relative_to(ROOT)} does not reference {REQUIRED_MAP_REFERENCE}"
            )

    if errors:
        print("Phase A authority check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        json.dumps(
            {
                "status": "PASS",
                "schema_version": authority["schema_version"],
                "active_binding_count": len(active),
                "forbidden_active_paths_absent": forbidden,
                "required_archival_paths_present": required_archival,
                "acceptance_evidence_label": authority[
                    "only_acceptance_evidence_label"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
