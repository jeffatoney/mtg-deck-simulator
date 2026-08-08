"""Focused Agent B tests for rules-owned interaction choices and atomic legality."""

from __future__ import annotations

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.hashing import state_hash
from mtg_kernel.land_actions import play_land
from mtg_kernel.models import TargetRef, Zone
from mtg_kernel.replay import transcript, validate_replay

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


def manifested_permanent(state, controller: str):
    return next(
        obj
        for obj in state.objects.values()
        if not obj.retired
        and not obj.ceased_to_exist
        and obj.zone is Zone.BATTLEFIELD
        and obj.controller == controller
        and obj.current_characteristics.get("manifested") is True
    )


def test_x_requires_explicit_cast_proposal_declaration_even_when_zero() -> None:
    state, executor, specs = funded_game("agent-b-x-explicit")
    spell = add_card(executor, specs["By Force"], Zone.HAND, owner="P0")
    before = state_hash(state)

    with pytest.raises(IllegalAction, match="X requires an explicit"):
        executor.cast("P0", spell.object_id)

    assert state_hash(state) == before
    assert spell.zone is Zone.HAND

    executor.cast("P0", spell.object_id, x_value=0)
    assert state.stack


def test_split_card_cast_path_requires_explicit_face_atomically() -> None:
    state, executor, specs = funded_game("agent-b-split-face-explicit")
    spell = add_card(executor, specs["Invert // Invent"], Zone.HAND, owner="P0")
    before = state_hash(state)

    with pytest.raises(IllegalAction, match="cast path requires an explicit card face"):
        executor.cast("P0", spell.object_id, targets=())

    assert state_hash(state) == before
    assert spell.zone is Zone.HAND

    executor.cast("P0", spell.object_id, face=0, targets=())
    assert state.stack


def test_variable_target_count_requires_explicit_target_selection_atomically() -> None:
    state, executor, specs = funded_game("agent-b-variable-target-count")
    spell = add_card(executor, specs["Twinflame"], Zone.HAND, owner="P0")
    before = state_hash(state)

    with pytest.raises(IllegalAction, match="variable target count requires an explicit"):
        executor.cast("P0", spell.object_id)

    assert state_hash(state) == before
    assert spell.zone is Zone.HAND

    executor.cast("P0", spell.object_id, targets=())
    assert state.stack


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


def test_manifested_creature_card_can_turn_face_up_as_special_action_and_replay() -> None:
    seed = "agent-b-manifest-face-up"
    state, executor, specs = funded_game(seed)
    target = add_card(executor, specs["Dualcaster Mage"], Zone.BATTLEFIELD, owner="P1")
    add_card(executor, specs["Spectral Sailor"], Zone.LIBRARY, owner="P1")
    spell = add_card(executor, specs["Reality Shift"], Zone.HAND, owner="P0")

    executor.cast("P0", spell.object_id, targets=(TargetRef(target.object_id),))
    pass_all(executor)

    manifested = manifested_permanent(state, "P1")
    object_id = manifested.object_id
    assert manifested.current_characteristics["name"] == "Face-down creature"
    assert manifested.permanent_status is not None
    assert manifested.permanent_status["face"] == "FACE_DOWN"

    executor.pass_priority("P0")
    face_up = getattr(executor, "turn_manifest_face_up")("P1", object_id)

    assert face_up.object_id == object_id
    assert face_up.current_characteristics["name"] == "Spectral Sailor"
    assert face_up.permanent_status is not None
    assert face_up.permanent_status["face"] == "FACE_UP"
    assert face_up.identity_visible_to == set(PLAYERS)
    assert state.turn.priority_holder_id == "P1"
    assert any(action.kind == "MANIFEST_FACE_UP_SPECIAL_ACTION" for action in state.actions)

    recorded = transcript(state, seed=seed)
    replayed = validate_replay(recorded)
    replayed_face_up = replayed.objects[object_id]
    assert replayed_face_up.current_characteristics["name"] == "Spectral Sailor"
    assert replayed_face_up.permanent_status is not None
    assert replayed_face_up.permanent_status["face"] == "FACE_UP"


def test_noncreature_manifest_cannot_use_manifest_face_up_action_atomically() -> None:
    state, executor, specs = funded_game("agent-b-manifest-noncreature")
    target = add_card(executor, specs["Dualcaster Mage"], Zone.BATTLEFIELD, owner="P1")
    add_card(executor, specs["Opt"], Zone.LIBRARY, owner="P1")
    spell = add_card(executor, specs["Reality Shift"], Zone.HAND, owner="P0")

    executor.cast("P0", spell.object_id, targets=(TargetRef(target.object_id),))
    pass_all(executor)
    manifested = manifested_permanent(state, "P1")
    executor.pass_priority("P0")
    before = state_hash(state)

    with pytest.raises(IllegalAction, match="cannot be turned face up"):
        getattr(executor, "turn_manifest_face_up")("P1", manifested.object_id)

    assert state_hash(state) == before
    assert manifested.current_characteristics["name"] == "Face-down creature"
    assert manifested.permanent_status is not None
    assert manifested.permanent_status["face"] == "FACE_DOWN"
