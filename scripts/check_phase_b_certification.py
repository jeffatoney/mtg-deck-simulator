#!/usr/bin/env python3
"""Require an exact-content durable Phase B certification record."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _phase_b_paths import aggregate_digest, all_digests  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs/audit/phase-b-certification/CERTIFICATION.json"


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
    if not isinstance(counts, dict) or any(counts.get(key) != 0 for key in ("fail", "skip", "xfail")):
        errors.append("certification contains failures, skips, or xfails")
    actual = all_digests()
    if record.get("covered_paths") != actual:
        errors.append("certification is STALE for the Phase B covered surface")
    elif record.get("covered_content_sha256") != aggregate_digest(actual):
        errors.append("covered_content_sha256 does not match covered_paths")
    commit = str(record.get("certified_content_commit", ""))
    if len(commit) != 40:
        errors.append("certified content commit is invalid")
    run_id = str(record.get("github_run_id", ""))
    run_url = str(record.get("github_run_url", ""))
    if not run_id or not run_url.endswith(f"/actions/runs/{run_id}"):
        errors.append("GitHub Actions run evidence is incomplete")
    try:
        if commit and subprocess.check_output(["git", "cat-file", "-t", commit], cwd=ROOT, text=True).strip() != "commit":
            errors.append("certified content commit is unavailable")
    except subprocess.CalledProcessError:
        errors.append("certified content commit is unavailable")
    if errors:
        print("Phase B certification check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(json.dumps({
        "status": "PASS",
        "certified_content_commit": commit,
        "covered_content_sha256": record["covered_content_sha256"],
        "github_run_url": run_url,
        "counts": counts,
        "transcript_count": record["transcript_count"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
