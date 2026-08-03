"""Direct exact-deck evidence for entry triggers, graveyard exile, and static abilities."""

from __future__ import annotations

from typing import Any

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.land_actions import play_land
from mtg_kernel.models import GameObject, Zone


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


def reset_pool(state) -> None:
    for symbol in ("W", "U", "B", "R", "G", "C"):
        state.players["P0"].mana_pool[symbol] = 0


def active_object(state, name: str) -> GameObject:
    return next(
        obj
        for obj in state.objects.values()
        if not obj.retired
        and not obj.ceased_to_exist
        and obj.current_characteristics.get("name") == name
    )


def test_izzet_boilerworks_executes_entry_trigger_and_mana() -> None:
    state, executor, specs = funded_game("runtime-eleven-boilerworks")
    island = add_card(executor, specs["Island"], Zone.BATTLEFIELD)
    card = add_card(executor, specs["Izzet Boilerworks"], Zone.HAND)

    boilerworks = play_land(
        executor,
        "P0",
        card.object_id,
        {"trigger_targets": {"boilerworks:etb": island.object_id}},
    )

    assert boilerworks.permanent_status is not None
    assert boilerworks.permanent_status["tap"] == "TAPPED"
    assert state.stack
    pass_all(executor)
    assert island.retired
    assert active_object(state, "Island").zone is Zone.HAND

    boilerworks.permanent_status["tap"] = "UNTAPPED"
    reset_pool(state)
    executor.activate("P0", boilerworks.object_id, "boilerworks:ur")
    assert state.players["P0"].mana_pool["U"] == 1
    assert state.players["P0"].mana_pool["R"] == 1


def test_temple_of_epiphany_scries_on_entry_and_produces_mana() -> None:
    state, executor, specs = funded_game("runtime-eleven-temple")
    bottom = add_card(executor, specs["Island"], Zone.LIBRARY)
    top = add_card(executor, specs["Mountain"], Zone.LIBRARY)
    card = add_card(executor, specs["Temple of Epiphany"], Zone.HAND)

    temple = play_land(executor, "P0", card.object_id, {"scry_to_bottom": True})

    assert temple.permanent_status is not None
    assert temple.permanent_status["tap"] == "TAPPED"
    assert state.stack
    pass_all(executor)
    assert state.zones["LIBRARY:P0"] == [top.object_id, bottom.object_id]
    assert any(choice.kind == "SCRY_1" and choice.selected == "BOTTOM" for choice in state.choices)

    temple.permanent_status["tap"] = "UNTAPPED"
    reset_pool(state)
    executor.activate("P0", temple.object_id, "temple:mana", choices={"mana_color": "U"})
    assert state.players["P0"].mana_pool["U"] == 1


def test_sentinel_totem_scries_then_exiles_all_graveyards() -> None:
    state, executor, specs = funded_game("runtime-eleven-totem")
    bottom = add_card(executor, specs["Island"], Zone.LIBRARY)
    top = add_card(executor, specs["Mountain"], Zone.LIBRARY)
    card = add_card(executor, specs["Sentinel Totem"], Zone.HAND)

    executor.cast("P0", card.object_id, choices={"scry_to_bottom": True})
    pass_all(executor)
    totem = active_object(state, "Sentinel Totem")
    assert totem.zone is Zone.BATTLEFIELD
    assert state.stack
    pass_all(executor)
    assert state.zones["LIBRARY:P0"] == [top.object_id, bottom.object_id]

    add_card(executor, specs["Opt"], Zone.GRAVEYARD)
    add_card(executor, specs["Mountain"], Zone.GRAVEYARD, owner="P1")
    executor.activate("P0", totem.object_id, "totem:exile")
    assert totem.retired
    pass_all(executor)

    assert not [
        obj
        for obj in state.objects.values()
        if not obj.retired and not obj.ceased_to_exist and obj.zone is Zone.GRAVEYARD
    ]
    assert active_object(state, "Sentinel Totem").zone is Zone.EXILE


def test_storm_fleet_sprinter_resolves_with_both_static_abilities() -> None:
    state, executor, specs = funded_game("runtime-eleven-sprinter")
    card = add_card(executor, specs["Storm Fleet Sprinter"], Zone.HAND)

    executor.cast("P0", card.object_id)
    pass_all(executor)

    sprinter = active_object(state, "Storm Fleet Sprinter")
    assert sprinter.zone is Zone.BATTLEFIELD
    assert "Haste" in sprinter.current_characteristics.get("keywords", ())
    static_effects = {
        str(ability.get("effect", {}).get("kind", ""))
        for ability in sprinter.current_characteristics.get("abilities", ())
        if ability.get("kind") == "STATIC"
    }
    assert static_effects == {"KEYWORD", "CANT_BE_BLOCKED"}
