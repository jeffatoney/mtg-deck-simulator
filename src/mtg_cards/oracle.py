"""Frozen-Oracle-backed Phase A card specifications."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from mtg_kernel.errors import RulesError
from mtg_kernel.models import CardSpec

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "docs/source/oracle/snapshot_v1.json"
PHASE_A_NAMES = (
    "Island",
    "Mountain",
    "Sol Ring",
    "Opt",
    "Abrade",
    "Soul-Guide Lantern",
    "Commit // Memory",
    "Malcolm, Keen-Eyed Navigator",
    "Glint-Horn Buccaneer",
    "Dualcaster Mage",
    "Twinflame",
    "Curiosity",
)

# Behavior compositions are keyed by immutable Oracle identity, never interpreted names.
BEHAVIOR_BY_ORACLE_ID: dict[str, tuple[dict[str, Any], ...]] = {
    "6ad8011d-3471-4369-9d68-b264cc027487": ({"kind": "MANA", "amount": {"C": 2}},),
    "f9db72dc-9a5b-48a4-a86e-7464d9a2166a": (
        {
            "mode": "damage",
            "target_schema": ["CREATURE"],
            "effect": {"kind": "DAMAGE", "amount": 3},
        },
        {"mode": "destroy", "target_schema": ["ARTIFACT"], "effect": {"kind": "DESTROY"}},
    ),
    "1b5e6560-ff2e-4475-96cb-63f64c8a86db": (
        {"trigger": "ETB", "target_schema": ["GRAVEYARD_CARD"], "effect": {"kind": "EXILE_TARGET"}},
    ),
    "56fd8895-3be2-4591-86fa-87567d9cdc14": (
        {
            "face": 0,
            "target_schema": ["SPELL_OR_NONLAND_PERMANENT"],
            "effect": {"kind": "LIBRARY_SECOND"},
        },
        {
            "face": 1,
            "cast_permission": "AFTERMATH",
            "target_schema": [],
            "effect": {"kind": "MEMORY"},
        },
    ),
    "8eb7c0a5-6190-40de-b473-2d1daa3bbe28": (
        {
            "trigger": "ETB",
            "target_schema": ["INSTANT_OR_SORCERY_SPELL"],
            "effect": {"kind": "CREATE_SPELL_COPY"},
        },
    ),
    "83cf1169-5853-4332-b897-7b17d72d76ab": (
        {"target_schema": ["CONTROLLED_CREATURE"], "effect": {"kind": "CREATE_TOKEN_COPY"}},
    ),
}


def _record_digest(record: dict[str, Any]) -> str:
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _face(
    record: dict[str, Any], index: int, abilities: tuple[dict[str, Any], ...]
) -> dict[str, Any]:
    raw_faces = record["card_faces"]
    raw = raw_faces[index] if raw_faces else record
    matched = [a for a in abilities if a.get("face", index) == index]
    spell_effects = [ability for ability in matched if "trigger" not in ability]
    result = dict(raw)
    if isinstance(result.get("mana_value"), float):
        result["mana_value"] = int(result["mana_value"])
    result["card_types"] = raw.get("types", [])
    result["abilities"] = matched
    result["target_schema"] = spell_effects[0].get("target_schema", []) if spell_effects else []
    result["effect"] = spell_effects[0].get("effect", {}) if spell_effects else {}
    if spell_effects and "cast_permission" in spell_effects[0]:
        result["cast_permission"] = spell_effects[0]["cast_permission"]
    result["generic_cost"] = 0
    return result


def load_phase_a_specs() -> dict[str, CardSpec]:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    records = {record["name"]: record for record in snapshot["cards"]}
    if set(PHASE_A_NAMES) - records.keys():
        raise RulesError("Phase A named source pool is incomplete")
    specs: dict[str, CardSpec] = {}
    for name in PHASE_A_NAMES:
        record = records[name]
        faces = record["card_faces"] or [record]
        if any(face.get("oracle_text") is None for face in faces):
            raise RulesError(f"incomplete frozen Oracle record: {name}")
        abilities = BEHAVIOR_BY_ORACLE_ID.get(record["oracle_id"], ())
        prepared_faces = tuple(_face(record, index, abilities) for index in range(len(faces)))
        spec_id = f"oracle:{record['oracle_id']}"
        specs[spec_id] = CardSpec(
            spec_id,
            name,
            record["oracle_id"],
            _record_digest(record),
            record["mana_cost"],
            int(record["mana_value"]),
            tuple(record["supertypes"]),
            tuple(record["types"]),
            tuple(record["subtypes"]),
            record["oracle_text"],
            prepared_faces,
            abilities,
        )
    return specs
