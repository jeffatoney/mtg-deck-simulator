from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "scripts/build_interaction_coverage_manifest.py"


def _build(tmp_path: Path) -> dict[str, object]:
    output = tmp_path / "interaction-surface.json"
    result = subprocess.run(
        [sys.executable, str(BUILDER), "--output", str(output)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(output.read_text(encoding="utf-8"))


def test_exact_deck_interaction_surface_is_finite_and_explicit(tmp_path: Path) -> None:
    manifest = _build(tmp_path)
    assert manifest["card_definition_count"] == 80
    assert manifest["physical_card_count"] == 100
    assert manifest["global_rule_record_count"] == 7
    assert manifest["card_effect_record_count"] > 80
    assert manifest["record_count"] == (
        manifest["card_effect_record_count"] + manifest["global_rule_record_count"]
    )

    records = manifest["records"]
    assert isinstance(records, list)
    ids = [record["record_id"] for record in records]
    assert len(ids) == len(set(ids))

    card_names = {
        record["card"]["name"]
        for record in records
        if record["record_class"] == "CARD_EFFECT"
    }
    assert len(card_names) == 80

    for record in records:
        assert record["status"] == "MAPPED"
        assert record["authority"]["rules_refs"]
        assert record["effect"]["parameters_sha256"].startswith("sha256:")
        for choice in record["choices"]:
            assert choice["purpose"]
            assert choice["rules_refs"]
            assert choice["replay_required"] is True


def test_unknown_effect_kinds_fail_closed(tmp_path: Path) -> None:
    manifest = _build(tmp_path)
    declared = json.loads(
        (ROOT / "automation/interaction-choice-contracts.json").read_text(encoding="utf-8")
    )["effect_contracts"]
    assert set(manifest["observed_effect_kinds"]) == set(declared)


def test_frozen_interaction_surface_lock_is_current() -> None:
    result = subprocess.run(
        [sys.executable, str(BUILDER), "--check-lock"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
