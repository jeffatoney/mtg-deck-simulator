"""Complete frozen-Oracle behavior compositions for the exact Phase B deck."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mtg_cards.oracle import (
    SNAPSHOT,
    _prepared_face,
    _record_digest,
    _validate_record,
)
from mtg_kernel.errors import RulesError
from mtg_kernel.models import CardSpec


def target(kind: str, minimum: int = 1, maximum: int | None = 1) -> dict[str, Any]:
    return {"kind": kind, "min": minimum, "max": maximum, "unique": True}


def spell(effect: str, *, mode: str = "default", face: int = 0, targets: str = "NONE",
          minimum: int = 0, maximum: int | None = 0, cost: str | None = None,
          permission: str | None = None, **parameters: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "kind": "SPELL", "face": face, "mode": mode,
        "target_schema": target(targets, minimum, maximum),
        "effect": {"kind": effect, **parameters},
    }
    if cost is not None:
        value["alternative_cost"] = cost
    if permission is not None:
        value["cast_permission"] = permission
    return value


def activated(ability_id: str, effect: str, *, mana_cost: str = "", targets: str = "NONE",
              minimum: int = 0, maximum: int | None = 0, tap: bool = False,
              sacrifice: bool = False, discard: int = 0, restriction: str | None = None,
              mana_ability: bool = False, **parameters: Any) -> dict[str, Any]:
    cost: dict[str, Any] = {}
    if mana_cost:
        cost["mana"] = mana_cost
    if tap:
        cost["tap"] = True
    if sacrifice:
        cost["sacrifice_source"] = True
    if discard:
        cost["discard"] = discard
    value: dict[str, Any] = {
        "ability_id": ability_id, "kind": "ACTIVATED", "cost": cost,
        "target_schema": target(targets, minimum, maximum),
        "effect": {"kind": effect, **parameters},
    }
    if restriction:
        value["restriction"] = restriction
    if mana_ability:
        value["mana_ability"] = True
    return value


def triggered(ability_id: str, trigger: str, effect: str, *, optional: bool = False,
              targets: str = "NONE", minimum: int = 0, maximum: int | None = 0,
              **parameters: Any) -> dict[str, Any]:
    return {
        "ability_id": ability_id, "kind": "TRIGGERED", "trigger": trigger,
        "optional": optional, "target_schema": target(targets, minimum, maximum),
        "effect": {"kind": effect, **parameters},
    }


def mana(ability_id: str, produced: dict[str, int], *, mana_cost: str = "",
         choice: tuple[str, ...] = (), life: int = 0) -> dict[str, Any]:
    effect = {"kind": "ADD_MANA", "mana": produced}
    if choice:
        effect = {"kind": "ADD_CHOSEN_MANA", "choices": choice}
    return activated(ability_id, effect.pop("kind"), mana_cost=mana_cost, tap=True,
                     mana_ability=True, life=life, **effect)


# Names are used only while compiling immutable Oracle-ID keyed data in this card layer.
# Kernel control flow dispatches primitive kinds, never card names.
RULES_BY_NAME: dict[str, tuple[dict[str, Any], ...]] = {
    "Abrade": (
        spell("DAMAGE", mode="damage", targets="CREATURE", minimum=1, maximum=1, amount=3),
        spell("DESTROY", mode="destroy", targets="ARTIFACT", minimum=1, maximum=1),
    ),
    "Aetherize": (spell("BOUNCE_ATTACKING_CREATURES"),),
    "Arcane Denial": (spell("COUNTER_WITH_DELAYED_DRAWS", targets="SPELL", minimum=1, maximum=1),),
    "Arcane Signet": (activated("arcane-signet:mana", "ADD_COMMANDER_COLOR", tap=True, mana_ability=True),),
    "Ash Barrens": (
        mana("ash-barrens:c", {"C": 1}),
        activated("ash-barrens:basic-landcycling", "TYPECYCLE", mana_cost="{1}", discard=1,
                  subtype="Basic Land", timing="INSTANT"),
    ),
    "Breeches, Brazen Plunderer": (
        triggered("breeches:pirate-damage", "PIRATE_DAMAGE_TO_OPPONENTS",
                  "RECORD_UNKNOWN_BREECHES_EXILES"),
    ),
    "Brotherhood's End": (
        spell("DAMAGE_ALL_CREATURES_PLANESWALKERS", mode="damage", amount=3),
        spell("DESTROY_ARTIFACTS_MV_LEQ", mode="artifacts", maximum_mana_value=3),
    ),
    "By Force": (spell("DESTROY_TARGETS", targets="ARTIFACT", minimum=0, maximum=None,
                        target_count_from_x=True),),
    "Cascade Bluffs": (
        mana("cascade-bluffs:c", {"C": 1}),
        activated("cascade-bluffs:filter", "FILTER_MANA_OPTIONS", mana_cost="{U/R}", tap=True,
                  mana_ability=True, options=({"U": 2}, {"U": 1, "R": 1}, {"R": 2})),
    ),
    "Change the Equation": (
        spell("COUNTER_IF", mode="small", targets="SPELL", minimum=1, maximum=1,
              predicate={"mana_value_lte": 2}),
        spell("COUNTER_IF", mode="red_green", targets="SPELL", minimum=1, maximum=1,
              predicate={"colors_any": ["R", "G"], "mana_value_lte": 6}),
    ),
    "Chart a Course": (spell("DRAW_THEN_DISCARD_UNLESS_ATTACKED", draw=2, discard=1),),
    "Command Tower": (activated("command-tower:mana", "ADD_COMMANDER_COLOR", tap=True, mana_ability=True),),
    "Commit // Memory": (
        spell("LIBRARY_SECOND", face=0, targets="SPELL_OR_NONLAND_PERMANENT", minimum=1, maximum=1),
        spell("MEMORY", face=1, permission="AFTERMATH"),
    ),
    "Crab Umbra": (
        spell("ATTACH_AURA", targets="CREATURE", minimum=1, maximum=1),
        activated("crab-umbra:untap", "UNTAP_ATTACHED", mana_cost="{2}{U}"),
        {"ability_id": "crab-umbra:umbra-armor", "kind": "REPLACEMENT",
         "event": "ENCHANTED_CREATURE_DESTROY", "effect": {"kind": "UMBRA_ARMOR"}},
    ),
    "Curiosity": (
        spell("ATTACH_AURA", targets="CREATURE", minimum=1, maximum=1),
        triggered("curiosity:damage", "ENCHANTED_CREATURE_DAMAGE_TO_OPPONENT",
                  "DRAW", optional=True, count=1),
    ),
    "Curse of the Swine": (spell("EXILE_CREATURES_CREATE_BOARS", targets="CREATURE",
                                  minimum=0, maximum=None, target_count_from_x=True),),
    "Demolition Field": (
        mana("demolition-field:c", {"C": 1}),
        activated("demolition-field:destroy", "DEMOLITION_FIELD", mana_cost="{2}", tap=True,
                  sacrifice=True, targets="OPPONENT_NONBASIC_LAND", minimum=1, maximum=1),
    ),
    "Dispel": (spell("COUNTER_IF", targets="SPELL", minimum=1, maximum=1,
                      predicate={"card_types_any": ["Instant"]}),),
    "Dizzy Spell": (
        spell("MODIFY_POWER_TOUGHNESS", targets="CREATURE", minimum=1, maximum=1,
              power=-3, toughness=0, duration="END_OF_TURN"),
        activated("dizzy-spell:transmute", "TRANSMUTE", mana_cost="{1}{U}{U}", discard=1,
                  restriction="SORCERY_SPEED", mana_value=1),
    ),
    "Drift of Phantasms": (
        activated("drift:transmute", "TRANSMUTE", mana_cost="{1}{U}{U}", discard=1,
                  restriction="SORCERY_SPEED", mana_value=3),
    ),
    "Dualcaster Mage": (
        triggered("dualcaster:etb", "ETB", "CREATE_SPELL_COPY",
                  targets="INSTANT_OR_SORCERY_SPELL", minimum=1, maximum=1,
                  may_choose_new_targets=True),
    ),
    "Echoing Truth": (spell("ECHOING_BOUNCE", targets="NONLAND_PERMANENT", minimum=1, maximum=1),),
    "Electroduplicate": (
        spell("CREATE_TOKEN_COPIES", targets="CONTROLLED_CREATURE", minimum=1, maximum=1,
              haste=True, delayed="SACRIFICE_AT_NEXT_END_STEP"),
        {"ability_id": "electroduplicate:flashback", "kind": "CAST_PERMISSION",
         "permission": "FLASHBACK", "cost": "{2}{R}{R}"},
    ),
    "Evolving Wilds": (activated("evolving-wilds:fetch", "FETCH_BASIC", tap=True, sacrifice=True,
                                 enters_tapped=True),),
    "Exotic Orchard": (activated("exotic-orchard:mana", "ADD_OPPONENT_PROFILE_COLOR",
                                  tap=True, mana_ability=True),),
    "Expedite": (spell("SEQUENCE", targets="CREATURE", minimum=1, maximum=1,
                        effects=({"kind": "GRANT_HASTE", "duration": "END_OF_TURN"},
                                 {"kind": "DRAW", "count": 1})),),
    "Fact or Fiction": (spell("FACT_OR_FICTION_MINIMIZING", reveal=5),),
    "Fading Hope": (spell("BOUNCE_AND_CONDITIONAL_SCRY", targets="CREATURE", minimum=1, maximum=1,
                           mana_value_lte=3, scry=1),),
    "Faithless Looting": (
        spell("DRAW_DISCARD", draw=2, discard=2),
        {"ability_id": "faithless-looting:flashback", "kind": "CAST_PERMISSION",
         "permission": "FLASHBACK", "cost": "{2}{R}"},
    ),
    "Fellwar Stone": (activated("fellwar-stone:mana", "ADD_OPPONENT_PROFILE_COLOR",
                                 tap=True, mana_ability=True),),
    "Fiery Cannonade": (spell("DAMAGE_ALL_NON_SUBTYPE", amount=2, excluded_subtype="Pirate"),),
    "Frantic Search": (spell("DRAW_DISCARD_UNTAP_LANDS", draw=2, discard=2, untap=3),),
    "Frostboil Snarl": (
        {"ability_id": "snarl:as-enters", "kind": "REPLACEMENT", "event": "ENTERS_BATTLEFIELD",
         "effect": {"kind": "REVEAL_OR_ENTER_TAPPED", "subtypes": ["Island", "Mountain"]}},
        activated("snarl:mana", "ADD_CHOSEN_MANA", tap=True, mana_ability=True, choices=("U", "R")),
    ),
    "Glint-Horn Buccaneer": (
        triggered("glint-horn:discard", "CONTROLLER_DISCARDS", "DAMAGE_EACH_OPPONENT", amount=1),
        activated("glint-horn:loot", "DRAW", mana_cost="{1}{R}", discard=1,
                  restriction="SOURCE_ATTACKING", count=1),
    ),
    "Impulse": (spell("LOOK_SELECT_REST_BOTTOM", look=4, select=1),),
    "Into the Roil": (spell("BOUNCE_AND_KICKER_DRAW", targets="NONLAND_PERMANENT", minimum=1,
                             maximum=1, kicker="{1}{U}"),),
    "Introduction to Annihilation": (spell("EXILE_THEN_CONTROLLER_DRAWS",
                                                   targets="NONLAND_PERMANENT", minimum=1, maximum=1),),
    "Invert // Invent": (
        spell("SWITCH_POWER_TOUGHNESS", face=0, targets="CREATURE", minimum=0, maximum=2,
              duration="END_OF_TURN"),
        spell("TUTOR_TYPES", face=1, types=("Instant", "Sorcery"), maximum_each=1),
    ),
    "Island": (mana("island:u", {"U": 1}),),
    "Izzet Boilerworks": (
        {"ability_id": "boilerworks:enters", "kind": "REPLACEMENT", "event": "ENTERS_BATTLEFIELD",
         "effect": {"kind": "ENTER_TAPPED"}},
        triggered("boilerworks:etb", "ETB", "RETURN_CONTROLLED_LAND",
                  targets="CONTROLLED_LAND", minimum=1, maximum=1),
        mana("boilerworks:ur", {"U": 1, "R": 1}),
    ),
    "Izzet Signet": (activated("izzet-signet:filter", "ADD_MANA", mana_cost="{1}", tap=True,
                                mana_ability=True, mana={"U": 1, "R": 1}),),
    "Lazotep Plating": (spell("AMASS_AND_HEXPROOF", amass=1, duration="END_OF_TURN"),),
    "Lightning-Rig Crew": (
        activated("rig-crew:damage", "DAMAGE_EACH_OPPONENT", tap=True, amount=1),
        triggered("rig-crew:pirate-cast", "CONTROLLER_CASTS_PIRATE", "UNTAP_SOURCE"),
    ),
    "Long-Term Plans": (spell("TUTOR_THIRD_FROM_TOP"),),
    "Malcolm, Keen-Eyed Navigator": (
        triggered("malcolm:pirate-damage", "PIRATE_DAMAGE_TO_OPPONENTS",
                  "CREATE_TREASURES_FOR_DAMAGED_OPPONENTS"),
    ),
    "Mind Stone": (
        mana("mind-stone:c", {"C": 1}),
        activated("mind-stone:draw", "DRAW", mana_cost="{1}", tap=True, sacrifice=True, count=1),
    ),
    "Mountain": (mana("mountain:r", {"R": 1}),),
    "Muddle the Mixture": (
        spell("COUNTER_IF", targets="SPELL", minimum=1, maximum=1,
              predicate={"card_types_any": ["Instant", "Sorcery"]}),
        activated("muddle:transmute", "TRANSMUTE", mana_cost="{1}{U}{U}", discard=1,
                  restriction="SORCERY_SPEED", mana_value=2),
    ),
    "Negate": (spell("COUNTER_IF", targets="SPELL", minimum=1, maximum=1,
                      predicate={"card_types_none": ["Creature"]}),),
    "Niv-Mizzet, the Firemind": (
        triggered("niv:draw", "CONTROLLER_DRAWS", "DAMAGE_ANY_TARGET", targets="ANY_TARGET",
                  minimum=1, maximum=1, amount=1),
        activated("niv:draw", "DRAW", tap=True, count=1),
    ),
    "Opt": (spell("SEQUENCE", effects=({"kind": "SCRY", "count": 1},
                                         {"kind": "DRAW", "count": 1})),),
    "Path of Ancestry": (
        {"ability_id": "path:enters", "kind": "REPLACEMENT", "event": "ENTERS_BATTLEFIELD",
         "effect": {"kind": "ENTER_TAPPED"}},
        activated("path:mana", "ADD_COMMANDER_COLOR_AND_MARK", tap=True, mana_ability=True),
        triggered("path:spent", "MARKED_MANA_SPENT_ON_SHARED_CREATURE_TYPE", "SCRY", count=1),
    ),
    "Prismari Command": (
        spell("PRISMARI_COMMAND", mode="choose_two", targets="PRISMARI_TARGETS", minimum=0,
              maximum=2, choose=2),
    ),
    "Prismatic Lens": (
        mana("lens:c", {"C": 1}),
        activated("lens:filter", "ADD_CHOSEN_MANA", mana_cost="{1}", tap=True,
                  mana_ability=True, choices=("W", "U", "B", "R", "G")),
    ),
    "Psychosis Crawler": (
        {"ability_id": "crawler:dynamic-pt", "kind": "STATIC",
         "effect": {"kind": "HAND_SIZE_POWER_TOUGHNESS"}},
        triggered("crawler:draw", "CONTROLLER_DRAWS", "EACH_OPPONENT_LOSES_LIFE", amount=1),
    ),
    "Ravenform": (
        spell("EXILE_CREATE_TOKEN", targets="ARTIFACT_OR_CREATURE", minimum=1, maximum=1,
              token={"name": "Bird", "power": 1, "toughness": 1, "colors": ["U"],
                     "subtypes": ["Bird"], "keywords": ["Flying"]}),
        {"ability_id": "ravenform:foretell", "kind": "SPECIAL_ACTION", "cost": "{2}",
         "effect": {"kind": "FORETELL", "cast_cost": "{U}"}},
    ),
    "Reality Ripple": (spell("PHASE_OUT", targets="ARTIFACT_CREATURE_OR_LAND", minimum=1, maximum=1),),
    "Reality Shift": (spell("EXILE_AND_MANIFEST", targets="CREATURE", minimum=1, maximum=1),),
    "Rebuild": (
        spell("BOUNCE_ALL_ARTIFACTS"),
        activated("rebuild:cycling", "DRAW", mana_cost="{2}", discard=1, count=1),
    ),
    "Resculpt": (spell("EXILE_CREATE_TOKEN", targets="ARTIFACT_OR_CREATURE", minimum=1, maximum=1,
                        token={"name": "Elemental", "power": 4, "toughness": 4,
                               "colors": ["U", "R"], "subtypes": ["Elemental"]}),),
    "Scavenger Grounds": (
        mana("grounds:c", {"C": 1}),
        activated("grounds:exile", "EXILE_ALL_GRAVEYARDS", mana_cost="{2}", tap=True,
                  sacrifice=True, additional_sacrifice_subtype="Desert"),
    ),
    "Sentinel Totem": (
        triggered("totem:etb", "ETB", "SCRY", count=1),
        activated("totem:exile", "EXILE_ALL_GRAVEYARDS", tap=True, sacrifice=True),
    ),
    "Shivan Reef": (
        mana("reef:c", {"C": 1}),
        activated("reef:colored", "ADD_CHOSEN_MANA_AND_DAMAGE_SELF", tap=True,
                  mana_ability=True, choices=("U", "R"), damage=1),
    ),
    "Siren Stormtamer": (activated("stormtamer:counter", "COUNTER_TARGETING_CONTROLLER",
                                          mana_cost="{U}", sacrifice=True, targets="SPELL_OR_ABILITY",
                                          minimum=1, maximum=1),),
    "Sleight of Hand": (spell("LOOK_SELECT_REST_BOTTOM", look=2, select=1),),
    "Sol Ring": (mana("sol-ring:cc", {"C": 2}),),
    "Soul-Guide Lantern": (
        triggered("lantern:etb", "ETB", "EXILE_TARGET", targets="GRAVEYARD_CARD",
                  minimum=1, maximum=1),
        activated("lantern:opponent-graves", "EXILE_OPPONENT_GRAVEYARDS", tap=True,
                  sacrifice=True),
        activated("lantern:draw", "DRAW", mana_cost="{1}", tap=True, sacrifice=True, count=1),
    ),
    "Spectral Sailor": (activated("sailor:draw", "DRAW", mana_cost="{3}{U}", count=1),),
    "Spell Pierce": (spell("COUNTER_UNLESS_PAY", targets="SPELL", minimum=1, maximum=1,
                            amount=2, predicate={"card_types_none": ["Creature"]}),),
    "Step Through": (
        spell("BOUNCE_TARGETS", targets="CREATURE", minimum=2, maximum=2),
        activated("step-through:wizardcycling", "TYPECYCLE", mana_cost="{2}", discard=1,
                  subtype="Wizard", timing="INSTANT"),
    ),
    "Storm Fleet Sprinter": (),
    "Syncopate": (spell("COUNTER_UNLESS_PAY_EXILE", targets="SPELL", minimum=1, maximum=1,
                         amount_from_x=True),),
    "Temple of Epiphany": (
        {"ability_id": "temple:enters", "kind": "REPLACEMENT", "event": "ENTERS_BATTLEFIELD",
         "effect": {"kind": "ENTER_TAPPED"}},
        triggered("temple:etb", "ETB", "SCRY", count=1),
        activated("temple:mana", "ADD_CHOSEN_MANA", tap=True, mana_ability=True,
                  choices=("U", "R")),
    ),
    "Terramorphic Expanse": (activated("terramorphic:fetch", "FETCH_BASIC", tap=True,
                                       sacrifice=True, enters_tapped=True),),
    "Thriving Isle": (
        {"ability_id": "thriving:as-enters", "kind": "REPLACEMENT", "event": "ENTERS_BATTLEFIELD",
         "effect": {"kind": "CHOOSE_COLOR_ENTER_TAPPED", "excluded": ["U"]}},
        activated("thriving:mana", "ADD_BLUE_OR_FIXED_CHOSEN", tap=True, mana_ability=True),
    ),
    "Twinflame": (spell("CREATE_TOKEN_COPIES", targets="CONTROLLED_CREATURE", minimum=0,
                         maximum=None, haste=True, delayed="EXILE_AT_NEXT_END_STEP",
                         additional_cost={"per_target_beyond_first": "{2}{R}"}),),
    "Vandalblast": (
        spell("DESTROY", mode="target", targets="OPPONENT_ARTIFACT", minimum=1, maximum=1),
        spell("DESTROY_ALL_OPPONENT_ARTIFACTS", mode="overload", cost="{4}{R}"),
    ),
    "Vedalken Aethermage": (
        triggered("aethermage:etb", "ETB", "BOUNCE_TARGET", targets="SLIVER", minimum=0, maximum=1),
        activated("aethermage:wizardcycling", "TYPECYCLE", mana_cost="{3}", discard=1,
                  subtype="Wizard", timing="INSTANT"),
    ),
    "Wash Away": (
        spell("COUNTER_IF", mode="normal", targets="SPELL", minimum=1, maximum=1,
              predicate={"cast_from_not_owner_hand": True}),
        spell("COUNTER", mode="cleave", targets="SPELL", minimum=1, maximum=1, cost="{1}{U}{U}"),
    ),
    "Wily Goblin": (triggered("wily:etb", "ETB", "CREATE_TREASURE", count=1),),
}

# A creature with only keyword/static text still needs an explicit reviewed composition.
RULES_BY_NAME["Storm Fleet Sprinter"] = (
    {"ability_id": "sprinter:haste", "kind": "STATIC", "effect": {"kind": "KEYWORD", "name": "Haste"}},
    {"ability_id": "sprinter:unblockable", "kind": "STATIC", "effect": {"kind": "CANT_BE_BLOCKED"}},
)


def load_full_deck_specs() -> dict[str, CardSpec]:
    snapshot = json.loads(Path(SNAPSHOT).read_text(encoding="utf-8"))
    source = snapshot.get("source", {})
    if snapshot.get("schema_version") != 2 or source.get("live_fetching_allowed_during_runs") is not False:
        raise RulesError("Oracle source is not the approved offline snapshot schema")
    records = {str(record["name"]): record for record in snapshot["cards"]}
    if set(records) != set(RULES_BY_NAME):
        raise RulesError(
            f"full-deck behavior inventory mismatch: missing={sorted(set(records)-set(RULES_BY_NAME))}, "
            f"extra={sorted(set(RULES_BY_NAME)-set(records))}"
        )
    source_version = f"snapshot-v2:{source.get('bulk_sha256', '')}"
    specs: dict[str, CardSpec] = {}
    for name, record in records.items():
        _validate_record(record)
        behaviors = tuple(RULES_BY_NAME[name])
        if not behaviors:
            raise RulesError(f"full-deck card has no reviewed behavior composition: {name}")
        for index, behavior in enumerate(behaviors):
            behavior.setdefault("ability_id", f"oracle:{record['oracle_id']}:{index}")
        faces = record["card_faces"] or [record]
        prepared = tuple(_prepared_face(record, index, behaviors) for index in range(len(faces)))
        spec_id = f"oracle:{record['oracle_id']}"
        specs[spec_id] = CardSpec(
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
            faces=prepared,
            abilities=behaviors,
        )
    return specs


FULL_DECK_NAMES = tuple(RULES_BY_NAME)

# Alternative-cast modes and top-level additional costs are explicit spell definitions.
RULES_BY_NAME["Electroduplicate"] = (
    spell("CREATE_TOKEN_COPIES", mode="normal", targets="CONTROLLED_CREATURE", minimum=1,
          maximum=1, haste=True, delayed="SACRIFICE_AT_NEXT_END_STEP"),
    spell("CREATE_TOKEN_COPIES", mode="flashback", targets="CONTROLLED_CREATURE", minimum=1,
          maximum=1, haste=True, delayed="SACRIFICE_AT_NEXT_END_STEP", permission="FLASHBACK",
          cost="{2}{R}{R}"),
)
RULES_BY_NAME["Faithless Looting"] = (
    spell("DRAW_DISCARD", mode="normal", draw=2, discard=2),
    spell("DRAW_DISCARD", mode="flashback", draw=2, discard=2, permission="FLASHBACK",
          cost="{2}{R}"),
)
RULES_BY_NAME["Ravenform"] = (
    spell("EXILE_CREATE_TOKEN", mode="normal", targets="ARTIFACT_OR_CREATURE", minimum=1,
          maximum=1, token={"name": "Bird", "power": 1, "toughness": 1, "colors": ["U"],
                            "subtypes": ["Bird"], "keywords": ["Flying"]}),
    spell("EXILE_CREATE_TOKEN", mode="foretell", targets="ARTIFACT_OR_CREATURE", minimum=1,
          maximum=1, token={"name": "Bird", "power": 1, "toughness": 1, "colors": ["U"],
                            "subtypes": ["Bird"], "keywords": ["Flying"]},
          permission="FORETELL", cost="{U}"),
    {"ability_id": "ravenform:foretell", "kind": "SPECIAL_ACTION", "cost": {"mana": "{2}"},
     "effect": {"kind": "FORETELL", "cast_cost": "{U}"}},
)
_twinflame = RULES_BY_NAME["Twinflame"][0]
_twinflame["additional_cost"] = _twinflame["effect"].pop("additional_cost")
