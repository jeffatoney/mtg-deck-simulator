#!/usr/bin/env python3
"""Fail-closed verification for durable repository audit evidence."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

INDEX_PATH = Path("docs/audit/EVIDENCE_INDEX.json")
PR_WORKFLOW_RE = re.compile(r"^\.github/workflows/pr\d+[-_].*\.ya?ml$", re.IGNORECASE)
PR_SCRIPT_RE = re.compile(r"^scripts/pr\d+[-_].*\.py$", re.IGNORECASE)
EXPLICIT_TEMP_WORKFLOWS = {
    ".github/workflows/public-policy-noninterference-first-failure.yml",
    ".github/workflows/public-policy-noninterference-test-diagnostic.yml",
}


class EvidenceError(RuntimeError):
    """Raised when repository evidence fails a durable-evidence invariant."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _safe_relative_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or value.strip() != value:
        raise EvidenceError(f"unsafe repository-relative path: {value!r}")
    return path


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"invalid JSON: {path}: {exc}") from exc


def _artifact_by_kind(index: dict[str, Any], kind: str) -> dict[str, Any]:
    matches = [item for item in index["artifacts"] if item.get("kind") == kind]
    if len(matches) != 1:
        raise EvidenceError(f"expected exactly one {kind!r} artifact, found {len(matches)}")
    return matches[0]


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


def _first_selector_preference(raw: dict[str, Any]) -> dict[str, Any] | None:
    index = raw["summary"]["first_selector_difference_decision_index"]
    if index is None:
        return None
    decision = raw["decisions"][index]
    return {
        "decision_index": index,
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
        "difference_attributable_only_to_final_ordering": decision[
            "difference_attributable_only_to_final_ordering"
        ],
        "pre_decision_full_state_hash": decision["pre_decision_full_state_hash"],
        "public_observation_digest": decision["public_observation_digest"],
    }


def _outcome_projection(raw: dict[str, Any]) -> dict[str, Any]:
    outcome = raw["summary"]["outcome"]
    final_state = raw["summary"]["final_state_capture"]
    return {
        "controlled_turns_completed": outcome["controlled_turns_completed"],
        "terminal_status": outcome["terminal_status"],
        "command_count": outcome["command_count"],
        "final_state_hash": outcome["final_state_hash"],
        "fresh_replay_state_hash": outcome["fresh_replay_state_hash"],
        "fresh_replay_equal": outcome["fresh_replay_equal"],
        "actual_first_attempt_turn": outcome["actual_first_attempt_turn"],
        "attempt_package": outcome["attempt_package"],
        "combo_earliest_legal_turn": outcome["combo_earliest_legal_turn"],
        "final_life": final_state["life"],
        "loss_reasons": final_state["loss_reasons"],
    }


def _expected_run_projection(
    member_name: str,
    member_sha256: str,
    raw: dict[str, Any],
) -> dict[str, Any]:
    return {
        "evidence_member": member_name,
        "member_sha256": member_sha256,
        "selector": raw["selector"],
        "seed": int(raw["seed"]),
        "status": raw["status"],
        "decision_counts": raw["summary"]["decision_counts"],
        "first_selector_difference_decision_index": raw["summary"][
            "first_selector_difference_decision_index"
        ],
        "actual_public_action_sequence_sha256": raw["summary"][
            "actual_public_action_sequence_sha256"
        ],
        "outcome": _outcome_projection(raw),
        "first_selector_preference": _first_selector_preference(raw),
    }


