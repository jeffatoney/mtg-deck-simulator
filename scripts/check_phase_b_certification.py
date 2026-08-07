#!/usr/bin/env python3
"""Require an exact-content durable Phase B certification record."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _certification_provenance import verify_github_actions_candidate  # noqa: E402
from _phase_b_paths import aggregate_digest, all_digests, all_digests_at_commit  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TRACKED_RECORD = ROOT / "docs/audit/phase-b-certification/CERTIFICATION.json"
_configured_record = os.environ.get("PHASE_B_CERTIFICATION_RECORD", "").strip()
RECORD = Path(_configured_record) if _configured_record else TRACKED_RECORD
if not RECORD.is_absolute():
    RECORD = ROOT / RECORD


def main() -> int:
    errors: list[str] = []
    if not RECORD.is_file():
        print("Phase B certification check failed:\n- durable certification record is missing")
        return 1
    try:
        record: dict[str, Any] = json.loads(RECORD.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Phase B certification check failed:\n- {exc}")
        return 1
    if record.get("schema_version") != "phase-b-certification-v1" or record.get("status") != "PASS":
        errors.append("record schema/status is not a passing Phase B certification")
    if record.get("verification_environment") != "GITHUB_ACTIONS":
        errors.append("certification was not produced in GitHub Actions")
    if record.get("legacy_evidence_used") is not False:
        errors.append("certification used prohibited legacy evidence")
    if record.get("golden_transcripts") != "PASS" or record.get("transcript_count") != 12:
        errors.append("certification does not bind twelve approved executed transcripts")
    if record.get("pilot_lock") != "PASS":
        errors.append("certification does not preserve pilot/full-study locks")
    counts = record.get("counts", {})
    if not isinstance(counts, dict) or any(
        counts.get(key) != 0 for key in ("fail", "skip", "xfail")
    ):
        errors.append("certification contains failures, skips, or xfails")
    commit = str(record.get("certified_content_commit", ""))
    commit_available = False
    if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        errors.append("certified content commit is invalid")
    else:
        try:
            commit_available = (
                subprocess.check_output(["git", "cat-file", "-t", commit], cwd=ROOT, text=True).strip()
                == "commit"
            )
        except subprocess.CalledProcessError:
            commit_available = False
        if not commit_available:
            errors.append("certified content commit is unavailable")

    certified_tree = str(record.get("certified_repository_tree_sha", ""))
    if len(certified_tree) != 40 or any(
        char not in "0123456789abcdef" for char in certified_tree
    ):
        errors.append("certified repository tree is invalid")
    elif commit_available:
        actual_tree = subprocess.check_output(
            ["git", "rev-parse", f"{commit}^{{tree}}"], cwd=ROOT, text=True
        ).strip()
        if certified_tree != actual_tree:
            errors.append("certified repository tree does not match certified content commit")

    recorded_paths = record.get("covered_paths")
    if commit_available:
        try:
            certified_paths = all_digests_at_commit(commit)
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            errors.append(f"unable to reconstruct certified content: {exc}")
        else:
            if recorded_paths != certified_paths:
                errors.append(
                    "certification provenance mismatch: covered_paths do not match "
                    "certified_content_commit"
                )
            elif record.get("covered_content_sha256") != aggregate_digest(certified_paths):
                errors.append("covered_content_sha256 does not match certified commit content")

    actual = all_digests()
    if recorded_paths != actual:
        errors.append("certification is STALE for the Phase B covered surface")
    elif record.get("covered_content_sha256") != aggregate_digest(actual):
        errors.append("covered_content_sha256 does not match covered_paths")

    run_id = str(record.get("github_run_id", ""))
    run_url = str(record.get("github_run_url", ""))
    if not run_id or not run_url.endswith(f"/actions/runs/{run_id}"):
        errors.append("GitHub Actions run evidence is incomplete")
    if record.get("ci_artifact_name") != f"phase-b-result-{commit}":
        errors.append("ci_artifact_name does not match certified_content_commit")
    candidate_record = RECORD.resolve() != TRACKED_RECORD.resolve()
    errors.extend(
        verify_github_actions_candidate(
            record,
            phase="phase-b",
            allow_unpublished_current_run=candidate_record,
            required_steps=(
                "Tests",
                "Manifest integrity",
                "Phase B verifier",
                "Build Phase B certification candidate",
            ),
        )
    )
    if errors:
        print("Phase B certification check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "certified_content_commit": commit,
                "covered_content_sha256": record["covered_content_sha256"],
                "github_run_url": run_url,
                "counts": counts,
                "transcript_count": record["transcript_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
