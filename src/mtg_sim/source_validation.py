"""Source-freeze inventory and validation for Phase 1B."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "docs" / "source"
INVENTORY_PATH = SOURCE_DIR / "source_inventory.json"
ORACLE_SNAPSHOT = "docs/source/oracle/snapshot_v1.json"
BASELINE_CONFIG = "configs/baseline.toml"
REQUIRED_SOURCE_FILES = (
    "docs/source/MagicCompRules_2026-06-19.txt",
    "docs/source/commanders.txt",
    "docs/source/decklist.txt",
    "docs/source/oracle/SCHEMA.md",
    "docs/source/oracle/REFRESH_PROCESS.md",
    ORACLE_SNAPSHOT,
    BASELINE_CONFIG,
    "docs/spec/OPEN_DECISIONS.md",
)
EXPECTED_COMMANDERS = ("Malcolm, Keen-Eyed Navigator", "Breeches, Brazen Plunderer")
SPLIT_CARD_NAMES = ("Commit // Memory", "Invert // Invent")
DECK_LINE_RE = re.compile(r"^(?P<quantity>[1-9][0-9]*) (?P<name>.+)$")
BASELINE_ASSUMPTIONS: dict[str, object] = {
    "primary_opponent_mana_profile": "blue_red_available",
    "sensitivity_opponent_mana_profile": "no_known_colors",
    "opponent_mana_lands_are_targetable": False,
    "opponent_mana_lands_are_abstract_metadata": True,
    "fact_or_fiction_policy": "minimize_deck_frozen_evaluation",
    "baseline_recovery_measurement": "independent_second_line_availability",
    "true_disrupted_recovery_study": "separate",
    "breeches_unknown_cards": "record_trigger_but_exclude_from_deterministic_resources",
}


@dataclass(frozen=True)
class ValidationResult:
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_category(relative: str) -> str:
    if relative.endswith("MagicCompRules_2026-06-19.txt"):
        return "comprehensive_rules"
    if relative.endswith("decklist.txt"):
        return "decklist"
    if relative.endswith("commanders.txt"):
        return "commanders"
    if relative == BASELINE_CONFIG:
        return "baseline_config"
    if relative.endswith("OPEN_DECISIONS.md"):
        return "baseline_decisions"
    if relative == ORACLE_SNAPSHOT:
        return "oracle_snapshot"
    if "/oracle/" in relative:
        return "oracle_schema"
    return "source_support"


def build_inventory() -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for relative in REQUIRED_SOURCE_FILES:
        path = ROOT / relative
        entries.append(
            {
                "path": relative,
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path),
                "source_category": _source_category(relative),
                "status": "frozen",
            }
        )
    return {
        "schema_version": 1,
        "generated_by": "uv run mtg-sim validate-sources --write-inventory",
        "entries": entries,
    }


def write_inventory(path: Path = INVENTORY_PATH) -> None:
    path.write_text(
        json.dumps(build_inventory(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _load_json(path: Path, errors: list[str]) -> dict[str, Any] | None:
    try:
        return cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as exc:
        errors.append(f"malformed JSON: {path.relative_to(ROOT)}: {exc}")
        return None


def _deck_entries(errors: list[str]) -> list[tuple[int, str]]:
    entries: list[tuple[int, str]] = []
    for line_number, line in enumerate(
        (ROOT / "docs/source/decklist.txt").read_text(encoding="utf-8").splitlines(), start=1
    ):
        match = DECK_LINE_RE.match(line)
        if match is None:
            errors.append(f"malformed decklist line {line_number}: {line!r}")
            continue
        entries.append((int(match.group("quantity")), match.group("name")))
    return entries


def _expected_card_entries(errors: list[str]) -> list[dict[str, object]]:
    expected = [
        {"zone": "library", "quantity": quantity, "name": name}
        for quantity, name in _deck_entries(errors)
    ]
    expected.extend(
        {"zone": "command", "quantity": 1, "name": name} for name in EXPECTED_COMMANDERS
    )
    return expected


def _validate_deck(errors: list[str]) -> None:
    entries = _deck_entries(errors)
    count = sum(quantity for quantity, _name in entries)
    if count != 98:
        errors.append(f"library count must be exactly 98 by quantity; found {count}")
    names = {name for _quantity, name in entries}
    for split_name in SPLIT_CARD_NAMES:
        if split_name not in names:
            errors.append(f"required normalized split-card name missing or malformed: {split_name}")
    for name in [name for _quantity, name in entries if "//" in name and " // " not in name]:
        errors.append(f"split-card name is malformed; use spaces around '//': {name}")


def _validate_commanders(errors: list[str]) -> None:
    commanders = tuple(
        line
        for line in (ROOT / "docs/source/commanders.txt").read_text(encoding="utf-8").splitlines()
        if line
    )
    if commanders != EXPECTED_COMMANDERS:
        errors.append("commanders.txt must contain exactly: " + ", ".join(EXPECTED_COMMANDERS))


def _validate_inventory(errors: list[str]) -> None:
    inventory = _load_json(INVENTORY_PATH, errors)
    if inventory is None:
        return
    entries = inventory.get("entries")
    if not isinstance(entries, list):
        errors.append("source inventory must contain an entries list")
        return
    by_path = {entry.get("path"): entry for entry in entries if isinstance(entry, dict)}
    for relative in REQUIRED_SOURCE_FILES:
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"required source file missing: {relative}")
            continue
        entry = by_path.get(relative)
        if entry is None:
            errors.append(f"required source file missing from inventory: {relative}")
            continue
        if entry.get("size_bytes") != path.stat().st_size:
            errors.append(f"recorded source size does not match: {relative}")
        if entry.get("sha256") != sha256(path):
            errors.append(f"recorded source hash does not match: {relative}")
        if entry.get("status") != "frozen":
            errors.append(f"frozen status invalid for inventory entry: {relative}")


def _parse_simple_toml(path: Path) -> dict[str, object]:
    values: dict[str, object] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        key, value = [part.strip() for part in line.split("=", 1)]
        if value in {"true", "false"}:
            values[key] = value == "true"
        else:
            values[key] = value.strip('"')
    return values


def _validate_baseline(errors: list[str]) -> None:
    actual = _parse_simple_toml(ROOT / BASELINE_CONFIG)
    for key, value in BASELINE_ASSUMPTIONS.items():
        if actual.get(key) != value:
            errors.append(f"baseline assumption mismatch: {key}")
    decisions = (ROOT / "docs/spec/OPEN_DECISIONS.md").read_text(encoding="utf-8").lower()
    if "blocking" in decisions and "no baseline decision remains blocking" not in decisions:
        errors.append("OPEN_DECISIONS.md still contains a blocking decision")


def _validate_oracle_snapshot(errors: list[str]) -> None:
    snapshot_path = ROOT / ORACLE_SNAPSHOT
    snapshot = _load_json(snapshot_path, errors)
    if snapshot is None:
        return
    if snapshot.get("source", {}).get("live_fetching_allowed_during_runs") is not False:
        errors.append("live Oracle fetching must be disabled during tests and simulations")
    expected = _expected_card_entries(errors)
    if sum(cast("int", entry["quantity"]) for entry in expected) != 100:
        errors.append("exactly 100 expected cards must be represented")
    if snapshot.get("expected_cards") != expected:
        errors.append("Oracle snapshot expected_cards does not match deck and command zone")
    expected_names = {str(entry["name"]) for entry in expected}
    cards = snapshot.get("cards")
    if not isinstance(cards, list):
        errors.append("Oracle snapshot must contain cards list")
        return
    names = {str(card.get("name")) for card in cards if isinstance(card, dict)}
    for missing in sorted(expected_names - names):
        errors.append(f"expected card has no Oracle data: {missing}")
    for extra in sorted(names - expected_names):
        errors.append(f"unexpected card included in Oracle snapshot: {extra}")
    for card in cards:
        if not isinstance(card, dict):
            errors.append("Oracle card entry must be an object")
            continue
        for field in (
            "name",
            "oracle_id",
            "card_faces",
            "mana_cost",
            "mana_value",
            "colors",
            "color_identity",
            "type_line",
            "oracle_text",
            "keywords",
            "power",
            "toughness",
            "loyalty",
        ):
            if field not in card:
                errors.append(f"Oracle card missing required field {field}: {card.get('name')}")


def validate_sources() -> ValidationResult:
    errors: list[str] = []
    _validate_inventory(errors)
    _validate_deck(errors)
    _validate_commanders(errors)
    _validate_oracle_snapshot(errors)
    _validate_baseline(errors)
    return ValidationResult(tuple(errors))
