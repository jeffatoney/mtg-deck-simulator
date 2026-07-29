"""Source-validation tests for the committed offline Scryfall snapshot.

SOURCE_VALIDATION_ONLY. These assert that the frozen deck, snapshot, and behavior
registry files agree with each other and with their recorded hashes. They make no
claim about rules behavior.

The legacy behavior-primitive assertions that used to live here moved to
legacy/tests/test_legacy_behavior_primitives.py: they exercised `mtg_sim.behaviors`,
which is quarantined rules logic and is PROHIBITED_AS_PHASE_A_EVIDENCE.
"""

from __future__ import annotations

import json

from mtg_sources.offline_sources import (
    DATA_BEHAVIORS_PATH,
    REPORT_PATH,
    SNAPSHOT_BEHAVIORS_PATH,
    audit_offline_snapshot,
    build_simulation_deck,
    load_behavior_registry,
    load_exact_decklist,
    load_normalized_snapshot,
)


def test_snapshot_audit_required_confirmations() -> None:
    audit = audit_offline_snapshot()
    assert audit["deck_total"] == 100
    assert audit["commanders"] == ["Malcolm, Keen-Eyed Navigator", "Breeches, Brazen Plunderer"]
    assert audit["library_total"] == 98
    assert audit["exact_printings"] == 80
    assert audit["exact_printings_expected"] == 80
    assert audit["exact_printings_resolved"] == 80
    assert audit["card_data_status"] == "PASS"
    assert audit["exact_printing_validation_passed"] is True
    assert audit["deck_hash_matches_metadata"] is True
    assert audit["exact_snapshot_hash_matches_metadata"] is True
    assert audit["behavior_files_identical"] is True


def test_exact_decklist_printings_match_snapshot_and_behaviors() -> None:
    snapshots = {
        (card.name, card.set_code, card.collector_number) for card in load_normalized_snapshot()
    }
    behaviors = {
        (card.name, card.set_code, card.collector_number) for card in load_behavior_registry()
    }
    for entry in load_exact_decklist():
        key = (entry.name, entry.set_code, entry.collector_number)
        assert key in snapshots
        assert key in behaviors


def test_commanders_are_not_in_simulation_library() -> None:
    loaded = build_simulation_deck()
    assert {card.name for card in loaded.library}.isdisjoint(
        {"Malcolm, Keen-Eyed Navigator", "Breeches, Brazen Plunderer"}
    )
    assert len(loaded.library) == 98


def test_card_behavior_files_are_identical() -> None:
    assert DATA_BEHAVIORS_PATH.read_bytes() == SNAPSHOT_BEHAVIORS_PATH.read_bytes()


def test_report_blocks_pilot_until_rules_engine_tests_pass() -> None:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert report["rules_engine_tests_status"] == "PENDING"
    assert report["pilot_allowed_under_original_requirements"] is False
