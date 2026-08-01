from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_phase_a_certification_and_verifier_are_standing() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "Phase A production verifier" in workflow
    assert "Durable Phase A certification is current" in workflow
    assert "github.head_ref == 'engine/phase-a-rules-kernel'" not in workflow
    record = json.loads(
        (ROOT / "docs/audit/phase-a-certification/CERTIFICATION.json").read_text(encoding="utf-8")
    )
    assert record["status"] == "PASS"
    assert record["verification_environment"] == "GITHUB_ACTIONS"
    assert record["legacy_evidence_used"] is False
    assert record["counts"] == {"pass": 22, "fail": 0, "skip": 0, "xfail": 0}
