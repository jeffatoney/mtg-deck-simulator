"""Reviewed Phase A card data and composable effect vocabulary."""

from __future__ import annotations

from dataclasses import dataclass

from mtg_sim.rules_kernel import CardDefinition, MIGRATED_NAMES


@dataclass(frozen=True, slots=True)
class EffectOperation:
    operation: str
    parameters: tuple[tuple[str, str | int | bool], ...] = ()


OPERATIONS = frozenset(
    {
        "draw",
        "discard",
        "damage",
        "life_loss",
        "create_token",
        "create_treasure",
        "move_object",
        "search",
        "shuffle",
        "counter",
        "copy",
        "retarget",
        "tap",
        "untap",
        "scry",
        "exile",
        "destroy",
        "return_to_hand",
        "attach",
        "grant_haste",
        "change_power_toughness",
        "add_mana",
        "pay_mana",
    }
)


@dataclass(frozen=True, slots=True)
class CardSpecification:
    definition: CardDefinition
    effects: tuple[EffectOperation, ...] = ()
    trigger: str | None = None


def _definition(
    name: str, types: tuple[str, ...], cost: str = "", faces: tuple[str, ...] = ()
) -> CardDefinition:
    stable = name.lower().replace(" ", "_").replace("//", "split")
    return CardDefinition(stable, stable, name, types, cost, faces)


VERTICAL_SLICE: dict[str, CardSpecification] = {
    "Island": CardSpecification(_definition("Island", ("Land",))),
    "Sol Ring": CardSpecification(
        _definition("Sol Ring", ("Artifact",), "1"),
        (EffectOperation("add_mana", (("amount", 2),)),),
    ),
    "Opt": CardSpecification(
        _definition("Opt", ("Instant",), "U"), (EffectOperation("scry"), EffectOperation("draw"))
    ),
    "Abrade": CardSpecification(
        _definition("Abrade", ("Instant",), "1R"),
        (EffectOperation("damage"), EffectOperation("destroy")),
    ),
    "Soul-Guide Lantern": CardSpecification(
        _definition("Soul-Guide Lantern", ("Artifact",), "1"),
        (EffectOperation("exile"),),
        "enters_battlefield",
    ),
    "Commit // Memory": CardSpecification(
        _definition("Commit // Memory", ("Instant", "Sorcery"), faces=("Commit", "Memory")),
        (EffectOperation("move_object"), EffectOperation("shuffle"), EffectOperation("draw")),
    ),
    "Malcolm, Keen-Eyed Navigator": CardSpecification(
        _definition("Malcolm, Keen-Eyed Navigator", ("Creature",), "2U"),
        (EffectOperation("create_treasure"),),
        "pirate_damage",
    ),
    "Glint-Horn Buccaneer": CardSpecification(
        _definition("Glint-Horn Buccaneer", ("Creature",), "1RR"),
        (EffectOperation("discard"), EffectOperation("draw"), EffectOperation("damage")),
        "discard",
    ),
    "Dualcaster Mage": CardSpecification(
        _definition("Dualcaster Mage", ("Creature",), "1RR"),
        (EffectOperation("copy"), EffectOperation("retarget")),
        "enters_battlefield",
    ),
    "Twinflame": CardSpecification(
        _definition("Twinflame", ("Sorcery",), "1R"),
        (EffectOperation("create_token"), EffectOperation("grant_haste")),
    ),
}

assert frozenset(VERTICAL_SLICE) == MIGRATED_NAMES
