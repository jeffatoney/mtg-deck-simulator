from __future__ import annotations

from collections import Counter

from mtg_cards.full_deck import FULL_DECK_NAMES, RULES_BY_NAME, load_full_deck_specs
from mtg_deck import build_exact_game, load_exact_deck_package
from mtg_deck.package import (
    COMPOSITION_REVIEWED,
    EXECUTION_IMPLEMENTED,
    EXECUTION_UNVERIFIED,
    IMPLEMENTED_CARDS,
)
from mtg_kernel.models import Zone


def test_all_frozen_oracle_records_and_physical_cards_resolve() -> None:
    specs = load_full_deck_specs()
    package = load_exact_deck_package()
    assert len(specs) == 80 == len(FULL_DECK_NAMES)
    assert package.physical_card_count == 100
    assert package.library_count == 98
    assert package.commander_count == 2
    assert all(spec.card_spec_id == f"oracle:{spec.oracle_id}" for spec in specs.values())
    assert all(len(spec.oracle_record_sha256) == 64 for spec in specs.values())
    assert all(
        spec.faces and all(face["oracle_text"] for face in spec.faces) for spec in specs.values()
    )


def test_complete_reviewed_composition_has_no_fallback_or_execution_overclaim() -> None:
    package = load_exact_deck_package()
    assert len(package.coverage) == 80
    assert {record.composition_status for record in package.coverage} == {COMPOSITION_REVIEWED}
    implemented = {
        record.name
        for record in package.coverage
        if record.execution_status == EXECUTION_IMPLEMENTED
    }
    unverified = {
        record.name
        for record in package.coverage
        if record.execution_status == EXECUTION_UNVERIFIED
    }
    assert (
        implemented
        == set(IMPLEMENTED_CARDS)
        == {
            "Abrade",
            "Aetherize",
            "Arcane Denial",
            "Arcane Signet",
            "Ash Barrens",
            "Breeches, Brazen Plunderer",
            "Brotherhood's End",
            "By Force",
            "Cascade Bluffs",
            "Change the Equation",
            "Chart a Course",
            "Command Tower",
            "Commit // Memory",
            "Crab Umbra",
            "Curiosity",
            "Curse of the Swine",
            "Demolition Field",
            "Dispel",
            "Dizzy Spell",
            "Drift of Phantasms",
            "Dualcaster Mage",
            "Echoing Truth",
            "Electroduplicate",
            "Evolving Wilds",
            "Exotic Orchard",
            "Expedite",
            "Fact or Fiction",
            "Fading Hope",
            "Faithless Looting",
            "Fellwar Stone",
            "Fiery Cannonade",
            "Frantic Search",
            "Frostboil Snarl",
            "Glint-Horn Buccaneer",
            "Impulse",
            "Into the Roil",
            "Introduction to Annihilation",
            "Invert // Invent",
            "Island",
            "Izzet Boilerworks",
            "Izzet Signet",
            "Lazotep Plating",
            "Lightning-Rig Crew",
            "Long-Term Plans",
            "Malcolm, Keen-Eyed Navigator",
            "Mind Stone",
            "Mountain",
            "Muddle the Mixture",
            "Negate",
            "Opt",
            "Prismatic Lens",
            "Psychosis Crawler",
            "Ravenform",
            "Reality Ripple",
            "Reality Shift",
            "Rebuild",
            "Resculpt",
            "Scavenger Grounds",
            "Sentinel Totem",
            "Shivan Reef",
            "Siren Stormtamer",
            "Sleight of Hand",
            "Sol Ring",
            "Soul-Guide Lantern",
            "Spectral Sailor",
            "Spell Pierce",
            "Step Through",
            "Storm Fleet Sprinter",
            "Syncopate",
            "Temple of Epiphany",
            "Terramorphic Expanse",
            "Thriving Isle",
            "Twinflame",
            "Vandalblast",
            "Vedalken Aethermage",
            "Wash Away",
            "Wily Goblin",
        }
    )
    assert unverified == set(FULL_DECK_NAMES) - implemented
    assert all(record.handler_ids for record in package.coverage)
    assert set(RULES_BY_NAME) == set(FULL_DECK_NAMES)
    assert all(abilities for abilities in RULES_BY_NAME.values())
    assert all(
        ability.get("ability_id") and ability.get("kind")
        for abilities in RULES_BY_NAME.values()
        for ability in abilities
    )


def test_exact_deck_has_98_library_cards_and_two_commanders() -> None:
    state, _, objects = build_exact_game()
    assert len(objects["library"]) == 98
    assert len(objects["command"]) == 2
    assert len(state.card_instances) == len(state.deck_slots) == 100
    assert len(set(state.card_instances)) == 100
    assert all(obj.zone is Zone.LIBRARY for obj in objects["library"])
    assert all(obj.zone is Zone.COMMAND for obj in objects["command"])
    assert sorted(slot.deck_source_position for slot in state.deck_slots.values()) == list(
        range(100)
    )
    names = Counter(obj.current_characteristics["name"] for obj in objects["library"])
    assert names["Island"] == 12
    assert names["Mountain"] == 10
    assert {obj.current_characteristics["name"] for obj in objects["command"]} == {
        "Malcolm, Keen-Eyed Navigator",
        "Breeches, Brazen Plunderer",
    }
    assert len(state.commander_designations) == 2


def test_all_reviewed_effect_primitives_are_explicit_and_known() -> None:
    effects: set[str] = set()
    for abilities in RULES_BY_NAME.values():
        for ability in abilities:
            effect = ability.get("effect", {})
            if isinstance(effect, dict):
                effects.add(str(effect.get("kind")))
                for step in effect.get("steps", []):
                    if isinstance(step, dict):
                        effects.add(str(step.get("kind")))
    assert len(effects) == 76
    assert "NONE" not in effects
    assert "" not in effects
    assert {
        "ADD_MANA",
        "COUNTER",
        "CREATE_SPELL_COPY",
        "CREATE_TOKEN_COPIES",
        "FACT_OR_FICTION_MINIMIZING",
        "FORETELL",
        "MEMORY",
        "TRANSMUTE",
        "TYPECYCLE",
    } <= effects
