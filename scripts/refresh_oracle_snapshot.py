#!/usr/bin/env python3
"""Deterministically rebuild the frozen Oracle snapshot from the supplied offline source."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "offline_snapshot/normalized/cards_snapshot.json"
OUT = ROOT / "docs/source/oracle/snapshot_v1.json"
APPROVED_BULK_SHA256 = "6dc3ad46f5bbfaa77a556e73aafb0521cf33ccd5bfaba2590b95de2405739f71"
APPROVED_DECK_SHA256 = "d620c125d5cbb422196a2037fb9dafaaa60ce4e4b449198a84473540fc265edd"
APPROVED_EXACT_ENTRIES = 80
APPROVED_TOTAL_CARDS = 100


def deck_entries() -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for line in (ROOT / "docs/source/decklist.txt").read_text(encoding="utf-8").splitlines():
        quantity, name = line.split(" ", 1)
        entries.append({"name": name, "quantity": int(quantity), "zone": "library"})
    for name in (ROOT / "docs/source/commanders.txt").read_text(encoding="utf-8").splitlines():
        if name:
            entries.append({"name": name, "quantity": 1, "zone": "command"})
    return entries


def oracle_face(face: dict[str, Any]) -> dict[str, Any]:
    return {
        key: face.get(key)
        for key in (
            "name",
            "mana_cost",
            "mana_value",
            "type_line",
            "supertypes",
            "types",
            "subtypes",
            "oracle_text",
            "colors",
            "power",
            "toughness",
            "loyalty",
            "keywords",
        )
    }


def oracle_card(card: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "name",
        "oracle_id",
        "layout",
        "mana_cost",
        "mana_value",
        "type_line",
        "supertypes",
        "types",
        "subtypes",
        "oracle_text",
        "colors",
        "color_identity",
        "keywords",
        "power",
        "toughness",
        "loyalty",
    )
    result = {key: card.get(key) for key in fields}
    result["defense"] = card.get("defense")
    result["legalities"] = {"commander": card["legalities"]["commander"]}
    faces = card.get("card_faces") or []
    result["card_faces"] = [oracle_face(face) for face in faces]
    return result


def fail(message: str) -> int:
    print(f"Oracle refresh refused: {message}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    source = json.loads(args.input.read_text(encoding="utf-8"))
    metadata = source["metadata"]
    approved = {
        "bulk_sha256": APPROVED_BULK_SHA256,
        "deck_sha256": APPROVED_DECK_SHA256,
        "exact_entries_expected": APPROVED_EXACT_ENTRIES,
        "exact_entries_resolved": APPROVED_EXACT_ENTRIES,
        "total_deck_cards": APPROVED_TOTAL_CARDS,
    }
    for key, expected in approved.items():
        if metadata.get(key) != expected:
            return fail(f"{key} expected {expected!r}, got {metadata.get(key)!r}")

    expected = deck_entries()
    if sum(int(entry["quantity"]) for entry in expected) != APPROVED_TOTAL_CARDS:
        return fail("the committed deck does not contain exactly 100 cards")
    expected_names = {str(entry["name"]) for entry in expected}
    cards = source["cards"]
    if len(cards) != APPROVED_EXACT_ENTRIES:
        return fail(f"offline source contains {len(cards)} entries, expected 80")
    by_name = {card["name"]: card for card in cards}
    if set(by_name) != expected_names:
        return fail("offline card identities do not exactly match deck and commander identities")
    for card in cards:
        faces = card.get("card_faces") or [card]
        if not card.get("oracle_id") or any(face.get("oracle_text") is None for face in faces):
            return fail(f"incomplete Oracle identity or rules text for {card['name']}")

    snapshot = {
        "schema_version": 2,
        "source": {
            "provider": metadata["source"],
            "bulk_file": metadata["source_filename"],
            "bulk_record_count": metadata["bulk_record_count"],
            "bulk_sha256": metadata["bulk_sha256"],
            "deck_sha256": metadata["deck_sha256"],
            "exact_entries_expected": metadata["exact_entries_expected"],
            "exact_entries_resolved": metadata["exact_entries_resolved"],
            "total_deck_cards": metadata["total_deck_cards"],
            "retrieved_at": metadata["ingested_at_utc"],
            "offline_input": str(args.input.resolve().relative_to(ROOT)),
            "offline_input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
            "live_fetching_allowed_during_runs": False,
        },
        "expected_cards": expected,
        "cards": [oracle_card(by_name[name]) for name in sorted(expected_names)],
    }
    args.output.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    try:
        display_output = args.output.resolve().relative_to(ROOT)
    except ValueError:
        display_output = args.output.resolve()
    print(f"Wrote {display_output} from committed offline input")
    print("Verified bulk SHA-256, deck SHA-256, 80/80 exact entries, and 100 total cards")
    print(f"Snapshot SHA-256: {hashlib.sha256(args.output.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
