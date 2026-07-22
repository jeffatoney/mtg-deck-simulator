#!/usr/bin/env python3
from __future__ import annotations
import argparse
import csv
import gzip
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

DECK_RE = re.compile(r"^(\d+)\s+(.+?)\s+\(([^)]+)\)\s+(\S+)(?:\s+\*CMDR\*)?\s*$")
MULTIFACE_LAYOUTS = {
    "transform",
    "modal_dfc",
    "split",
    "adventure",
    "flip",
    "double_faced_token",
    "reversible_card",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def parse_deck(path: Path):
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        m = DECK_RE.match(line)
        if not m:
            raise ValueError(f"Unparseable deck line {line_no}: {line}")
        qty, name, set_code, collector = m.groups()
        rows.append(
            {
                "quantity": int(qty),
                "name": name,
                "set": set_code.lower(),
                "collector_number": collector,
                "commander": "*CMDR*" in line,
                "source_line": line,
            }
        )
    return rows


def type_parts(type_line):
    if not type_line:
        return [], [], []
    left, *right = re.split(r"\s+[—-]\s+", type_line, maxsplit=1)
    words = left.split()
    supers = {"Basic", "Legendary", "Snow", "World", "Ongoing"}
    typeset = {
        "Artifact",
        "Battle",
        "Creature",
        "Enchantment",
        "Instant",
        "Kindred",
        "Land",
        "Planeswalker",
        "Sorcery",
        "Tribal",
    }
    return (
        [w for w in words if w in supers],
        [w for w in words if w in typeset],
        right[0].split() if right else [],
    )


def normalize(card, deck_row):
    supertypes, types, subtypes = type_parts(card.get("type_line"))
    faces = []
    for face in card.get("card_faces") or []:
        fs, ft, fst = type_parts(face.get("type_line"))
        faces.append(
            {
                "name": face.get("name"),
                "mana_cost": face.get("mana_cost"),
                "mana_value": face.get("cmc"),
                "type_line": face.get("type_line"),
                "supertypes": fs,
                "types": ft,
                "subtypes": fst,
                "oracle_text": face.get("oracle_text"),
                "colors": face.get("colors", []),
                "power": face.get("power"),
                "toughness": face.get("toughness"),
                "loyalty": face.get("loyalty"),
                "keywords": face.get("keywords", []),
                "image_uris": face.get("image_uris", {}),
            }
        )
    return {
        "deck_quantity": deck_row["quantity"],
        "is_commander": deck_row["commander"],
        "name": card.get("name"),
        "scryfall_id": card.get("id"),
        "oracle_id": card.get("oracle_id"),
        "set": card.get("set"),
        "set_name": card.get("set_name"),
        "collector_number": str(card.get("collector_number")),
        "layout": card.get("layout"),
        "mana_cost": card.get("mana_cost"),
        "mana_value": card.get("cmc"),
        "colors": card.get("colors", []),
        "color_identity": card.get("color_identity", []),
        "type_line": card.get("type_line"),
        "supertypes": supertypes,
        "types": types,
        "subtypes": subtypes,
        "oracle_text": card.get("oracle_text"),
        "keywords": card.get("keywords", []),
        "power": card.get("power"),
        "toughness": card.get("toughness"),
        "loyalty": card.get("loyalty"),
        "legalities": card.get("legalities", {}),
        "digital": card.get("digital"),
        "games": card.get("games", []),
        "game_changer": card.get("game_changer"),
        "card_faces": faces,
        "image_uris": card.get("image_uris", {}),
        "rulings_uri": card.get("rulings_uri"),
        "scryfall_uri": card.get("scryfall_uri"),
        "artist": card.get("artist"),
        "rarity": card.get("rarity"),
    }


def image_rows(card, image_root):
    rows = []
    faces = card.get("card_faces") or [card]
    for idx, face in enumerate(faces):
        fname = face.get("name") or card["name"]
        uris = face.get("image_uris") or card.get("image_uris") or {}
        face_label = "front" if idx == 0 else f"face_{idx + 1}"
        for version in ("small", "normal"):
            filename = (
                f"{card['set']}_{card['collector_number']}_{slug(fname)}_{face_label}_{version}.jpg"
            )
            rows.append(
                {
                    "name": card["name"],
                    "face_name": fname,
                    "face": face_label,
                    "set": card["set"],
                    "collector_number": str(card["collector_number"]),
                    "version": version,
                    "url": uris.get(version, ""),
                    "local_path": str(image_root / version / filename),
                    "download_status": "pending_external_download"
                    if uris.get(version)
                    else "missing_url",
                    "size_bytes": "",
                    "sha256": "",
                }
            )
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bulk-jsonl-gz", type=Path, required=True)
    ap.add_argument("--deck", type=Path, required=True)
    ap.add_argument("--behaviors", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    out = args.output
    for rel in (
        "raw/cards",
        "normalized",
        "images/small",
        "images/normal",
        "simulation",
        "reports",
    ):
        (out / rel).mkdir(parents=True, exist_ok=True)
    deck = parse_deck(args.deck)
    deck_sha = sha256_file(args.deck)
    bulk_sha = sha256_file(args.bulk_jsonl_gz)
    need = {(d["set"], d["collector_number"]): d for d in deck}
    found = {}
    total_bulk = 0
    with gzip.open(args.bulk_jsonl_gz, "rt", encoding="utf-8") as f:
        for line in f:
            total_bulk += 1
            card = json.loads(line)
            key = (card.get("set", "").lower(), str(card.get("collector_number", "")))
            if key in need:
                found[key] = card
    unresolved = []
    errors = []
    normalized = []
    manifest = []
    raw = []
    behavior_doc = json.loads(args.behaviors.read_text(encoding="utf-8"))
    behavior_key = {
        (x["name"], x["set"], x["collector_number"]): x
        for x in behavior_doc.get("behavior_registry", [])
    }
    for key, d in need.items():
        card = found.get(key)
        if not card:
            unresolved.append({**d, "reason": "exact_printing_not_found_in_bulk"})
            errors.append(f"Unresolved exact printing: {d['source_line']}")
            continue
        raw.append(card)
        (
            out / "raw/cards" / f"{d['set']}_{d['collector_number']}_{slug(d['name'])}.json"
        ).write_text(json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8")
        n = normalize(card, d)
        normalized.append(n)
        manifest.extend(image_rows(card, out / "images"))
        if card.get("name") != d["name"]:
            errors.append(f"Name mismatch: {d['source_line']} -> {card.get('name')}")
        if card.get("legalities", {}).get("commander") != "legal":
            errors.append(f"Not Commander-legal: {d['source_line']}")
        if card.get("digital") is True or "paper" not in card.get("games", []):
            errors.append(f"Digital-only/no paper availability: {d['source_line']}")
        if "game_changer" not in card:
            errors.append(f"Game Changer field missing: {d['source_line']}")
        elif card.get("game_changer") is True:
            errors.append(f"Game Changer prohibited: {d['source_line']}")
        if card.get("layout") in MULTIFACE_LAYOUTS and not card.get("card_faces"):
            errors.append(f"Multiface data missing: {d['source_line']}")
        b = behavior_key.get((d["name"], d["set"], d["collector_number"]))
        if not b or b.get("implementation") in (None, "", "UNDECLARED"):
            errors.append(f"Behavior declaration missing: {d['source_line']}")
    metadata = {
        "schema_version": 1,
        "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Scryfall default-cards JSONL gzip supplied by user",
        "source_filename": args.bulk_jsonl_gz.name,
        "bulk_record_count": total_bulk,
        "bulk_sha256": bulk_sha,
        "deck_sha256": deck_sha,
        "exact_entries_expected": len(deck),
        "exact_entries_resolved": len(normalized),
        "total_deck_cards": sum(d["quantity"] for d in deck),
    }
    rawdoc = {"metadata": metadata, "cards": raw}
    rawbytes = json.dumps(rawdoc, indent=2, ensure_ascii=False).encode("utf-8")
    (out / "raw/scryfall_exact_printings_snapshot.json").write_bytes(rawbytes)
    metadata["exact_snapshot_sha256"] = hashlib.sha256(rawbytes).hexdigest()
    (out / "raw/snapshot_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    (out / "normalized/cards_snapshot.json").write_text(
        json.dumps({"metadata": metadata, "cards": normalized}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    fields = [
        "deck_quantity",
        "is_commander",
        "name",
        "scryfall_id",
        "oracle_id",
        "set",
        "set_name",
        "collector_number",
        "layout",
        "mana_cost",
        "mana_value",
        "colors",
        "color_identity",
        "type_line",
        "supertypes",
        "types",
        "subtypes",
        "oracle_text",
        "keywords",
        "power",
        "toughness",
        "loyalty",
        "commander_legality",
        "digital",
        "game_changer",
        "rulings_uri",
        "scryfall_uri",
        "artist",
        "rarity",
    ]
    with (out / "normalized/cards_snapshot.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for c in normalized:
            row = {k: c.get(k) for k in fields}
            row["commander_legality"] = c.get("legalities", {}).get("commander")
            for k in ("colors", "color_identity", "supertypes", "types", "subtypes", "keywords"):
                row[k] = "|".join(c.get(k) or [])
            w.writerow(row)
    with (out / "images/image_manifest.csv").open("w", newline="", encoding="utf-8") as f:
        flds = [
            "name",
            "face_name",
            "face",
            "set",
            "collector_number",
            "version",
            "url",
            "local_path",
            "download_status",
            "size_bytes",
            "sha256",
        ]
        w = csv.DictWriter(f, fieldnames=flds)
        w.writeheader()
        w.writerows(manifest)
    with (out / "reports/missing_unresolved_cards.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        flds = ["quantity", "name", "set", "collector_number", "commander", "source_line", "reason"]
        w = csv.DictWriter(f, fieldnames=flds)
        w.writeheader()
        w.writerows(unresolved)
    shutil.copy2(args.behaviors, out / "simulation/card_behaviors.json")
    image_urls_missing = sum(1 for x in manifest if not x["url"])
    card_data_status = "PASS" if not errors else "FAIL"
    report = {
        "card_data_status": card_data_status,
        "exact_printing_validation_passed": card_data_status == "PASS",
        "exact_entries_expected": len(deck),
        "exact_entries_resolved": len(normalized),
        "bulk_record_count": total_bulk,
        "commander_illegal_count": sum(
            1 for c in normalized if c.get("legalities", {}).get("commander") != "legal"
        ),
        "digital_only_count": sum(
            1 for c in normalized if c.get("digital") is True or "paper" not in c.get("games", [])
        ),
        "game_changer_count": sum(1 for c in normalized if c.get("game_changer") is True),
        "multiface_missing_count": sum(
            1
            for c in normalized
            if c.get("layout") in MULTIFACE_LAYOUTS and not c.get("card_faces")
        ),
        "behavior_declaration_missing_count": sum(
            1 for d in deck if not behavior_key.get((d["name"], d["set"], d["collector_number"]))
        ),
        "image_manifest_entries": len(manifest),
        "image_urls_missing": image_urls_missing,
        "image_cache_status": "PENDING_EXTERNAL_DOWNLOAD",
        "rules_engine_tests_status": "PENDING",
        "pilot_allowed_under_original_requirements": False,
        "pilot_blockers": [
            "Small/normal image files are not cached yet.",
            "Behavior names are declared, but executable behavior implementations and rules tests are not yet validated.",
        ],
        "validation_errors": errors,
        "bulk_sha256": bulk_sha,
        "deck_sha256": deck_sha,
        "exact_snapshot_sha256": metadata["exact_snapshot_sha256"],
    }
    (out / "reports/snapshot_validation_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    md = [
        "# Offline Snapshot Validation Report",
        "",
        f"**Card-data status:** {card_data_status}",
        f"**Exact printings resolved:** {len(normalized)} of {len(deck)}",
        f"**Scryfall bulk records scanned:** {total_bulk:,}",
        f"**Commander-illegal cards:** {report['commander_illegal_count']}",
        f"**Digital-only cards:** {report['digital_only_count']}",
        f"**Game Changers:** {report['game_changer_count']}",
        f"**Image URLs captured:** {len(manifest) - image_urls_missing} of {len(manifest)}",
        "",
        "## Pilot status",
        "",
        "**Pilot remains blocked under the original requirements.** Card data is complete, but image caching and executable behavior/rules validation remain pending.",
        "",
        "## Validation errors",
    ]
    md += [f"- {e}" for e in errors] or ["- None"]
    md += [
        "",
        "## Snapshot hashes",
        f"- Bulk file SHA-256: `{bulk_sha}`",
        f"- Exact extracted snapshot SHA-256: `{metadata['exact_snapshot_sha256']}`",
        f"- Deck SHA-256: `{deck_sha}`",
    ]
    (out / "reports/snapshot_validation_report.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if card_data_status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
