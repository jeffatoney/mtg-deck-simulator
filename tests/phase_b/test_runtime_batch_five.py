"""Executable coverage for the fifth exact-deck Phase B runtime batch."""

from __future__ import annotations

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import TargetRef, Zone


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


def test_abrade_damage_mode_deals_three_damage_to_a_creature() -> None:
    state, executor, specs = funded_game("abrade-damage")
    creature = add_card(executor, specs["Dualcaster Mage"], Zone.BATTLEFIELD, owner="P1")
    spell = add_card(executor, specs["Abrade"], Zone.HAND)

    executor.cast("P0", spell.object_id, (TargetRef(creature.object_id),), mode="damage")
    pass_all(executor)

    assert creature.retired
    assert any(
        not obj.retired
        and obj.zone is Zone.GRAVEYARD
        and obj.current_characteristics.get("name") == "Dualcaster Mage"
        for obj in state.objects.values()
    )


def test_abrade_destroy_mode_destroys_an_artifact() -> None:
    state, executor, specs = funded_game("abrade-destroy")
    artifact = add_card(executor, specs["Sol Ring"], Zone.BATTLEFIELD, owner="P1")
    spell = add_card(executor, specs["Abrade"], Zone.HAND)

    executor.cast("P0", spell.object_id, (TargetRef(artifact.object_id),), mode="destroy")
    pass_all(executor)

    assert artifact.retired
    assert any(
        not obj.retired
        and obj.zone is Zone.GRAVEYARD
        and obj.current_characteristics.get("name") == "Sol Ring"
        for obj in state.objects.values()
    )
