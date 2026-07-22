"""Source-freeze inventory and validation for Phase 1A."""

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
REQUIRED_SOURCE_FILES = (
    "docs/source/MagicCompRules_2026-06-19.txt",
    "docs/source/commanders.txt",
    "docs/source/decklist.txt",
    "docs/source/oracle/SCHEMA.md",
    "docs/source/oracle/REFRESH_PROCESS.md",
)
EXPECTED_COMMANDERS = ("Malcolm, Keen-Eyed Navigator", "Breeches, Brazen Plunderer")
SPLIT_CARD_NAMES = ("Commit // Memory", "Invert // Invent")
DECK_LINE_RE = re.compile(r"^(?P<quantity>[1-9][0-9]*) (?P<name>.+)$")


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
    data = build_inventory()
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_inventory(errors: list[str]) -> dict[str, Any] | None:
    if not INVENTORY_PATH.is_file():
        errors.append(f"required source inventory missing: {INVENTORY_PATH.relative_to(ROOT)}")
        return None
    try:
        data = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        return cast("dict[str, Any]", data)
    except json.JSONDecodeError as exc:
        errors.append(f"source inventory is malformed JSON: {exc}")
        return None


def _deck_entries(errors: list[str]) -> list[tuple[int, str]]:
    deck_path = ROOT / "docs/source/decklist.txt"
    entries: list[tuple[int, str]] = []
    if not deck_path.is_file():
        errors.append("required source file missing: docs/source/decklist.txt")
        return entries
    for line_number, line in enumerate(deck_path.read_text(encoding="utf-8").splitlines(), start=1):
        match = DECK_LINE_RE.match(line)
        if match is None:
            errors.append(f"malformed decklist line {line_number}: {line!r}")
            continue
        entries.append((int(match.group("quantity")), match.group("name")))
    return entries


def _validate_deck(errors: list[str]) -> None:
    entries = _deck_entries(errors)
    count = sum(quantity for quantity, _name in entries)
    if count != 98:
        errors.append(f"library count must be exactly 98 by quantity; found {count}")
    names = {name for _quantity, name in entries}
    for split_name in SPLIT_CARD_NAMES:
        if split_name not in names:
            errors.append(f"required normalized split-card name missing or malformed: {split_name}")
    malformed_split = [name for _quantity, name in entries if "//" in name and " // " not in name]
    for name in malformed_split:
        errors.append(f"split-card name is malformed; use spaces around '//': {name}")


def _validate_commanders(errors: list[str]) -> None:
    path = ROOT / "docs/source/commanders.txt"
    if not path.is_file():
        errors.append("required source file missing: docs/source/commanders.txt")
        return
    commanders = tuple(line for line in path.read_text(encoding="utf-8").splitlines() if line)
    if len(commanders) != 2:
        errors.append(f"commander count must be exactly 2; found {len(commanders)}")
    if commanders != EXPECTED_COMMANDERS:
        errors.append("commanders.txt must contain exactly: " + ", ".join(EXPECTED_COMMANDERS))


def _validate_inventory(errors: list[str]) -> None:
    inventory = _load_inventory(errors)
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
        if not entry.get("source_category"):
            errors.append(f"source category missing from inventory: {relative}")
        if entry.get("status") not in {"frozen", "generated"}:
            errors.append(f"frozen/generated status invalid for inventory entry: {relative}")


def validate_sources() -> ValidationResult:
    errors: list[str] = []
    _validate_inventory(errors)
    _validate_deck(errors)
    _validate_commanders(errors)
    return ValidationResult(tuple(errors))