def _trajectory_projection(
    legacy: dict[str, Any],
    repaired: dict[str, Any],
) -> dict[str, Any]:
    first_public_difference: int | None = None
    first_same_key_different_handle: int | None = None

    for index, (legacy_decision, repaired_decision) in enumerate(
        zip(legacy["decisions"], repaired["decisions"], strict=False)
    ):
        legacy_action = legacy_decision["actual_selected_public_action"]
        repaired_action = repaired_decision["actual_selected_public_action"]
        same_key = legacy_action["public_action_key"] == repaired_action["public_action_key"]

        if first_public_difference is None and not same_key:
            first_public_difference = index
        if (
            first_same_key_different_handle is None
            and same_key
            and legacy_action["internal_opaque_handle"] != repaired_action["internal_opaque_handle"]
        ):
            first_same_key_different_handle = index

    if first_public_difference is None:
        raise EvidenceError("selector trajectories never differ by public action key")

    legacy_decision = legacy["decisions"][first_public_difference]
    repaired_decision = repaired["decisions"][first_public_difference]
    result: dict[str, Any] = {
        "first_actual_public_action_key_difference_decision_index": first_public_difference,
        "pre_decision_full_state_equal_at_first_public_difference": (
            legacy_decision["pre_decision_full_state_hash"]
            == repaired_decision["pre_decision_full_state_hash"]
        ),
        "public_observation_digest_equal_at_first_public_difference": (
            legacy_decision["public_observation_digest"]
            == repaired_decision["public_observation_digest"]
        ),
        "legacy_actual_public_action": _action_summary(
            legacy_decision["actual_selected_public_action"]
        ),
        "repaired_actual_public_action": _action_summary(
            repaired_decision["actual_selected_public_action"]
        ),
        "first_same_public_key_different_opaque_representative_decision_index": (
            first_same_key_different_handle
        ),
    }

    if first_same_key_different_handle is not None:
        legacy_equivalent = legacy["decisions"][first_same_key_different_handle]
        repaired_equivalent = repaired["decisions"][first_same_key_different_handle]
        result["equivalent_representative_detail"] = {
            "public_action_key_equal": (
                legacy_equivalent["actual_selected_public_action"]["public_action_key"]
                == repaired_equivalent["actual_selected_public_action"]["public_action_key"]
            ),
            "legacy_public_action": _action_summary(
                legacy_equivalent["actual_selected_public_action"]
            ),
            "repaired_public_action": _action_summary(
                repaired_equivalent["actual_selected_public_action"]
            ),
            "post_decision_full_state_equal": (
                legacy_equivalent["post_decision_full_state_hash"]
                == repaired_equivalent["post_decision_full_state_hash"]
            ),
            "resulting_public_state_digest_equal": (
                legacy_equivalent["resulting_public_state_digest"]
                == repaired_equivalent["resulting_public_state_digest"]
            ),
        }
    return result


