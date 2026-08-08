"""Focused Agent B tests for rules-owned interaction choices and atomic legality."""

from __future__ import annotations

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.hashing import state_hash
from mtg_kernel.land_actions import play_land
from mtg_kernel.models import TargetRef, Zone

PLAYERS = ("P0", "P1")
MANA_SYMBOLS = ("W", "U", "B", "R", "G", "C")


def funded_game(seed: str):
    state, executor = new_game(PLAYERS, seed)
    for player in state.players.values():
        for symbol in MANA_SYMBOLS:
            player.mana_pool[symbol] = 30
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


def test_kicker_requires_explicit_cast_proposal_declaration_atomically() -> None:
    state, executor, specs = funded_game("agent-b-kicker-explicit")
    target = add_card(executor, specs["Sol Ring"], Zone.BATTLEFIELD, owner="P1")
    spell = add_card(executor, specs["Into the Roil"], Zone.HAND, owner="P0")
    before = state_hash(state)

    with pytest.raises(IllegalAction, match="kicker requires an explicit boolean declaration"):
        executor.cast(
            "P0",
            spell.object_id,
            targets=(TargetRef(target.object_id),),
        )

    assert state_hash(state) == before
    assert spell.zone is Zone.HAND
    assert target.zone is Zone.BATTLEFIELD


def test_reveal_land_requires_explicit_replacement_choice_atomically() -> None:
    state, executor, specs = funded_game("agent-b-reveal-explicit")
    card = add_card(executor, specs["Frostboil Snarl"], Zone.HAND, owner="P0")
    before = state_hash(state)

    with pytest.raises(IllegalAction, match="explicit reveal-or-decline choice"):
        play_land(executor, "P0", card.object_id)

    assert state_hash(state) == before
    assert card.zone is Zone.HAND

    permanent = play_land(
        executor,
        "P0",
        card.object_id,
        choices={"reveal_object_id": None},
    )
    assert permanent.permanent_status is not None
    assert permanent.permanent_status["tap"] == "TAPPED"
    assert any(
        choice.kind == "REVEAL_FOR_LAND_ENTRY" and choice.selected == "DECLINE"
        for choice in state.choices
    )


def test_scavenger_grounds_requires_explicit_qualifying_sacrifice_atomically() -> None:
    state, executor, specs = funded_game("agent-b-grounds-explicit")
    grounds = add_card(executor, specs["Scavenger Grounds"], Zone.BATTLEFIELD, owner="P0")
    add_card(executor, specs["Opt"], Zone.GRAVEYARD, owner="P0")
    before = state_hash(state)

    with pytest.raises(IllegalAction, match="additional sacrifice cost requires an explicit"):
        executor.activate("P0", grounds.object_id, "grounds:exile")

    assert state_hash(state) == before
    assert grounds.zone is Zone.BATTLEFIELD
    assert grounds.permanent_status is not None
    assert grounds.permanent_status["tap"] == "UNTAPPED"


def test_scavenger_grounds_may_sacrifice_another_desert_and_source_survives() -> None:
    state, executor, specs = funded_game("agent-b-grounds-other-desert")
    grounds = add_card(executor, specs["Scavenger Grounds"], Zone.BATTLEFIELD, owner="P0")
    other_desert = add_card(
        executor,
        specs["Scavenger Grounds"],
        Zone.BATTLEFIELD,
        owner="P0",
    )
    add_card(executor, specs["Opt"], Zone.GRAVEYARD, owner="P0")
    add_card(executor, specs["Mountain"], Zone.GRAVEYARD, owner="P1")

    executor.activate(
        "P0",
        grounds.object_id,
        "grounds:exile",
        choices={"additional_sacrifice_object_id": other_desert.object_id},
    )

    assert grounds.zone is Zone.BATTLEFIELD
    assert grounds.permanent_status is not None
    assert grounds.permanent_status["tap"] == "TAPPED"
    assert other_desert.retired
    assert active_named(state, "Scavenger Grounds", Zone.GRAVEYARD)
    sacrifice_choice = next(
        choice for choice in state.choices if choice.kind == "ADDITIONAL_SACRIFICE_SELECTION"
    )
    assert sacrifice_choice.selected == other_desert.object_id

    pass_all(executor)

    assert active_named(state, "Scavenger Grounds", Zone.BATTLEFIELD)
    assert not [
        obj
        for obj in state.objects.values()
        if not obj.retired and not obj.ceased_to_exist and obj.zone is Zone.GRAVEYARD
    ]
