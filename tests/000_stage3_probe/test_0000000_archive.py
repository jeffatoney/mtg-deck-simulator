from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
WITNESS_PATH = (
    ROOT / "tests/phase_c/test_malcolm_glint_horn_witness_contract.py"
)
ARCHIVE = ROOT / (
    "docs/audit/phase-c-postpilot/evidence/"
    "pr100-glint-horn-repaired-behavior-4d15c185.zip"
)


def _witness_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage3_archive_probe_impl",
        WITNESS_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _compact_decision(decision: dict[str, object]) -> dict[str, object]:
    return {
        key: decision.get(key)
        for key in (
            "decision_index",
            "turn",
            "phase",
            "step",
            "actual_selected_public_action",
            "actual_selected_public_key",
            "actual_selected_metadata",
            "actual_selected_payload",
            "selected_action",
            "selected_action_metadata",
            "selected_action_payload",
            "post_state_hash",
            "public_state_digest",
        )
        if key in decision
    }


def test_repaired_archive_revalidation() -> None:
    witness = _witness_module()
    payload: dict[str, object] = {
        "schema_version": "pr100-stage3-archive-probe-v1",
        "archive_sha256": hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),
        "members": {},
        "metrics": {},
        "records": {},
        "divergences": {},
    }
    with zipfile.ZipFile(ARCHIVE) as archive:
        payload["member_set"] = sorted(archive.namelist())
        for name in sorted(archive.namelist()):
            raw = archive.read(name)
            data = json.loads(raw)
            payload["members"][name] = {
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
            }
            payload["metrics"][name] = witness._archive_metrics(data)
            decisions = data["decisions"]
            selected = [
                _compact_decision(decision)
                for decision in decisions
                if decision.get("actual_selected_public_action") != "PASS"
            ]
            payload["records"][name] = {
                "top_level_keys": sorted(data),
                "game_record": data.get("game_record"),
                "first_decision_keys": sorted(decisions[0]),
                "selected_nonpass": selected,
            }
        legacy_101 = witness._load_member(archive, "legacy-101.json")
        repaired_101 = witness._load_member(archive, "repaired-101.json")
        legacy_391 = witness._load_member(
            archive,
            "legacy-391730338978874520.json",
        )
        repaired_391 = witness._load_member(
            archive,
            "repaired-391730338978874520.json",
        )
        for label, legacy, repaired in (
            ("101", legacy_101, repaired_101),
            ("391730338978874520", legacy_391, repaired_391),
        ):
            payload["divergences"][label] = {
                field: witness._first_divergence(legacy, repaired, field)
                for field in (
                    "actual_selected_public_key",
                    "actual_post_state_hash",
                    "actual_public_state_digest",
                )
            }
    pytest.exit(
        "STAGE3_ARCHIVE_PROBE="
        + json.dumps(payload, sort_keys=True, separators=(",", ":")),
        returncode=1,
    )
