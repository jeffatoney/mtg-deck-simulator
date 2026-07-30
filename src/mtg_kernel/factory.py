"""Factories that construct games without bypassing identity or zone services."""

from __future__ import annotations

from mtg_kernel.engine import GameExecutor
from mtg_kernel.models import (
    CardInstance,
    CardSpec,
    DeckSlot,
    GameObject,
    GameState,
    ObjectKind,
    PlayerState,
    TurnState,
    Zone,
)
from mtg_kernel.specs import base_characteristics, default_visibility


def new_game(
    player_ids: tuple[str, ...] = ("P0", "P1"), seed: str = "phase-a"
) -> tuple[GameState, GameExecutor]:
    state = GameState(
        "game",
        {player_id: PlayerState(player_id) for player_id in player_ids},
        TurnState(player_ids[0], priority_holder_id=player_ids[0]),
    )
    return state, GameExecutor(state, seed)


def add_card(
    executor: GameExecutor,
    spec: CardSpec,
    zone: Zone,
    owner: str = "P0",
    commander: bool = False,
    visible_to: set[str] | None = None,
    face_down: bool = False,
) -> GameObject:
    identity = executor.identity
    executor.state.card_specs[spec.card_spec_id] = spec
    slot_id = identity.new_id("deck-slot")
    executor.state.deck_slots[slot_id] = DeckSlot(
        slot_id, spec.card_spec_id, len(executor.state.deck_slots)
    )
    instance_id = identity.new_id("card")
    executor.state.card_instances[instance_id] = CardInstance(
        instance_id, spec.card_spec_id, slot_id, owner, commander
    )
    if commander:
        executor.state.commander_designations[instance_id] = owner
    object_kind = ObjectKind.PERMANENT if zone is Zone.BATTLEFIELD else ObjectKind.CARD_IN_ZONE
    orientation = "FACE_DOWN" if face_down else "FACE_UP"
    obj = GameObject(
        identity.new_id("object"),
        object_kind,
        zone,
        owner,
        owner if zone is Zone.BATTLEFIELD else None,
        (instance_id,),
        current_characteristics=base_characteristics(spec),
        permanent_status={"tap": "UNTAPPED", "face": orientation, "phase": "PHASED_IN"}
        if zone is Zone.BATTLEFIELD
        else None,
        nonbattlefield_orientation=orientation
        if zone is not Zone.BATTLEFIELD
        else "NOT_APPLICABLE",
        identity_visible_to=visible_to
        if visible_to is not None
        else default_visibility(zone, owner, set(executor.state.players), face_down),
    )
    executor.state.objects[obj.object_id] = obj
    executor.zones.register(obj)
    return obj


def add_external_public_object(
    executor: GameExecutor,
    object_id: str,
    zone: Zone,
    owner: str,
    controller: str | None,
    characteristics: dict[str, object],
) -> GameObject:
    obj = GameObject(
        object_id,
        ObjectKind.EXTERNAL_PUBLIC_OBJECT,
        zone,
        owner,
        controller if zone in {Zone.BATTLEFIELD, Zone.STACK} else None,
        current_characteristics=dict(characteristics),
        permanent_status={"tap": "UNTAPPED", "face": "FACE_UP", "phase": "PHASED_IN"}
        if zone is Zone.BATTLEFIELD
        else None,
        identity_visible_to=set(executor.state.players),
    )
    executor.state.objects[obj.object_id] = obj
    executor.zones.register(obj)
    return obj
