"""Negative tests for the durable Phase A certification gate."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _phase_a_paths import COVERED_PATHS  # noqa: E402

RECORD = "docs/audit/phase-a-certification/CERTIFICATION.json"
EXTRA_PATHS = (
    "docs/spec/identity/IDENTITY_MODEL_V2.0.0_APPROVAL_RECORD.json",
    "docs/source/MagicCompRules_2026-06-19.txt",
)


def _copy(relative: str, destination: Path) -> None:
    source = ROOT / relative
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True)
    else:
        shutil.copy2(source, target)


def _run(cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(cwd / "scripts/check_phase_a_certification.py")],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _record_source() -> Path:
    candidate = os.environ.get("PHASE_A_CERTIFICATION_RECORD", "").strip()
    return Path(candidate) if candidate else ROOT / RECORD


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    record_source = _record_source()
    if not record_source.is_file():
        pytest.skip("no durable certification or CI candidate is available")
    for relative in (*COVERED_PATHS, *EXTRA_PATHS):
        _copy(relative, tmp_path)
    record_target = tmp_path / RECORD
    record_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(record_source, record_target)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base"],
        cwd=tmp_path,
        check=True,
    )
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    record = json.loads(record_target.read_text(encoding="utf-8"))
    record["certified_content_commit"] = head
    record["ci_artifact_name"] = f"phase-a-result-{head}"
    record_target.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return tmp_path


def _patch_record(sandbox: Path, **changes: object) -> None:
    path = sandbox / RECORD
    record = json.loads(path.read_text(encoding="utf-8"))
    record.update(changes)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_current_certification_passes(sandbox: Path) -> None:
    result = _run(sandbox)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "relative",
    [
        "src/mtg_kernel/errors.py",
        "tests/phase_a/test_kernel_acceptance.py",
        "scripts/check_phase_a_certification.py",
        ".github/workflows/ci.yml",
        "automation/phase-a-test-mapping.json",
        "docs/audit/phase-a-golden-transcripts/APPROVALS.json",
        "scripts/check_phase_a_golden_transcripts.py",
    ],
)
def test_covered_change_is_rejected(sandbox: Path, relative: str) -> None:
    target = sandbox / relative
    if target.suffix == ".json":
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["certification_test_drift"] = True
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        target.write_text(target.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
    result = _run(sandbox)
    assert result.returncode == 1
    assert "STALE" in result.stdout


def test_renamed_engine_file_is_rejected(sandbox: Path) -> None:
    source = sandbox / "src/mtg_kernel/errors.py"
    source.rename(source.with_name("errors_renamed.py"))
    result = _run(sandbox)
    assert result.returncode == 1
    assert "STALE" in result.stdout


def test_missing_record_is_rejected(sandbox: Path) -> None:
    (sandbox / RECORD).unlink()
    result = _run(sandbox)
    assert result.returncode == 1
    assert "no durable certification" in result.stderr


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"status": "FAIL"}, "not PASS"),
        ({"legacy_evidence_used": True}, "legacy_evidence_used"),
        ({"evidence_classification": "SOURCE_VALIDATION_ONLY"}, "CLEAN_ENGINE"),
        ({"schema_version": "phase-a-certification-v99"}, "unexpected certification schema"),
        ({"verification_environment": "LOCAL_REPRODUCTION"}, "GITHUB_ACTIONS"),
        ({"github_run_id": None}, "github_run_id"),
        ({"ci_artifact_name": "forged"}, "ci_artifact_name"),
        ({"pilot_lock": "FAIL"}, "pilot lock"),
        ({"golden_transcripts": "FAIL"}, "golden transcripts"),
    ],
)
def test_forged_record_is_rejected(sandbox: Path, changes: dict[str, object], message: str) -> None:
    _patch_record(sandbox, **changes)
    result = _run(sandbox)
    assert result.returncode == 1
    assert message in result.stdout
