#!/usr/bin/env python3
"""Refresh the frozen Oracle snapshot from Scryfall bulk data."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
DECKLIST = ROOT / "docs/source/decklist.txt"
COMMANDERS = ROOT / "docs/source/commanders.txt"
OUT = ROOT / "docs/source/oracle/snapshot_v1.json"
BULK_API = "https://api.scryfall.com/bulk-data/oracle-cards"
USER_AGENT = "mtg-deck-simulator/phase1b"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def deck_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in DECKLIST.read_text(encoding="utf-8").splitlines():
        qty_s, name = line.split(" ", 1)
        entries.append({"zone": "library", "quantity": int(qty_s), "name": name})
    for name in COMMANDERS.read_text(encoding="utf-8").splitlines():
        if name:
            entries.append({"zone": "command", "quantity": 1, "name": name})
    return entries


def fetch_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.loads(response.read())


def face_data(card: dict[str, Any]) -> list[dict[str, Any]]:
    faces = card.get("card_faces")
    if isinstance(faces, list):
        return [
            {
                "name": face.get("name"),
                "mana_cost": face.get("mana_cost", ""),
                "type_line": face.get("type_line", ""),
                "oracle_text": face.get("oracle_text", ""),
                "colors": face.get("colors", []),
                "power": face.get("power"),
                "toughness": face.get("toughness"),
                "loyalty": face.get("loyalty"),
            }
            for face in faces
        ]
    return [
        {
            "name": card.get("name"),
            "mana_cost": card.get("mana_cost", ""),
            "type_line": card.get("type_line", ""),
            "oracle_text": card.get("oracle_text", ""),
            "colors": card.get("colors", []),
            "power": card.get("power"),
            "toughness": card.get("toughness"),
            "loyalty": card.get("loyalty"),
        }
    ]


def card_record(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": card["name"],
        "oracle_id": card["oracle_id"],
        "card_faces": face_data(card),
        "mana_cost": card.get("mana_cost", ""),
        "mana_value": card.get("cmc"),
        "colors": card.get("colors", []),
        "color_identity": card.get("color_identity", []),
        "type_line": card.get("type_line", ""),
        "oracle_text": card.get("oracle_text", ""),
        "keywords": card.get("keywords", []),
        "power": card.get("power"),
        "toughness": card.get("toughness"),
        "loyalty": card.get("loyalty"),
        "defense": card.get("defense"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    bulk_meta = cast("dict[str, Any]", fetch_json(BULK_API))
    download_uri = str(bulk_meta["download_uri"])
    req = urllib.request.Request(download_uri, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as response:
        bulk_bytes = response.read()
    bulk_hash = sha256_bytes(bulk_bytes)
    bulk_cards = cast("list[dict[str, Any]]", json.loads(bulk_bytes))
    expected = deck_entries()
    expected_names = {entry["name"] for entry in expected}
    by_name = {card["name"]: card for card in bulk_cards if card.get("name") in expected_names}
    missing = sorted(expected_names - by_name.keys())
    if missing:
        sys.stderr.write("Missing Oracle records: " + ", ".join(missing) + "\n")
        return 1
    snapshot: dict[str, Any] = {
        "schema_version": 1,
        "source": {
            "provider": "Scryfall Oracle Cards bulk data",
            "bulk_api": BULK_API,
            "bulk_download_uri": download_uri,
            "bulk_updated_at": bulk_meta.get("updated_at"),
            "retrieved_at": datetime.now(UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "retrieval_command": "uv run python scripts/refresh_oracle_snapshot.py",
            "bulk_size_bytes": len(bulk_bytes),
            "bulk_sha256": bulk_hash,
            "live_fetching_allowed_during_runs": False,
            "refresh_policy": "A later Oracle refresh must create a new snapshot version and new hash.",
        },
        "expected_cards": expected,
        "cards": [card_record(by_name[name]) for name in sorted(expected_names)],
    }
    text = json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    args.output.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    snapshot["source"]["snapshot_sha256"] = digest
    text = json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    args.output.write_text(text, encoding="utf-8")
    print(f"Wrote {args.output.relative_to(ROOT)}")
    print(
        f"Cards: {len(snapshot['cards'])} unique; expected count: {sum(e['quantity'] for e in expected)}"
    )
    print(f"Snapshot SHA-256: {hashlib.sha256(args.output.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
