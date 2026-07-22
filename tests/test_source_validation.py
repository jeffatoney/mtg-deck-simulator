"""Source-freeze validation tests."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from mtg_sim.cli import app
from mtg_sim.source_validation import EXPECTED_COMMANDERS, validate_sources

ROOT = Path(__file__).resolve().parents[1]


def test_current_sources_validate() -> None:
    result = validate_sources()
    assert result.ok, result.errors


def test_validate_sources_cli_passes() -> None:
    result = CliRunner().invoke(app, ["validate-sources"])
    assert result.exit_code == 0
    assert "Source validation passed." in result.stdout


def test_decklist_has_exactly_98_library_cards() -> None:
    total = 0
    for line in (ROOT / "docs/source/decklist.txt").read_text(encoding="utf-8").splitlines():
        quantity, _name = line.split(" ", 1)
        total += int(quantity)
    assert total == 98


def test_commanders_are_exact() -> None:
    commanders = tuple(
        (ROOT / "docs/source/commanders.txt").read_text(encoding="utf-8").splitlines()
    )
    assert commanders == EXPECTED_COMMANDERS


def test_split_cards_are_normalized() -> None:
    deck_names = {
        line.split(" ", 1)[1]
        for line in (ROOT / "docs/source/decklist.txt").read_text(encoding="utf-8").splitlines()
    }
    assert "Commit // Memory" in deck_names
    assert "Invert // Invent" in deck_names
    assert all("//" not in name or " // " in name for name in deck_names)


def test_inventory_contains_required_metadata() -> None:
    inventory = json.loads((ROOT / "docs/source/source_inventory.json").read_text(encoding="utf-8"))
    entries = inventory["entries"]
    assert entries
    for entry in entries:
        assert set(entry) == {"path", "sha256", "size_bytes", "source_category", "status"}
        assert len(entry["sha256"]) == 64
        assert entry["status"] in {"frozen", "generated"}


def test_oracle_snapshot_represents_exact_expected_cards() -> None:
    snapshot = json.loads(
        (ROOT / "docs/source/oracle/snapshot_v1.json").read_text(encoding="utf-8")
    )
    assert sum(entry["quantity"] for entry in snapshot["expected_cards"]) == 100
    expected_names = {entry["name"] for entry in snapshot["expected_cards"]}
    assert {card["name"] for card in snapshot["cards"]} == expected_names
    assert snapshot["source"]["live_fetching_allowed_during_runs"] is False


def test_baseline_config_contains_resolved_assumptions() -> None:
    text = (ROOT / "configs/baseline.toml").read_text(encoding="utf-8")
    for expected in (
        'primary_opponent_mana_profile = "blue_red_available"',
        'sensitivity_opponent_mana_profile = "no_known_colors"',
        "opponent_mana_lands_are_targetable = false",
        "opponent_mana_lands_are_abstract_metadata = true",
        'fact_or_fiction_policy = "minimize_deck_frozen_evaluation"',
        'baseline_recovery_measurement = "independent_second_line_availability"',
        'true_disrupted_recovery_study = "separate"',
        'breeches_unknown_cards = "record_trigger_but_exclude_from_deterministic_resources"',
    ):
        assert expected in text
