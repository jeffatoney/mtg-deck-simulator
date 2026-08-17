from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from scripts.check_repository_evidence import EvidenceError, validate_repository


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _action(identity: str, handle: str) -> dict[str, Any]:
    key = json.dumps(
        {
            "identity": identity,
            "kind": "CAST",
            "mana_value": 1,
            "metadata": {},
            "tags": ["SPELL"],
            "target_count": 0,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "public_action_key": key,
        "public_action_key_sha256": hashlib.sha256(key.encode()).hexdigest(),
        "action_kind": "CAST",
        "public_identity": identity,
        "mana_value": 1,
        "target_count": 0,
        "public_tags": ["SPELL"],
        "canonical_public_metadata": {},
        "substantive_score_prefix": [1, 0, 0, -1, 0],
        "internal_opaque_handle": handle,
    }


def _raw(selector: str, seed: int) -> dict[str, Any]:
    historical = _action("Opt", "legacy-handle")
    repaired = _action("Siren Stormtamer", "repaired-handle")
    actual = historical if selector == "legacy" else repaired
    decision = {
        "decision_index": 0,
        "turn_number": 2,
        "phase": "PRECOMBAT_MAIN",
        "step": "PRECOMBAT_MAIN",
        "tie_classification": "DISTINCT_PUBLIC_KEYS",
        "top_substantive_score_prefix": [1, 0, 0, -1, 0],
        "top_candidate_count": 2,
        "top_distinct_public_key_count": 2,
        "historical_selected_public_action": historical,
        "repaired_selected_public_action": repaired,
        "actual_selected_public_action": actual,
        "historical_and_repaired_selections_differ": True,
        "difference_attributable_only_to_final_ordering": True,
        "pre_decision_full_state_hash": f"state-{seed}",
        "public_observation_digest": f"observation-{seed}",
        "post_decision_full_state_hash": f"post-{selector}-{seed}",
        "resulting_public_state_digest": f"public-{selector}-{seed}",
    }
    return {
        "schema_version": "fixture",
        "commit": "source-commit",
        "tree": "source-tree",
        "seed": seed,
        "mode": "STANDARD",
        "selector": selector,
        "through_turn": 10,
        "policy_actions": True,
        "fresh_replay_requested": True,
        "status": "PASS",
        "summary": {
            "decision_counts": {
                "total_standard_decisions": 1,
                "decisions_with_no_substantive_tie": 0,
                "decisions_tied_only_same_public_key": 0,
                "decisions_tied_distinct_public_keys": 1,
                "decisions_where_historical_and_repaired_selections_differ": 1,
            },
            "first_selector_difference_decision_index": 0,
            "actual_public_action_sequence_sha256": f"sequence-{selector}-{seed}",
            "selector": selector,
            "outcome": {
                "controlled_turns_completed": 10,
                "terminal_status": "ACTIVE",
                "command_count": 1,
                "final_state_hash": f"final-{selector}-{seed}",
                "fresh_replay_state_hash": f"final-{selector}-{seed}",
                "fresh_replay_equal": True,
                "actual_first_attempt_turn": None,
                "attempt_package": None,
                "combo_earliest_legal_turn": {},
            },
            "final_state_capture": {
                "final_full_state_hash": f"final-{selector}-{seed}",
                "life": {"P0": 40, "P1": 40, "P2": 40, "P3": 40},
                "loss_reasons": {"P0": [], "P1": [], "P2": [], "P3": []},
                "terminal": {
                    "status": "ACTIVE",
                    "winners": [],
                    "losers": [],
                    "cause_event_ids": [],
                },
            },
        },
        "decisions": [decision],
    }


def _action_summary(action: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_kind": action["action_kind"],
        "public_identity": action.get("public_identity"),
        "canonical_public_metadata": action.get("canonical_public_metadata", {}),
        "mana_value": action["mana_value"],
        "target_count": action["target_count"],
        "substantive_score_prefix": action["substantive_score_prefix"],
        "public_action_key_sha256": action["public_action_key_sha256"],
    }


def _first_preference(raw: dict[str, Any]) -> dict[str, Any]:
    decision = raw["decisions"][0]
    return {
        "decision_index": 0,
        "turn_number": decision["turn_number"],
        "phase": decision["phase"],
        "step": decision["step"],
        "tie_classification": decision["tie_classification"],
        "top_substantive_score_prefix": decision["top_substantive_score_prefix"],
        "top_candidate_count": decision["top_candidate_count"],
        "top_distinct_public_key_count": decision["top_distinct_public_key_count"],
        "historical_selected_public_action": _action_summary(
            decision["historical_selected_public_action"]
        ),
        "repaired_selected_public_action": _action_summary(
            decision["repaired_selected_public_action"]
        ),
        "difference_attributable_only_to_final_ordering": True,
        "pre_decision_full_state_hash": decision["pre_decision_full_state_hash"],
        "public_observation_digest": decision["public_observation_digest"],
    }


def _run_projection(name: str, raw: dict[str, Any], member_sha: str) -> dict[str, Any]:
    return {
        "evidence_member": name,
        "member_sha256": member_sha,
        "selector": raw["selector"],
        "seed": int(raw["seed"]),
        "status": "PASS",
        "decision_counts": raw["summary"]["decision_counts"],
        "first_selector_difference_decision_index": 0,
        "actual_public_action_sequence_sha256": raw["summary"][
            "actual_public_action_sequence_sha256"
        ],
        "outcome": {
            **raw["summary"]["outcome"],
            "final_life": raw["summary"]["final_state_capture"]["life"],
            "loss_reasons": raw["summary"]["final_state_capture"]["loss_reasons"],
        },
        "first_selector_preference": _first_preference(raw),
    }


def _trajectory(legacy: dict[str, Any], repaired: dict[str, Any]) -> dict[str, Any]:
    legacy_action = legacy["decisions"][0]["actual_selected_public_action"]
    repaired_action = repaired["decisions"][0]["actual_selected_public_action"]
    return {
        "first_actual_public_action_key_difference_decision_index": 0,
        "pre_decision_full_state_equal_at_first_public_difference": True,
        "public_observation_digest_equal_at_first_public_difference": True,
        "legacy_actual_public_action": _action_summary(legacy_action),
        "repaired_actual_public_action": _action_summary(repaired_action),
        "first_same_public_key_different_opaque_representative_decision_index": None,
    }


def _write_fixture(root: Path) -> tuple[Path, Path]:
    case = root / "docs/audit/case"
    case.mkdir(parents=True)
    archive = case / "raw.zip"
    raws = {
        "legacy-101.json": _raw("legacy", 101),
        "repaired-101.json": _raw("repaired", 101),
        "legacy-391730338978874520.json": _raw("legacy", 391730338978874520),
        "repaired-391730338978874520.json": _raw("repaired", 391730338978874520),
    }
    member_bytes = {
        name: json.dumps(value, sort_keys=True).encode() for name, value in raws.items()
    }
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for name, data in member_bytes.items():
            zipped.writestr(name, data)

    members = []
    for name, raw in raws.items():
        data = member_bytes[name]
        members.append(
            {
                "name": name,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
                "selector": raw["selector"],
                "seed": int(raw["seed"]),
                "status": "PASS",
                "commit": "source-commit",
                "tree": "source-tree",
            }
        )
    member_sha = {member["name"]: member["sha256"] for member in members}

    analysis = {
        "schema_version": "1.0.0",
        "source_evidence": {
            "artifact_sha256": _sha256(archive),
            "durable_archive_path": "docs/audit/case/raw.zip",
        },
        "runs": {
            "legacy_101": _run_projection(
                "legacy-101.json", raws["legacy-101.json"], member_sha["legacy-101.json"]
            ),
            "repaired_101": _run_projection(
                "repaired-101.json",
                raws["repaired-101.json"],
                member_sha["repaired-101.json"],
            ),
            "legacy_391730338978874520": _run_projection(
                "legacy-391730338978874520.json",
                raws["legacy-391730338978874520.json"],
                member_sha["legacy-391730338978874520.json"],
            ),
            "repaired_391730338978874520": _run_projection(
                "repaired-391730338978874520.json",
                raws["repaired-391730338978874520.json"],
                member_sha["repaired-391730338978874520.json"],
            ),
        },
        "selector_trajectory_comparison": {
            "101": _trajectory(raws["legacy-101.json"], raws["repaired-101.json"]),
            "391730338978874520": _trajectory(
                raws["legacy-391730338978874520.json"],
                raws["repaired-391730338978874520.json"],
            ),
        },
    }
    analysis_path = case / "analysis.json"
    analysis_path.write_text(json.dumps(analysis), encoding="utf-8")

    index = {
        "schema_version": "1.0.0",
        "tracked_roots": ["docs/audit/case"],
        "artifacts": [
            {
                "path": "docs/audit/case/raw.zip",
                "kind": "raw_evidence_zip",
                "size_bytes": archive.stat().st_size,
                "sha256": _sha256(archive),
                "members": members,
            },
            {
                "path": "docs/audit/case/analysis.json",
                "kind": "behavioral_analysis_json",
                "size_bytes": analysis_path.stat().st_size,
                "sha256": _sha256(analysis_path),
            },
        ],
    }
    index_path = root / "docs/audit/EVIDENCE_INDEX.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index), encoding="utf-8")
    return archive, analysis_path


def _refresh_index_entry(root: Path, path: Path) -> None:
    index_path = root / "docs/audit/EVIDENCE_INDEX.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    relative = path.relative_to(root).as_posix()
    entry = next(item for item in index["artifacts"] if item["path"] == relative)
    entry["size_bytes"] = path.stat().st_size
    entry["sha256"] = _sha256(path)
    index_path.write_text(json.dumps(index), encoding="utf-8")


def test_valid_fixture_passes(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    validate_repository(tmp_path)


def test_missing_indexed_artifact_fails(tmp_path: Path) -> None:
    archive, _ = _write_fixture(tmp_path)
    archive.unlink()
    with pytest.raises(EvidenceError, match="missing"):
        validate_repository(tmp_path)


def test_hash_mismatch_fails(tmp_path: Path) -> None:
    _, analysis = _write_fixture(tmp_path)
    text = analysis.read_text(encoding="utf-8")
    analysis.write_text(text.replace("schema_version", "schema_versioN", 1), encoding="utf-8")
    with pytest.raises(EvidenceError, match="SHA-256 mismatch"):
        validate_repository(tmp_path)


def test_unindexed_tracked_file_fails(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    extra = tmp_path / "docs/audit/case/claimed-report.md"
    extra.write_text("claimed but not indexed\n", encoding="utf-8")
    with pytest.raises(EvidenceError, match="not indexed"):
        validate_repository(tmp_path)


def test_forbidden_pr_scaffolding_fails(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    script = tmp_path / "scripts/pr100_apply_fix.py"
    script.parent.mkdir(parents=True)
    script.write_text("print('mutate source')\n", encoding="utf-8")
    with pytest.raises(EvidenceError, match="investigation scaffolding"):
        validate_repository(tmp_path)


def test_zip_member_identity_mismatch_fails_even_when_archive_hash_is_refreshed(
    tmp_path: Path,
) -> None:
    archive, _ = _write_fixture(tmp_path)
    with zipfile.ZipFile(archive, "r") as zipped:
        members = {name: zipped.read(name) for name in zipped.namelist()}
    changed = json.loads(members["legacy-101.json"])
    changed["commit"] = "wrong-commit"
    members["legacy-101.json"] = json.dumps(changed, sort_keys=True).encode()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for name, data in members.items():
            zipped.writestr(name, data)
    _refresh_index_entry(tmp_path, archive)
    index_path = tmp_path / "docs/audit/EVIDENCE_INDEX.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    raw_entry = next(item for item in index["artifacts"] if item["kind"] == "raw_evidence_zip")
    member_entry = next(item for item in raw_entry["members"] if item["name"] == "legacy-101.json")
    member_entry["size_bytes"] = len(members["legacy-101.json"])
    member_entry["sha256"] = hashlib.sha256(members["legacy-101.json"]).hexdigest()
    index_path.write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(EvidenceError, match="identity mismatch"):
        validate_repository(tmp_path)


def test_analysis_projection_mismatch_fails_even_when_report_hash_is_refreshed(
    tmp_path: Path,
) -> None:
    _, analysis_path = _write_fixture(tmp_path)
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    analysis["runs"]["legacy_101"]["decision_counts"]["total_standard_decisions"] = 999
    analysis_path.write_text(json.dumps(analysis), encoding="utf-8")
    _refresh_index_entry(tmp_path, analysis_path)
    with pytest.raises(EvidenceError, match="projection does not match raw evidence"):
        validate_repository(tmp_path)
