#!/usr/bin/env python3
"""Fail when the durable Phase A certification no longer covers the current tree."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _certification_provenance import verify_github_actions_candidate  # noqa: E402
from _phase_a_paths import aggregate_digest, all_digests, all_digests_at_commit  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TRACKED_RECORD_PATH = ROOT / "docs/audit/phase-a-certification/CERTIFICATION.json"
_configured_record = os.environ.get("PHASE_A_CERTIFICATION_RECORD", "").strip()
RECORD_PATH = Path(_configured_record) if _configured_record else TRACKED_RECORD_PATH
if not RECORD_PATH.is_absolute():
    RECORD_PATH = ROOT / RECORD_PATH
APPROVAL_PATH = ROOT / "docs/spec/identity/IDENTITY_MODEL_V2.0.0_APPROVAL_RECORD.json"
MAPPING_PATH = ROOT / "automation/phase-a-test-mapping.json"
RULES_PATH = ROOT / "docs/source/MagicCompRules_2026-06-19.txt"
ORACLE_PATH = ROOT / "docs/source/oracle/snapshot_v1.json"
EXPECTED_SCHEMA = "phase-a-certification-v3"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{_display_path(path)} must contain a JSON object")
    return value


def _commit_exists(commit: str) -> bool:
    completed = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> int:
    if not RECORD_PATH.is_file():
        print(
            "Phase A certification check failed:\n"
            f"- no durable certification at {_display_path(RECORD_PATH)}",
            file=sys.stderr,
        )
        return 1

    try:
        record = _load_json(RECORD_PATH)
        approval = _load_json(APPROVAL_PATH)
        mapping = _load_json(MAPPING_PATH)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Phase A certification check failed:\n- {error}", file=sys.stderr)
        return 1

    errors: list[str] = []
    if record.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"unexpected certification schema {record.get('schema_version')!r}")
    if record.get("status") != "PASS":
        errors.append("certification status is not PASS")
    if record.get("evidence_classification") != "CLEAN_ENGINE_PRODUCTION_PATH":
        errors.append("certification is not CLEAN_ENGINE_PRODUCTION_PATH evidence")
    if record.get("legacy_evidence_used") is not False:
        errors.append("certification does not assert legacy_evidence_used == false")
    if record.get("clean_tree_before_run") is not True:
        errors.append("certification does not assert a clean tree before verification")
    if record.get("verification_environment") != "GITHUB_ACTIONS":
        errors.append("authoritative certification must be produced by GITHUB_ACTIONS")

    run_id = record.get("github_run_id")
    run_url = record.get("github_run_url")
    artifact = record.get("ci_artifact_name")
    commit = record.get("certified_content_commit")
    if not isinstance(run_id, str) or not run_id.isdigit():
        errors.append("github_run_id is missing or invalid")
    if not isinstance(run_url, str) or not run_url.endswith(f"/actions/runs/{run_id}"):
        errors.append("github_run_url is missing or does not match github_run_id")
    if not isinstance(commit, str) or _COMMIT.fullmatch(commit) is None:
        errors.append("certified_content_commit is missing or invalid")
    elif not _commit_exists(commit):
        errors.append(f"certified_content_commit {commit} is not present in this repository")
    if artifact != f"phase-a-result-{commit}":
        errors.append("ci_artifact_name does not match certified_content_commit")

    certified_tree = record.get("certified_repository_tree_sha")
    if not isinstance(certified_tree, str) or _COMMIT.fullmatch(certified_tree) is None:
        errors.append("certified_repository_tree_sha is missing or invalid")
    elif (
        isinstance(commit, str) and _COMMIT.fullmatch(commit) is not None and _commit_exists(commit)
    ):
        if certified_tree != _git("rev-parse", f"{commit}^{{tree}}"):
            errors.append("certified repository tree does not match certified content commit")

    counts = record.get("counts")
    if not isinstance(counts, dict):
        errors.append("counts are missing")
    else:
        if counts.get("pass", 0) < 26:
            errors.append("certification records fewer than 26 passing Phase A tests")
        for key in ("fail", "skip", "xfail"):
            if counts.get(key) != 0:
                errors.append(f"certification count {key} is not zero")

    expected_requirements = sorted(mapping.get("requirements", {}))
    if record.get("blocking_requirements_mapped") != expected_requirements:
        errors.append("blocking requirement mapping does not match the current authority map")

    identity_digest = approval.get("document_sha256")
    if not isinstance(identity_digest, str) or _SHA256.fullmatch(identity_digest) is None:
        errors.append("approval record document_sha256 is invalid")
    elif record.get("identity_document_sha256") != identity_digest:
        errors.append("certification identity digest does not match the approval record")

    rules_digest = _sha256(RULES_PATH)
    oracle_digest = _sha256(ORACLE_PATH)
    if record.get("rules_source_sha256") != rules_digest:
        errors.append("certification rules source digest is stale")
    if record.get("oracle_source_sha256") != oracle_digest:
        errors.append("certification Oracle source digest is stale")
    if (
        record.get("pilot_lock") != "PASS"
        or (ROOT / ".github/workflows/pilot-simulation.yml").exists()
    ):
        errors.append("pilot lock is not active")
    if record.get("unsupported_behavior") != "HARD_VALIDATION_FAILURE":
        errors.append("unsupported behavior is not fail-closed")
    if record.get("golden_transcripts") != "PASS":
        errors.append("five digest-bound owner-approved golden transcripts are not certified")

    recorded_paths = record.get("covered_paths")
    certified_paths: dict[str, str] = {}
    if isinstance(commit, str) and _COMMIT.fullmatch(commit) is not None and _commit_exists(commit):
        try:
            certified_paths = all_digests_at_commit(commit)
        except (FileNotFoundError, subprocess.CalledProcessError) as error:
            errors.append(f"unable to reconstruct certified content: {error}")
        else:
            if recorded_paths != certified_paths:
                errors.append(
                    "certification provenance mismatch: covered_paths do not match "
                    "certified_content_commit"
                )
            elif record.get("covered_content_sha256") != aggregate_digest(certified_paths):
                errors.append("covered_content_sha256 does not match certified commit content")
    try:
        actual_paths = all_digests()
    except FileNotFoundError as error:
        errors.append(str(error))
        actual_paths = {}
    if recorded_paths != actual_paths:
        recorded_keys = set(recorded_paths) if isinstance(recorded_paths, dict) else set()
        actual_keys = set(actual_paths)
        missing = sorted(actual_keys - recorded_keys)
        extra = sorted(recorded_keys - actual_keys)
        changed = sorted(
            key
            for key in actual_keys & recorded_keys
            if isinstance(recorded_paths, dict) and recorded_paths.get(key) != actual_paths[key]
        )
        errors.append(
            f"certification is STALE: missing={missing}, extra={extra}, changed={changed}"
        )
    elif record.get("covered_content_sha256") != aggregate_digest(actual_paths):
        errors.append("covered_content_sha256 does not match covered_paths")

    candidate_record = RECORD_PATH.resolve() != TRACKED_RECORD_PATH.resolve()
    required_producer_steps = (
        ("Phase A production verifier", "Build CI certification candidate")
        if candidate_record
        else (
            "Phase A production verifier",
            "Build CI certification candidate",
            "Tests",
            "Manifest integrity",
        )
    )
    errors.extend(
        verify_github_actions_candidate(
            record,
            phase="phase-a",
            allow_unpublished_current_run=candidate_record,
            required_steps=required_producer_steps,
        )
    )

    if errors:
        print("Phase A certification check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        json.dumps(
            {
                "status": "PASS",
                "certified_content_commit": commit,
                "covered_content_sha256": record["covered_content_sha256"],
                "verification_environment": record["verification_environment"],
                "github_run_url": run_url,
                "counts": counts,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
