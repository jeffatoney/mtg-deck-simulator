"""Frozen-Oracle-backed Phase A card specifications and complete behavior compositions."""

from __future__ import annotations

import hashlib
import json
import re
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


def _target(kind: str, *, minimum: int = 1, maximum: int | None = 1) -> dict[str, Any]:
    return {"kind": kind, "min": minimum, "max": maximum, "unique": True}


# Every printed rules-bearing line for the named Phase A slice is represented here.
# Dispatch is by immutable Oracle ID; names remain display data only.
BEHAVIOR_BY_ORACLE_ID: dict[str, tuple[dict[str, Any], ...]] = {
    "b2c6aa39-2d2a-459c-a555-fb48ba993373": (
        {
            "ability_id": "island:mana-u",
            "kind": "ACTIVATED",
            "mana_ability": True,
            "cost": {"tap": True},
            "effect": {"kind": "ADD_MANA", "mana": {"U": 1}},
        },
    ),
    "a3fb7228-e76b-4e96-a40e-20b5fed75685": (
        {
            "ability_id": "mountain:mana-r",
            "kind": "ACTIVATED",
            "mana_ability": True,
            "cost": {"tap": True},
            "effect": {"kind": "ADD_MANA", "mana": {"R": 1}},
        },
    ),
    "6ad8011d-3471-4369-9d68-b264cc027487": (
        {
            "ability_id": "sol-ring:mana-cc",
            "kind": "ACTIVATED",
            "mana_ability": True,
            "cost": {"tap": True},
            "effect": {"kind": "ADD_MANA", "mana": {"C": 2}},
        },
    ),
    "713332c1-5bd8-400f-bfff-c1ca0697a043": (
        {
            "ability_id": "opt:spell",
            "kind": "SPELL",
            "face": 0,
            "mode": "default",
            "target_schema": _target("NONE", minimum=0, maximum=0),
            "effect": {
                "kind": "SEQUENCE",
                "effects": ({"kind": "SCRY", "count": 1}, {"kind": "DRAW", "count": 1}),
            },
        },
    ),
    "f9db72dc-9a5b-48a4-a86e-7464d9a2166a": (
        {
            "ability_id": "abrade:damage",
            "kind": "SPELL",
            "face": 0,
            "mode": "damage",
            "target_schema": _target("CREATURE"),
            "effect": {"kind": "DAMAGE", "amount": 3},
        },
        {
            "ability_id": "abrade:destroy",
            "kind": "SPELL",
            "face": 0,
            "mode": "destroy",
            "target_schema": _target("ARTIFACT"),
            "effect": {"kind": "DESTROY"},
        },
    ),
    "1b5e6560-ff2e-4475-96cb-63f64c8a86db": (
        {
            "ability_id": "lantern:etb",
            "kind": "TRIGGERED",
            "trigger": "ETB",
            "target_schema": _target("GRAVEYARD_CARD"),
            "effect": {"kind": "EXILE_TARGET"},
        },
        {
            "ability_id": "lantern:exile-opponents",
            "kind": "ACTIVATED",
            "cost": {"tap": True, "sacrifice_source": True},
            "target_schema": _target("NONE", minimum=0, maximum=0),
            "effect": {"kind": "EXILE_OPPONENT_GRAVEYARDS"},
        },
        {
            "ability_id": "lantern:draw",
            "kind": "ACTIVATED",
            "cost": {"mana": "{1}", "tap": True, "sacrifice_source": True},
            "target_schema": _target("NONE", minimum=0, maximum=0),
            "effect": {"kind": "DRAW", "count": 1},
        },
    ),
    "56fd8895-3be2-4591-86fa-87567d9cdc14": (
        {
            "ability_id": "commit:spell",
            "kind": "SPELL",
            "face": 0,
            "mode": "default",
            "target_schema": _target("SPELL_OR_NONLAND_PERMANENT"),
            "effect": {"kind": "LIBRARY_SECOND"},
        },
        {
            "ability_id": "memory:spell",
            "kind": "SPELL",
            "face": 1,
            "mode": "default",
            "cast_permission": "AFTERMATH",
            "target_schema": _target("NONE", minimum=0, maximum=0),
            "effect": {"kind": "MEMORY"},
        },
    ),
    "a66f8b44-0163-4456-b152-4acefab896a4": (
        {
            "ability_id": "malcolm:pirate-damage",
            "kind": "TRIGGERED",
            "trigger": "PIRATE_DAMAGE_TO_OPPONENTS",
            "target_schema": _target("NONE", minimum=0, maximum=0),
            "effect": {"kind": "CREATE_TREASURES_FOR_DAMAGED_OPPONENTS"},
        },
    ),
    "64ad5657-78e9-4f34-8877-18c4f51fff9a": (
        {
            "ability_id": "glint-horn:discard-trigger",
            "kind": "TRIGGERED",
            "trigger": "CONTROLLER_DISCARDS",
            "target_schema": _target("NONE", minimum=0, maximum=0),
            "effect": {"kind": "DAMAGE_EACH_OPPONENT", "amount": 1},
        },
        {
            "ability_id": "glint-horn:attack-loot",
            "kind": "ACTIVATED",
            "cost": {"mana": "{1}{R}", "discard": 1},
            "restriction": "SOURCE_ATTACKING",
            "target_schema": _target("NONE", minimum=0, maximum=0),
            "effect": {"kind": "DRAW", "count": 1},
        },
    ),
    "8eb7c0a5-6190-40de-b473-2d1daa3bbe28": (
        {
            "ability_id": "dualcaster:etb",
            "kind": "TRIGGERED",
            "trigger": "ETB",
            "target_schema": _target("INSTANT_OR_SORCERY_SPELL"),
            "effect": {"kind": "CREATE_SPELL_COPY", "may_choose_new_targets": True},
        },
    ),
    "83cf1169-5853-4332-b897-7b17d72d76ab": (
        {
            "ability_id": "twinflame:spell",
            "kind": "SPELL",
            "face": 0,
            "mode": "default",
            "target_schema": _target("CONTROLLED_CREATURE", minimum=0, maximum=None),
            "additional_cost": {"per_target_beyond_first": "{2}{R}"},
            "effect": {
                "kind": "CREATE_TOKEN_COPIES",
                "haste": True,
                "delayed": "EXILE_AT_NEXT_END_STEP",
            },
        },
    ),
    "223fa044-d387-4884-bf4e-75f1b61c6a46": (
        {
            "ability_id": "curiosity:aura-spell",
            "kind": "SPELL",
            "face": 0,
            "mode": "default",
            "target_schema": _target("CREATURE"),
            "effect": {"kind": "ATTACH_AURA"},
        },
        {
            "ability_id": "curiosity:damage-trigger",
            "kind": "TRIGGERED",
            "trigger": "ENCHANTED_CREATURE_DAMAGE_TO_OPPONENT",
            "optional": True,
            "target_schema": _target("NONE", minimum=0, maximum=0),
            "effect": {"kind": "DRAW", "count": 1},
        },
    ),
}


