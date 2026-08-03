"""Executable coverage for the second exact-deck Phase B runtime batch."""

from __future__ import annotations

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.factory import add_card, add_external_public_object, new_game
from mtg_kernel.models import Zone


def funded_game(seed: str):
    state, executor = new_game(("P0", "P1"), seed)
    for symbol in ("W", "U", "B", "R", "G", "C"):
        state.players["P0"].mana_pool[symbol] = 30
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    return state, executor, specs


def pass_all(executor) -> None:
    for _ in range(2):
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def test_brotherhoods_end_damages_creatures_and_planeswalkers_simultaneously() -> None:
    state, executor, specs = funded_game("brotherhood-damage")
    creature = add_card(executor, specs["Dualcaster Mage"], Zone.BATTLEFIELD, owner="P1")
    surviving_walker = add_external_public_object(
        executor,
        "walker-survives",
        Zone.BATTLEFIELD,
        "P1",
        "P1",
        {
            "name": "Opponent Planeswalker A",
            "card_types": ["Planeswalker"],
            "mana_value": 4,
            "abilities": [],
        },
    )
    defeated_walker = add_external_public_object(
        executor,
        "walker-defeated",
        Zone.BATTLEFIELD,
        "P1",
        "P1",
        {
            "name": "Opponent Planeswalker B",
            "card_types": ["Planeswalker"],
            "mana_value": 3,
            "abilities": [],
        },
    )
    surviving_walker.counters["LOYALTY"] = 4
    defeated_walker.counters["LOYALTY"] = 3
    spell = add_card(executor, specs["Brotherhood's End"], Zone.HAND)

    executor.cast("P0", spell.object_id, mode="damage")
    pass_all(executor)

    assert creature.retired
    assert any(
        not obj.retired
        and obj.zone is Zone.GRAVEYARD
        and obj.current_characteristics.get("name") == "Dualcaster Mage"
        for obj in state.objects.values()
    )
    assert not surviving_walker.retired
    assert surviving_walker.counters["LOYALTY"] == 1
    assert defeated_walker.retired
    assert any(
        entry["object_id"] == defeated_walker.object_id
        and entry["destination"] == Zone.GRAVEYARD.value
        for entry in state.external_object_ledger
    )


def test_brotherhoods_end_destroys_only_artifacts_with_mana_value_three_or_less() -> None:
    state, executor, specs = funded_game("brotherhood-artifacts")
    low_value = add_card(executor, specs["Sol Ring"], Zone.BATTLEFIELD, owner="P1")
    high_value = add_external_public_object(
        executor,
        "large-artifact",
        Zone.BATTLEFIELD,
        "P1",
        "P1",
        {
            "name": "Large Opponent Artifact",
            "card_types": ["Artifact"],
            "mana_value": 4,
            "abilities": [],
        },
    )
    spell = add_card(executor, specs["Brotherhood's End"], Zone.HAND)

    executor.cast("P0", spell.object_id, mode="artifacts")
    pass_all(executor)

    assert low_value.retired
    assert any(
        not obj.retired
        and obj.zone is Zone.GRAVEYARD
        and obj.current_characteristics.get("name") == "Sol Ring"
        for obj in state.objects.values()
    )
    assert not high_value.retired
    assert high_value.zone is Zone.BATTLEFIELD
