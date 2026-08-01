"""Phase B verifier, mapping, certification, and pilot-lock contracts."""

from __future__ import annotations

import json
from pathlib import Path

from mtg_verify.phase_b import exact_deck_execution_blockers

ROOT = Path(__file__).resolve().parents[2]


def test_phase_b_mapping_has_no_slice_placeholders_and_covers_all_blockers() -> None:
    authority = json.loads((ROOT / "automation/phase-b-authority-map.json").read_text())
    mapping = json.loads((ROOT / "automation/phase-b-test-mapping.json").read_text())
    assert set(mapping["requirements"]) == set(authority["blocking_requirement_ids"])
    assert not any(
        "PENDING_SLICE" in node for nodes in mapping["requirements"].values() for node in nodes
    )


def test_verifier_and_durable_certification_fail_closed_on_real_blockers() -> None:
    cli = (ROOT / "src/mtg_kernel/cli.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "verify-phase-b" in cli
    assert "Phase B candidate verifier" in workflow
    assert "Build Phase B certification candidate" in workflow
    assert "Durable Phase B certification is current" in workflow
    assert "pilot-simulation.yml" not in workflow
    blockers = exact_deck_execution_blockers()
    assert blockers
    assert any(value.startswith("UNVERIFIED_CARD:") for value in blockers)
    assert not (ROOT / "docs/audit/phase-b-certification/CERTIFICATION.json").exists()