def _record_digest(record: dict[str, Any]) -> str:
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _mana_value_from_cost(cost: str) -> int:
    value = 0
    for symbol in re.findall(r"\{([^}]+)\}", cost):
        if symbol.isdigit():
            value += int(symbol)
        elif symbol == "X":
            continue
        else:
            value += 1
    return value


def _validate_record(record: dict[str, Any]) -> None:
    required = {
        "name",
        "oracle_id",
        "mana_cost",
        "mana_value",
        "supertypes",
        "types",
        "subtypes",
        "keywords",
        "colors",
        "color_identity",
        "card_faces",
    }
    missing = required - record.keys()
    if missing:
        raise RulesError(f"incomplete frozen Oracle record {record.get('name')!r}: {sorted(missing)}")
    if not record["oracle_id"] or not isinstance(record["types"], list):
        raise RulesError(f"invalid frozen Oracle identity record: {record.get('name')!r}")
    faces = record["card_faces"] or [record]
    face_required = {"name", "mana_cost", "oracle_text", "types", "supertypes", "subtypes", "keywords"}
    for face in faces:
        missing_face = face_required - face.keys()
        if missing_face or not isinstance(face.get("oracle_text"), str) or not face["oracle_text"].strip():
            raise RulesError(f"incomplete frozen Oracle face for {record['name']}: {sorted(missing_face)}")


def _prepared_face(
    record: dict[str, Any], index: int, behaviors: tuple[dict[str, Any], ...]
) -> dict[str, Any]:
    raw_faces = record["card_faces"]
    raw = dict(raw_faces[index] if raw_faces else record)
    raw.setdefault("supertypes", record["supertypes"])
    raw.setdefault("subtypes", record["subtypes"])
    raw.setdefault("keywords", record["keywords"])
    raw["card_types"] = list(raw.get("types", []))
    raw["mana_value"] = _mana_value_from_cost(raw.get("mana_cost", ""))
    matched = tuple(behavior for behavior in behaviors if int(behavior.get("face", 0)) == index)
    raw["abilities"] = list(matched)
    raw["spell_modes"] = [behavior for behavior in matched if behavior["kind"] == "SPELL"]
    raw["activated_abilities"] = [
        behavior for behavior in matched if behavior["kind"] == "ACTIVATED"
    ]
    raw["triggered_abilities"] = [
        behavior for behavior in matched if behavior["kind"] == "TRIGGERED"
    ]
    return raw


def load_phase_a_specs() -> dict[str, CardSpec]:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    source = snapshot.get("source", {})
    if snapshot.get("schema_version") != 2 or source.get("live_fetching_allowed_during_runs") is not False:
        raise RulesError("Oracle source is not the approved offline snapshot schema")
    source_version = f"snapshot-v2:{source.get('bulk_sha256', '')}"
    records = {record["name"]: record for record in snapshot["cards"]}
    missing_names = set(PHASE_A_NAMES) - records.keys()
    if missing_names:
        raise RulesError(f"Phase A named source pool is incomplete: {sorted(missing_names)}")
    specs: dict[str, CardSpec] = {}
    for name in PHASE_A_NAMES:
        record = records[name]
        _validate_record(record)
        behaviors = BEHAVIOR_BY_ORACLE_ID.get(record["oracle_id"])
        if not behaviors:
            raise RulesError(f"real Phase A card has no complete behavior composition: {name}")
        raw_faces = record["card_faces"] or [record]
        prepared_faces = tuple(
            _prepared_face(record, index, behaviors) for index in range(len(raw_faces))
        )
        spec_id = f"oracle:{record['oracle_id']}"
        spec = CardSpec(
            card_spec_id=spec_id,
            name=name,
            oracle_id=record["oracle_id"],
            oracle_record_sha256=_record_digest(record),
            source_version=source_version,
            mana_cost=record["mana_cost"],
            mana_value=int(record["mana_value"]),
            supertypes=tuple(record["supertypes"]),
            card_types=tuple(record["types"]),
            subtypes=tuple(record["subtypes"]),
            colors=tuple(record["colors"]),
            color_identity=tuple(record["color_identity"]),
            keywords=tuple(record["keywords"]),
            power=record.get("power"),
            toughness=record.get("toughness"),
            oracle_text=record.get("oracle_text"),
            faces=prepared_faces,
            abilities=behaviors,
        )
        specs[spec_id] = spec
    return specs
