"""Executable tests for fail-closed verifier-result selection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mtg_verify.result_selection import select_verifier_result


def _write(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _common() -> dict[str, object]:
    return {
        "status": "PASS",
        "commit": "a" * 40,
        "counts": {"pass": 1, "fail": 0, "skip": 0, "xfail": 0},
        "artifact": "/tmp/result.json",
    }


def _phase_a() -> dict[str, object]:
    return {
        **_common(),
        "rules_source_sha256": "b" * 64,
        "oracle_source_sha256": "c" * 64,
        "pilot_lock": "PASS",
        "unsupported_capabilities": [],
    }


def _phase_b() -> dict[str, object]:
    return {
        **_common(),
        "mapping_complete": True,
        "golden_transcripts": "PASS",
        "pilot_lock": "PASS",
        "transcript_count": 12,
        "transcript_approval_document_sha256": "d" * 64,
        "unsupported_capability_count": 0,
        "strategic_model_blocker_count": 0,
    }


def test_selects_direct_phase_b_result_and_ignores_nested_phase_a(tmp_path: Path) -> None:
    selected = _write(tmp_path / "phase-b-run" / "result.json", _phase_b())
    _write(tmp_path / "phase-b-run" / "standing-phase-a" / "result.json", _phase_a())
    assert select_verifier_result(tmp_path, "phase-b") == selected


def test_rejects_nested_only_result(tmp_path: Path) -> None:
    _write(tmp_path / "phase-b-run" / "standing-phase-a" / "result.json", _phase_a())
    with pytest.raises(ValueError, match="exactly one direct phase-b"):
        select_verifier_result(tmp_path, "phase-b")


def test_rejects_duplicate_direct_results(tmp_path: Path) -> None:
    _write(tmp_path / "run-a" / "result.json", _phase_b())
    _write(tmp_path / "run-b" / "result.json", _phase_b())
    with pytest.raises(ValueError, match="found 2"):
        select_verifier_result(tmp_path, "phase-b")


def test_rejects_wrong_phase_payload(tmp_path: Path) -> None:
    _write(tmp_path / "run" / "result.json", _phase_a())
    with pytest.raises(ValueError, match="not a Phase B verifier result"):
        select_verifier_result(tmp_path, "phase-b")


def test_rejects_phase_b_result_with_open_blocker(tmp_path: Path) -> None:
    payload = _phase_b()
    payload["unsupported_capability_count"] = 1
    _write(tmp_path / "run" / "result.json", payload)
    with pytest.raises(ValueError, match="unsupported capabilities"):
        select_verifier_result(tmp_path, "phase-b")


def test_selects_valid_phase_a_result(tmp_path: Path) -> None:
    selected = _write(tmp_path / "phase-a-run" / "result.json", _phase_a())
    assert select_verifier_result(tmp_path, "phase-a") == selected