def _validate_raw_zip(
    root: Path,
    entry: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    archive_path = root / _safe_relative_path(entry["path"])
    expected_members = entry.get("members")
    if not isinstance(expected_members, list) or not expected_members:
        raise EvidenceError("raw evidence ZIP must declare a nonempty members list")

    expected_names = [str(member["name"]) for member in expected_members]
    if len(expected_names) != len(set(expected_names)):
        raise EvidenceError("duplicate raw evidence member name in index")

    raw_members: dict[str, dict[str, Any]] = {}
    try:
        with zipfile.ZipFile(archive_path) as archive:
            actual_names = sorted(archive.namelist())
            if actual_names != sorted(expected_names):
                raise EvidenceError(
                    "raw evidence member set mismatch: "
                    f"expected {sorted(expected_names)}, got {actual_names}"
                )
            for member in expected_members:
                name = str(member["name"])
                data = archive.read(name)
                if len(data) != int(member["size_bytes"]):
                    raise EvidenceError(f"raw evidence size mismatch for {name}")
                if _sha256_bytes(data) != member["sha256"]:
                    raise EvidenceError(f"raw evidence SHA-256 mismatch for {name}")
                try:
                    value = json.loads(data)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise EvidenceError(f"raw evidence member is invalid JSON: {name}") from exc
                for key in ("selector", "seed", "status", "commit", "tree"):
                    expected = member[key]
                    actual = value[key]
                    if key == "seed":
                        actual = int(actual)
                    if actual != expected:
                        raise EvidenceError(
                            f"raw evidence identity mismatch for {name}: {key} "
                            f"expected {expected!r}, got {actual!r}"
                        )
                if value["status"] != "PASS":
                    raise EvidenceError(f"raw evidence member did not pass: {name}")
                if not value["summary"]["outcome"]["fresh_replay_equal"]:
                    raise EvidenceError(f"fresh replay mismatch in raw evidence member: {name}")
                raw_members[name] = value
    except (OSError, zipfile.BadZipFile) as exc:
        raise EvidenceError(f"invalid raw evidence ZIP: {archive_path}: {exc}") from exc
    return raw_members


def _validate_behavioral_analysis(
    root: Path,
    index: dict[str, Any],
    raw_entry: dict[str, Any],
    raw_members: dict[str, dict[str, Any]],
) -> None:
    analysis_entry = _artifact_by_kind(index, "behavioral_analysis_json")
    analysis = _load_json(root / _safe_relative_path(analysis_entry["path"]))
    if analysis.get("schema_version") != "1.0.0":
        raise EvidenceError("unsupported behavioral analysis schema version")
    source = analysis.get("source_evidence", {})
    if source.get("artifact_sha256") != raw_entry["sha256"]:
        raise EvidenceError("analysis does not bind the indexed raw archive digest")
    if source.get("durable_archive_path") != raw_entry["path"]:
        raise EvidenceError("analysis does not bind the indexed raw archive path")

    member_sha = {member["name"]: member["sha256"] for member in raw_entry["members"]}
    expected_run_members = {
        "legacy_101": "legacy-101.json",
        "repaired_101": "repaired-101.json",
        "legacy_391730338978874520": "legacy-391730338978874520.json",
        "repaired_391730338978874520": "repaired-391730338978874520.json",
    }
    runs = analysis.get("runs", {})
    if set(runs) != set(expected_run_members):
        raise EvidenceError("behavioral analysis run set does not match expected evidence members")
    for run_name, member_name in expected_run_members.items():
        expected = _expected_run_projection(
            member_name, member_sha[member_name], raw_members[member_name]
        )
        if runs[run_name] != expected:
            raise EvidenceError(
                f"behavioral analysis projection does not match raw evidence: {run_name}"
            )

    expected_trajectory = {
        "101": _trajectory_projection(
            raw_members["legacy-101.json"],
            raw_members["repaired-101.json"],
        ),
        "391730338978874520": _trajectory_projection(
            raw_members["legacy-391730338978874520.json"],
            raw_members["repaired-391730338978874520.json"],
        ),
    }
    if analysis.get("selector_trajectory_comparison") != expected_trajectory:
        raise EvidenceError("selector trajectory comparison does not match raw evidence")


def _validate_forbidden_scaffolding(root: Path) -> None:
    diagnostic_root = root / ".github/diagnostics"
    if diagnostic_root.is_dir():
        files = sorted(
            path.relative_to(root).as_posix()
            for path in diagnostic_root.rglob("*")
            if path.is_file()
        )
        if files:
            raise EvidenceError("temporary diagnostic files remain committed: " + ", ".join(files))

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if (
            PR_WORKFLOW_RE.match(relative)
            or PR_SCRIPT_RE.match(relative)
            or relative in EXPLICIT_TEMP_WORKFLOWS
        ):
            raise EvidenceError(
                f"temporary PR-scoped investigation scaffolding remains: {relative}"
            )


def validate_repository(root: Path) -> None:
    root = root.resolve()
    index_path = root / INDEX_PATH
    index = _load_json(index_path)
    if index.get("schema_version") != "1.0.0":
        raise EvidenceError("unsupported evidence index schema version")

    artifacts = index.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise EvidenceError("evidence index must contain a nonempty artifacts list")

    indexed_paths: set[str] = set()
    for artifact in artifacts:
        relative = _safe_relative_path(str(artifact["path"]))
        relative_text = relative.as_posix()
        if relative_text in indexed_paths:
            raise EvidenceError(f"duplicate indexed evidence path: {relative_text}")
        indexed_paths.add(relative_text)
        path = root / relative
        if not path.is_file():
            raise EvidenceError(f"indexed evidence is missing: {relative_text}")
        if path.stat().st_size <= 0:
            raise EvidenceError(f"indexed evidence is empty: {relative_text}")
        if path.stat().st_size != int(artifact["size_bytes"]):
            raise EvidenceError(f"indexed evidence size mismatch: {relative_text}")
        if _sha256_file(path) != artifact["sha256"]:
            raise EvidenceError(f"indexed evidence SHA-256 mismatch: {relative_text}")

    tracked_roots = index.get("tracked_roots", [])
    if not isinstance(tracked_roots, list) or not tracked_roots:
        raise EvidenceError("evidence index must declare at least one tracked root")
    for tracked in tracked_roots:
        tracked_path = root / _safe_relative_path(str(tracked))
        if not tracked_path.is_dir():
            raise EvidenceError(f"tracked evidence root is missing: {tracked}")
        for path in tracked_path.rglob("*"):
            if path.is_file():
                relative = path.relative_to(root).as_posix()
                if relative not in indexed_paths:
                    raise EvidenceError(f"tracked evidence file is not indexed: {relative}")

    raw_entry = _artifact_by_kind(index, "raw_evidence_zip")
    raw_members = _validate_raw_zip(root, raw_entry)
    _validate_behavioral_analysis(root, index, raw_entry, raw_members)
    _validate_forbidden_scaffolding(root)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) > 1:
        print("usage: check_repository_evidence.py [REPOSITORY_ROOT]", file=sys.stderr)
        return 2
    root = Path(args[0]) if args else Path(".")
    try:
        validate_repository(root)
    except EvidenceError as exc:
        print(f"FAIL: repository evidence integrity: {exc}", file=sys.stderr)
        return 1
    print("PASS: repository evidence integrity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
