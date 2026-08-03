"""Direct production-path evidence for Reality Shift manifestation."""

from __future__ import annotations

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import TargetRef, Zone

PLAYERS = ("P0", "P1")
MANA_SYMBOLS = ("W", "U", "B", "R", "G", "C")


def game_with_exact_mana(seed: str):
    state, executor = new_game(PLAYERS, seed)
    for player in state.players.values():
        player.mana_pool.update({symbol: 0 for symbol in MANA_SYMBOLS})
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    return state, executor, specs


def pass_all(executor) -> None:
    for _ in PLAYERS:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def active_named(state, name: str, zone: Zone):
    return [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and not obj.ceased_to_exist
        and obj.zone is zone
        and obj.current_characteristics.get("name") == name
    ]


def test_reality_shift_exiles_target_and_manifests_top_card_face_down() -> None:
    state, executor, specs = game_with_exact_mana("runtime-twenty-two-manifest")
    state.players["P0"].mana_pool.update({"U": 1, "C": 1})
    top_card = add_card(executor, specs["Island"], Zone.LIBRARY, owner="P1")
    target = add_card(executor, specs["Wily Goblin"], Zone.BATTLEFIELD, owner="P1")
    reality_shift = add_card(executor, specs["Reality Shift"], Zone.HAND, owner="P0")

    executor.cast("P0", reality_shift.object_id, targets=(TargetRef(target.object_id),))
    pass_all(executor)

    assert len(active_named(state, "Wily Goblin", Zone.EXILE)) == 1
    assert top_card.retired
    assert state.zones.get("LIBRARY:P1", []) == []
    manifested = [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and not obj.ceased_to_exist
        and obj.zone is Zone.BATTLEFIELD
        and obj.owner == "P1"
        and obj.current_characteristics.get("manifested") is True
    ]
    assert len(manifested) == 1
    permanent = manifested[0]
    assert permanent.predecessor_object_id == top_card.object_id
    assert permanent.component_card_instance_ids == top_card.component_card_instance_ids
    assert permanent.controller == "P1"
    assert permanent.current_characteristics == {
        "name": "Face-down creature",
        "mana_cost": "",
        "mana_value": 0,
        "supertypes": [],
        "card_types": ["Creature"],
        "subtypes": [],
        "colors": [],
        "color_identity": [],
        "keywords": [],
        "abilities": [],
        "power": 2,
        "toughness": 2,
        "manifested": True,
    }
    assert permanent.permanent_status == {
        "tap": "UNTAPPED",
        "face": "FACE_DOWN",
        "phase": "PHASED_IN",
    }
    assert permanent.identity_visible_to == {"P1"}
    assert any(
        event.kind == "MANIFESTED_PERMANENT_CREATED"
        and event.payload.get("object_id") == permanent.object_id
        for event in state.events
    )


def test_reality_shift_with_empty_library_exiles_without_creating_a_permanent() -> None:
    state, executor, specs = game_with_exact_mana("runtime-twenty-two-empty-library")
    state.players["P0"].mana_pool.update({"U": 1, "C": 1})
    target = add_card(executor, specs["Wily Goblin"], Zone.BATTLEFIELD, owner="P1")
    reality_shift = add_card(executor, specs["Reality Shift"], Zone.HAND, owner="P0")

    executor.cast("P0", reality_shift.object_id, targets=(TargetRef(target.object_id),))
    pass_all(executor)

    assert len(active_named(state, "Wily Goblin", Zone.EXILE)) == 1
    assert not any(
        not obj.retired
        and obj.zone is Zone.BATTLEFIELD
        and obj.current_characteristics.get("manifested") is True
        for obj in state.objects.values()
    )
    assert any(
        event.kind == "MANIFEST_SKIPPED_EMPTY_LIBRARY"
        and event.payload.get("player_id") == "P1"
        for event in state.events
    )
