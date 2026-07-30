#!/usr/bin/env python3
"""Create a CI-produced candidate for the durable Phase A certification record."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _phase_a_paths import aggregate_digest, all_digests  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
APPROVAL_PATH = ROOT / "docs/spec/identity/IDENTITY_MODEL_V2.0.0_APPROVAL_RECORD.json"
TRACKED_RECORD = ROOT / "docs/audit/phase-a-certification/CERTIFICATION.json"


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _require_ci_environment() -> tuple[str, str, str]:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError(
            "durable certification candidates may only be produced in GitHub Actions"
        )
    required = {
        name: os.environ.get(name, "").strip()
        for name in ("GITHUB_RUN_ID", "GITHUB_SERVER_URL", "GITHUB_REPOSITORY")
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"missing GitHub Actions environment values: {missing}")
    return (
        required["GITHUB_RUN_ID"],
        required["GITHUB_SERVER_URL"],
        required["GITHUB_REPOSITORY"],
    )


def build_record(verifier: dict[str, Any]) -> dict[str, Any]:
    run_id, server, repository = _require_ci_environment()
    head = _git("rev-parse", "HEAD")
    if verifier.get("commit") != head:
        raise RuntimeError("verifier result does not certify checked-out HEAD")
    if verifier.get("github_actions") is not True or str(verifier.get("github_run_id")) != run_id:
        raise RuntimeError("verifier result is not from this GitHub Actions run")
    if verifier.get("status") != "PASS" or verifier.get("clean_tree_before_run") is not True:
        raise RuntimeError("refusing to record a failing or dirty verification run")
    if verifier.get("evidence_classification") != "CLEAN_ENGINE_PRODUCTION_PATH":
        raise RuntimeError("verifier evidence classification is not acceptable")
    if verifier.get("legacy_evidence_used") is not False:
        raise RuntimeError("verifier used legacy evidence")
    counts = verifier.get("counts")
    if not isinstance(counts, dict) or counts.get("pass", 0) < 22:
        raise RuntimeError("verifier did not record at least 22 passing Phase A tests")
    if any(counts.get(key) != 0 for key in ("fail", "skip", "xfail")):
        raise RuntimeError("verifier recorded a failure, skip, or xfail")

    covered_paths = all_digests()
    approval = _json_object(APPROVAL_PATH)
    return {
        "schema_version": "phase-a-certification-v2",
        "status": "PASS",
        "certified_content_commit": head,
        "certified_repository_tree_sha": _git("rev-parse", "HEAD^{tree}"),
        "covered_paths": covered_paths,
        "covered_content_sha256": aggregate_digest(covered_paths),
        "verification_environment": "GITHUB_ACTIONS",
        "github_run_id": run_id,
        "github_run_url": f"{server}/{repository}/actions/runs/{run_id}",
        "ci_artifact_name": f"phase-a-result-{head}",
        "verifier_run_id": verifier["run_id"],
        "counts": counts,
        "clean_tree_before_run": True,
        "evidence_classification": verifier["evidence_classification"],
        "legacy_evidence_used": False,
        "blocking_requirements_mapped": sorted(verifier["blocking_requirement_tests"]),
        "identity_document_sha256": approval["document_sha256"],
        "rules_source_sha256": verifier["rules_source_sha256"],
        "oracle_source_sha256": verifier["oracle_source_sha256"],
        "unsupported_capabilities": verifier["unsupported_capabilities"],
        "unsupported_behavior": verifier["unsupported_behavior"],
        "pilot_lock": verifier["pilot_lock"],
        "note": (
            "Renew this CI-produced record whenever any covered path changes. "
            "scripts/check_phase_a_certification.py enforces exact content digests."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verifier-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = args.output.resolve()
        try:
            output.relative_to(ROOT.resolve())
        except ValueError:
            pass
        else:
            if output == TRACKED_RECORD.resolve() or ROOT.resolve() in output.parents:
                raise RuntimeError("CI candidate output must be outside the repository tree")
        verifier = _json_object(args.verifier_result)
        record = build_record(verifier)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, RuntimeError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": record["status"],
                "output": str(output),
                "certified_content_commit": record["certified_content_commit"],
                "covered_content_sha256": record["covered_content_sha256"],
                "github_run_url": record["github_run_url"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
