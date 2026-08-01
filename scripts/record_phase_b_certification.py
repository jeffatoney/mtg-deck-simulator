#!/usr/bin/env python3
"""Create a CI-only durable Phase B certification candidate from a PASS verifier."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _phase_b_paths import aggregate_digest, all_digests  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TRACKED = ROOT / "docs/audit/phase-b-certification/CERTIFICATION.json"


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("verifier result must be an object")
    return value


def build_record(verifier: dict[str, Any]) -> dict[str, Any]:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError(
            "Phase B certification candidates may only be produced in GitHub Actions"
        )
    required = {
        name: os.environ.get(name, "").strip()
        for name in ("GITHUB_RUN_ID", "GITHUB_SERVER_URL", "GITHUB_REPOSITORY")
    }
    if any(not value for value in required.values()):
        raise RuntimeError("GitHub Actions evidence environment is incomplete")
    head = _git("rev-parse", "HEAD")
    if verifier.get("commit") != head or verifier.get("status") != "PASS":
        raise RuntimeError("verifier did not PASS the checked-out head")
    if (
        verifier.get("github_actions") is not True
        or str(verifier.get("github_run_id")) != required["GITHUB_RUN_ID"]
    ):
        raise RuntimeError("verifier did not run in this GitHub Actions job")
    if verifier.get("clean_tree_before_run") is not True:
        raise RuntimeError("verifier did not begin from a clean tree")
    if (
        verifier.get("evidence_classification") != "CLEAN_ENGINE_PRODUCTION_PATH"
        or verifier.get("legacy_evidence_used") is not False
    ):
        raise RuntimeError("verifier evidence classification is unacceptable")
    if verifier.get("golden_transcripts") != "PASS" or verifier.get("transcript_count") != 12:
        raise RuntimeError("twelve owner-approved transcripts did not pass")
    if verifier.get("pilot_lock") != "PASS" or verifier.get("unsupported_capabilities"):
        raise RuntimeError("pilot lock or unsupported exact-deck capabilities block certification")
    counts = verifier.get("counts")
    if (
        not isinstance(counts, dict)
        or counts.get("pass", 0) < 1
        or any(counts.get(key) != 0 for key in ("fail", "skip", "xfail"))
    ):
        raise RuntimeError("verifier test counts are not fully passing")
    paths = all_digests()
    run_id = required["GITHUB_RUN_ID"]
    return {
        "schema_version": "phase-b-certification-v1",
        "status": "PASS",
        "certified_content_commit": head,
        "certified_repository_tree_sha": _git("rev-parse", "HEAD^{tree}"),
        "covered_paths": paths,
        "covered_content_sha256": aggregate_digest(paths),
        "verification_environment": "GITHUB_ACTIONS",
        "github_run_id": run_id,
        "github_run_url": f"{required['GITHUB_SERVER_URL']}/{required['GITHUB_REPOSITORY']}/actions/runs/{run_id}",
        "ci_artifact_name": f"phase-b-result-{head}",
        "verifier_run_id": verifier["run_id"],
        "counts": counts,
        "clean_tree_before_run": True,
        "evidence_classification": "CLEAN_ENGINE_PRODUCTION_PATH",
        "legacy_evidence_used": False,
        "blocking_requirements_mapped": sorted(verifier["blocking_requirement_tests"]),
        "golden_transcripts": "PASS",
        "transcript_count": 12,
        "transcript_approval_document_sha256": verifier["transcript_approval_document_sha256"],
        "pilot_lock": "PASS",
        "unsupported_capabilities": [],
        "note": "Renew whenever any Phase B covered path changes.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verifier-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = args.output.resolve()
        if output == TRACKED.resolve() or ROOT.resolve() in output.parents:
            raise RuntimeError("CI candidate output must be outside the repository tree")
        record = build_record(_json(args.verifier_result))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "output": str(output),
                "certified_content_commit": record["certified_content_commit"],
                "covered_content_sha256": record["covered_content_sha256"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
