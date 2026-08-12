from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import _phase_b_paths  # noqa: E402


GOVERNANCE_PATHS = (
    "docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json",
    "docs/spec/phase-c/NO_OPPONENT_POLICY_GUARDRAIL.json",
)
HANDOFF_PROTOCOL = ROOT / "docs/audit/handoff/PROTOCOL.md"


def test_phase_c_governance_inputs_are_on_phase_b_certification_surface() -> None:
    assert set(GOVERNANCE_PATHS).issubset(_phase_b_paths.COVERED_PATHS)


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


@pytest.mark.parametrize("relative", GOVERNANCE_PATHS)
def test_governance_mutation_changes_certification_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
) -> None:
    for source_relative in GOVERNANCE_PATHS:
        source = ROOT / source_relative
        target = tmp_path / source_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    monkeypatch.setattr(_phase_b_paths, "ROOT", tmp_path)
    monkeypatch.setattr(_phase_b_paths, "COVERED_PATHS", GOVERNANCE_PATHS)
    before_paths = _phase_b_paths.all_digests()
    before_aggregate = _phase_b_paths.aggregate_digest(before_paths)

    target = tmp_path / relative
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    after_paths = _phase_b_paths.all_digests()
    after_aggregate = _phase_b_paths.aggregate_digest(after_paths)
    assert after_paths[relative] != before_paths[relative]
    assert after_aggregate != before_aggregate
