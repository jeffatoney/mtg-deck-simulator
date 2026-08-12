from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

import mtg_runs.phase_c as phase_c

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import _phase_b_paths  # noqa: E402

CONFIG_PATH = "docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json"
GUARDRAIL_PATH = "docs/spec/phase-c/NO_OPPONENT_POLICY_GUARDRAIL.json"
HANDOFF_PROTOCOL = ROOT / "docs/audit/handoff/PROTOCOL.md"
PILOT_WORKFLOW = ROOT / ".github/workflows/phase-c-pilot.yml"
PHASE_C_SOURCE = ROOT / "src/mtg_runs/phase_c.py"


def test_phase_b_certification_surface_is_disjoint_from_activation_allowlist() -> None:
    assert set(_phase_b_paths.COVERED_PATHS).isdisjoint(phase_c._ACTIVATION_ALLOWLIST)
    assert CONFIG_PATH in phase_c._ACTIVATION_ALLOWLIST
    assert CONFIG_PATH not in _phase_b_paths.COVERED_PATHS
    assert GUARDRAIL_PATH in _phase_b_paths.COVERED_PATHS


def test_pilot_workflow_checks_phase_b_before_authorization_without_deadlock() -> None:
    text = PILOT_WORKFLOW.read_text(encoding="utf-8")
    assert text.index("Durable Phase B certification") < text.index(
        "Validate implementation and governance-only activation"
    )
    assert set(_phase_b_paths.COVERED_PATHS).isdisjoint(phase_c._ACTIVATION_ALLOWLIST)


def test_locked_config_digest_is_read_from_implementation_commit() -> None:
    text = PHASE_C_SOURCE.read_text(encoding="utf-8")
    locked_read = "locked_config_sha = _git_file_sha256(root, implementation_commit, config_path)"
    activation_read = "locked_config_sha = _git_file_sha256(root, activation_commit, config_path)"
    assert locked_read in text
    assert activation_read not in text
    assert "if locked_config_sha != expected_locked_config_sha256:" in text


def test_activation_config_mutation_does_not_stale_phase_b_surface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for relative in (CONFIG_PATH, GUARDRAIL_PATH):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    monkeypatch.setattr(_phase_b_paths, "ROOT", tmp_path)
    monkeypatch.setattr(_phase_b_paths, "COVERED_PATHS", (GUARDRAIL_PATH,))
    before_surface = _phase_b_paths.all_digests()
    config_path = tmp_path / CONFIG_PATH
    before_config_sha = hashlib.sha256(config_path.read_bytes()).hexdigest()

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    authorization = payload["authorization"]
    assert isinstance(authorization, dict)
    authorization.update(
        {
            "execution_allowed": True,
            "status": "AUTHORIZED",
            "approved_by": "Jeff Toney",
            "approved_at": "2026-08-12T00:00:00Z",
        }
    )
    config_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    after_config_sha = hashlib.sha256(config_path.read_bytes()).hexdigest()
    after_surface = _phase_b_paths.all_digests()
    assert after_config_sha != before_config_sha
    assert after_surface == before_surface


def test_no_opponent_guardrail_mutation_changes_phase_b_certification_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = ROOT / GUARDRAIL_PATH
    target = tmp_path / GUARDRAIL_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    monkeypatch.setattr(_phase_b_paths, "ROOT", tmp_path)
    monkeypatch.setattr(_phase_b_paths, "COVERED_PATHS", (GUARDRAIL_PATH,))
    before_paths = _phase_b_paths.all_digests()
    before_aggregate = _phase_b_paths.aggregate_digest(before_paths)
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    after_paths = _phase_b_paths.all_digests()
    after_aggregate = _phase_b_paths.aggregate_digest(after_paths)
    assert after_paths[GUARDRAIL_PATH] != before_paths[GUARDRAIL_PATH]
    assert after_aggregate != before_aggregate


def test_handoff_protocol_requires_machine_state_reconciliation() -> None:
    text = " ".join(HANDOFF_PROTOCOL.read_text(encoding="utf-8").split())
    assert "## Machine-state reconciliation checklist" in text
    for required in (
        "PR merged",
        "Exact `main` identified",
        "CI green",
        "Certification current",
        "Handoff current",
        "Diagnostic completed",
        "Audit completed",
        "Report created",
        "Owner package ready",
        "byte count greater than zero",
        "workflow run ID and head SHA",
    ):
        assert required in text
