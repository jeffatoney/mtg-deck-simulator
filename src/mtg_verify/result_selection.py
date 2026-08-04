"""Fail-closed selection of phase verifier results from CI artifact trees."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COUNT_KEYS = ("pass", "fail", "skip", "xfail")


def _read_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"verifier result is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("verifier result must be a JSON object")
    return payload


def _validate_digest(payload: Mapping[str, Any], key: str) -> None:
    if _SHA256.fullmatch(str(payload.get(key, ""))) is None:
        raise ValueError(f"verifier result has an invalid {key}")


def _validate_common(payload: Mapping[str, Any]) -> None:
    if payload.get("status") != "PASS":
        raise ValueError("verifier result is not a passing result")
    commit = str(payload.get("commit", ""))
    if _COMMIT_SHA.fullmatch(commit) is None:
        raise ValueError("verifier result omits a full lowercase commit SHA")
    counts = payload.get("counts")
    if not isinstance(counts, Mapping) or any(key not in counts for key in _COUNT_KEYS):
        raise ValueError("verifier result has incomplete test counts")
    if any(not isinstance(counts[key], int) or int(counts[key]) < 0 for key in _COUNT_KEYS):
        raise ValueError("verifier result test counts must be nonnegative integers")
    if int(counts["pass"]) < 1 or any(int(counts[key]) for key in ("fail", "skip", "xfail")):
        raise ValueError("verifier result contains failed or excluded tests")
    if not str(payload.get("run_id", "")):
        raise ValueError("verifier result omits its run ID")
    if payload.get("evidence_classification") != "CLEAN_ENGINE_PRODUCTION_PATH":
        raise ValueError("verifier result has the wrong evidence classification")
    if payload.get("legacy_evidence_used") is not False:
        raise ValueError("verifier result used legacy evidence")


def _validate_phase_a(payload: Mapping[str, Any]) -> None:
    required = {
        "architecture_boundary",
        "authority_map",
        "branch",
        "golden_transcripts",
        "mapping",
        "oracle_source_sha256",
        "pilot_lock",
        "replay_and_hash",
        "rules_source_sha256",
        "schema_version",
        "unsupported_behavior",
        "unsupported_capabilities",
    }
    missing = sorted(required.difference(payload))
    if missing:
        raise ValueError(f"result is not a Phase A verifier result; missing {missing}")
    if payload.get("schema_version") != "phase-a-result-v2":
        raise ValueError("result has the wrong Phase A schema version")
    for key in (
        "architecture_boundary",
        "authority_map",
        "golden_transcripts",
        "mapping",
        "pilot_lock",
        "replay_and_hash",
    ):
        if payload.get(key) != "PASS":
            raise ValueError(f"Phase A verifier result has a failed {key} gate")
    if payload.get("unsupported_behavior") != "HARD_VALIDATION_FAILURE":
        raise ValueError("Phase A verifier result does not fail closed")
    if not isinstance(payload.get("unsupported_capabilities"), list):
        raise ValueError("Phase A verifier result has malformed unsupported capabilities")
    _validate_digest(payload, "rules_source_sha256")
    _validate_digest(payload, "oracle_source_sha256")


def _validate_phase_b(payload: Mapping[str, Any]) -> None:
    required = {
        "decklist_sha256",
        "evaluator_snapshot_id",
        "evaluator_snapshot_sha256",
        "golden_transcripts",
        "learning_plan_sha256",
        "mapping_complete",
        "oracle_source_sha256",
        "pilot_lock",
        "rules_source_sha256",
        "schema_version",
        "strategic_evaluator",
        "strategic_model_blockers",
        "transcript_count",
        "transcript_approval_document_sha256",
        "unsupported_capabilities",
    }
    missing = sorted(required.difference(payload))
    if missing:
        raise ValueError(f"result is not a Phase B verifier result; missing {missing}")
    if payload.get("schema_version") != "phase-b-result-v2":
        raise ValueError("result has the wrong Phase B schema version")
    if payload.get("mapping_complete") is not True:
        raise ValueError("Phase B verifier result does not have complete mapping")
    if payload.get("golden_transcripts") != "PASS" or payload.get("pilot_lock") != "PASS":
        raise ValueError("Phase B verifier result has a failed transcript or pilot-lock gate")
    if payload.get("strategic_evaluator") != "PASS":
        raise ValueError("Phase B verifier result has a failed strategic evaluator")
    if payload.get("transcript_count") != 12:
        raise ValueError("Phase B verifier result does not contain twelve approved transcripts")
    for key in (
        "decklist_sha256",
        "evaluator_snapshot_sha256",
        "learning_plan_sha256",
        "oracle_source_sha256",
        "rules_source_sha256",
        "transcript_approval_document_sha256",
    ):
        _validate_digest(payload, key)
    if not str(payload.get("evaluator_snapshot_id", "")):
        raise ValueError("Phase B verifier result omits its evaluator identity")
    unsupported = payload.get("unsupported_capabilities")
    if not isinstance(unsupported, list) or unsupported:
        raise ValueError("Phase B verifier result contains unsupported capabilities")
    strategic = payload.get("strategic_model_blockers")
    if not isinstance(strategic, list) or strategic:
        raise ValueError("Phase B verifier result contains strategic-model blockers")


def select_verifier_result(root: Path, phase: str) -> Path:
    """Return the one direct verifier result whose payload matches the requested phase.

    A verifier writes ``<artifact-root>/<run-id>/result.json``. Nested standing-verifier
    evidence is intentionally ignored. Missing or duplicate direct results fail closed.
    """

    if phase not in {"phase-a", "phase-b"}:
        raise ValueError(f"unsupported verifier phase: {phase}")
    if not root.is_dir():
        raise ValueError(f"verifier artifact root is not a directory: {root}")
    candidates = sorted(path for path in root.glob("*/result.json") if path.is_file())
    if len(candidates) != 1:
        raise ValueError(
            f"expected exactly one direct {phase} verifier result under {root}; "
            f"found {len(candidates)}"
        )
    selected = candidates[0]
    payload = _read_payload(selected)
    _validate_common(payload)
    if phase == "phase-a":
        _validate_phase_a(payload)
    else:
        _validate_phase_b(payload)
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=("phase-a", "phase-b"))
    parser.add_argument("--root", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        selected = select_verifier_result(arguments.root, arguments.phase)
    except ValueError as exc:
        parser.error(str(exc))
    print(selected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
