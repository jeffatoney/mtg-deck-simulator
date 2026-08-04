"""Fail-closed selection of phase verifier results from CI artifact trees."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_COUNT_KEYS = ("pass", "fail", "skip", "xfail")


def _read_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"verifier result is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("verifier result must be a JSON object")
    return payload


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


def _validate_phase_a(payload: Mapping[str, Any]) -> None:
    required = {
        "artifact",
        "rules_source_sha256",
        "oracle_source_sha256",
        "pilot_lock",
        "unsupported_capabilities",
    }
    missing = sorted(required.difference(payload))
    if missing:
        raise ValueError(f"result is not a Phase A verifier result; missing {missing}")
    if payload.get("pilot_lock") != "PASS" or not isinstance(
        payload.get("unsupported_capabilities"), list
    ):
        raise ValueError("Phase A verifier result has invalid control fields")


def _validate_phase_b(payload: Mapping[str, Any]) -> None:
    required = {
        "artifact",
        "mapping_complete",
        "golden_transcripts",
        "pilot_lock",
        "transcript_count",
        "transcript_approval_document_sha256",
        "unsupported_capability_count",
        "strategic_model_blocker_count",
    }
    missing = sorted(required.difference(payload))
    if missing:
        raise ValueError(f"result is not a Phase B verifier result; missing {missing}")
    if payload.get("mapping_complete") is not True:
        raise ValueError("Phase B verifier result does not have complete mapping")
    if payload.get("golden_transcripts") != "PASS" or payload.get("pilot_lock") != "PASS":
        raise ValueError("Phase B verifier result has a failed transcript or pilot-lock gate")
    if payload.get("transcript_count") != 12:
        raise ValueError("Phase B verifier result does not contain twelve approved transcripts")
    digest = str(payload.get("transcript_approval_document_sha256", ""))
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("Phase B verifier result has an invalid approval-document digest")
    if payload.get("unsupported_capability_count") != 0:
        raise ValueError("Phase B verifier result contains unsupported capabilities")
    if payload.get("strategic_model_blocker_count") != 0:
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
