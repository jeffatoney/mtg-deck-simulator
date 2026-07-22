"""Rules-gate tests for committed offline Scryfall sources."""

from __future__ import annotations

import json

from mtg_sim.behaviors import (
    EXECUTABLE_IMPLEMENTATIONS,
    LibraryState,
    MalcolmDamageEvent,
    curiosity_draws,
    glint_horn_damage,
    malcolm_treasures,
)
from mtg_sim.offline_sources import (
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


def test_behavior_declarations_are_not_all_executable_yet() -> None:
    declared = {entry.implementation for entry in load_behavior_registry()}
    missing = declared - EXECUTABLE_IMPLEMENTATIONS
    assert missing


def test_report_blocks_pilot_until_rules_engine_tests_pass() -> None:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert report["rules_engine_tests_status"] == "PENDING"
    assert report["pilot_allowed_under_original_requirements"] is False


def test_malcolm_treasures_are_opponent_dependent() -> None:
    assert malcolm_treasures(MalcolmDamageEvent((True, False, True))) == 2
    assert malcolm_treasures(MalcolmDamageEvent((False, False, False))) == 0


def test_empty_library_draw_fails_closed() -> None:
    try:
        curiosity_draws(1, LibraryState(0))
    except ValueError as exc:
        assert "empty" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("drawing from an empty library must fail closed")


def test_glint_horn_damage_scales_per_discard_and_opponent() -> None:
    assert glint_horn_damage(discarded_cards=2, opponents=3) == 6
