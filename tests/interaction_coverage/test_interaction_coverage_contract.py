from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "scripts/build_interaction_coverage_manifest.py"
CANDIDATE_LOCK_CHECKER = ROOT / "scripts/check_interaction_candidate_lock.py"


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


def _purposes(record: dict[str, object]) -> set[str]:
    return {str(choice["purpose"]) for choice in record["choices"]}


def test_exact_deck_interaction_surface_is_finite_and_explicit(tmp_path: Path) -> None:
    manifest = _build(tmp_path)
    assert manifest["card_definition_count"] == 80
    assert manifest["physical_card_count"] == 100
    assert manifest["card_composition_record_count"] == 80
    assert manifest["global_rule_record_count"] == 10
    assert manifest["card_effect_record_count"] > 80
    assert manifest["record_count"] == (
        manifest["card_composition_record_count"]
        + manifest["card_effect_record_count"]
        + manifest["global_rule_record_count"]
    )

    records = manifest["records"]
    assert isinstance(records, list)
    ids = [record["record_id"] for record in records]
    assert len(ids) == len(set(ids))

    composition_records = [
        record for record in records if record["record_class"] == "CARD_COMPOSITION"
    ]
    assert len(composition_records) == 80
    assert len({record["card"]["name"] for record in composition_records}) == 80
    for record in composition_records:
        assert record["card"]["behavior_index"] == -1
        assert record["effect"]["kind"] == "ORACLE_COMPOSITION"
        assert record["authority"]["rules_refs"] == ["108.1"]

    card_records = [record for record in records if record["record_class"] == "CARD_EFFECT"]
    assert len({record["card"]["name"] for record in card_records}) == 80
    for record in card_records:
        assert record["card"]["composition_status"] == "REVIEWED_COMPOSITION"
        assert record["card"]["oracle_record_sha256"].startswith("sha256:")

    for record in records:
        assert record["status"] == "MAPPED"
        assert record["authority"]["rules_refs"]
        assert record["effect"]["parameters_sha256"].startswith("sha256:")
        assert record["legality"]["contract_sha256"].startswith("sha256:")
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


def test_global_choice_families_are_explicit(tmp_path: Path) -> None:
    manifest = _build(tmp_path)
    records = {record["record_id"]: record for record in manifest["records"]}
    expected = {
        "GLOBAL-TRIGGER-ORDERING": {"TRIGGER_ORDER"},
        "GLOBAL-REPLACEMENT-ORDERING": {"REPLACEMENT_EFFECT_SELECTION"},
        "GLOBAL-COST-PAYMENT": {
            "MANA_ABILITY_ACTIVATION_SEQUENCE",
            "MANA_PAYMENT_CONFIGURATION",
            "COST_PAYMENT_ORDER",
        },
        "GLOBAL-CLEANUP-REENTRY": {"CLEANUP_DISCARD_SELECTION"},
        "GLOBAL-COMBAT-ATTACKERS": {"ATTACKER_SELECTION", "ATTACK_DESTINATION_SELECTION"},
        "GLOBAL-SBA-TIMING": {"LEGEND_RULE_KEEP_SELECTION"},
        "GLOBAL-COMMANDER-GRAVEYARD-EXILE-RETURN": {"COMMANDER_RETURN_FROM_GRAVEYARD_OR_EXILE"},
        "GLOBAL-COMMANDER-HAND-LIBRARY-REPLACEMENT": {"COMMANDER_HAND_LIBRARY_REPLACEMENT"},
        "GLOBAL-PRIORITY-STACK-LIFO": {"PRIORITY_ACTION_OR_PASS"},
    }
    for record_id, purposes in expected.items():
        assert purposes <= _purposes(records[record_id])
    assert records["GLOBAL-ILLEGAL-ACTION-ROLLBACK"]["choices"] == []


def test_card_specific_cost_choices_are_not_hidden_defaults(tmp_path: Path) -> None:
    manifest = _build(tmp_path)
    card_records = [
        record for record in manifest["records"] if record["record_class"] == "CARD_EFFECT"
    ]

    scavenger = [record for record in card_records if record["card"]["name"] == "Scavenger Grounds"]
    assert any("SACRIFICE_PERMANENT_SELECTION" in _purposes(record) for record in scavenger)

    cascade = [record for record in card_records if record["card"]["name"] == "Cascade Bluffs"]
    assert any("HYBRID_COST_CONFIGURATION" in _purposes(record) for record in cascade)

    glint_horn = [
        record for record in card_records if record["card"]["name"] == "Glint-Horn Buccaneer"
    ]
    assert any("DISCARD_COST_CARD_IDENTITY" in _purposes(record) for record in glint_horn)


def test_target_controller_policy_uses_actual_actor_when_target_can_be_ours(tmp_path: Path) -> None:
    manifest = _build(tmp_path)
    arcane_denial = next(
        record
        for record in manifest["records"]
        if record["record_class"] == "CARD_EFFECT" and record["card"]["name"] == "Arcane Denial"
    )
    delayed_draw = next(
        choice
        for choice in arcane_denial["choices"]
        if choice["purpose"] == "DELAYED_TRIGGER_DRAW_COUNT"
    )
    assert delayed_draw["actor"] == "TARGET_CONTROLLER"
    assert delayed_draw["policy_class"] == "ACTOR_POLICY"


def test_proof_bundle_schema_binds_to_record_schema() -> None:
    record_schema = json.loads(
        (ROOT / "automation/interaction-record.schema.json").read_text(encoding="utf-8")
    )
    bundle_schema = json.loads(
        (ROOT / "automation/interaction-proof-bundle.schema.json").read_text(encoding="utf-8")
    )
    assert bundle_schema["properties"]["records"]["items"]["$ref"] == record_schema["$id"]


def test_provisional_interaction_candidate_lock_is_current_and_not_frozen() -> None:
    candidate = subprocess.run(
        [sys.executable, str(CANDIDATE_LOCK_CHECKER)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert candidate.returncode == 0, candidate.stdout + candidate.stderr
    report = json.loads(candidate.stdout)
    assert report["status"] == "PASS"
    assert report["lock_status"] == "PROVISIONAL_PENDING_AGENT_A_INTEGRATION"

    legacy_frozen = subprocess.run(
        [sys.executable, str(BUILDER), "--check-lock"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert legacy_frozen.returncode != 0
