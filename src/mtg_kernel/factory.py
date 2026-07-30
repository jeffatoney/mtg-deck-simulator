"""Factories that construct games without bypassing identity or zone services."""

from __future__ import annotations

from mtg_kernel.engine import GameExecutor
from mtg_kernel.models import (
    CardInstance,
    CardSpec,
    GameObject,
    GameState,
    ObjectKind,
    PlayerState,
    TurnState,
    Zone,
)


def new_game(
    player_ids: tuple[str, ...] = ("P0", "P1"), seed: str = "phase-a"
) -> tuple[GameState, GameExecutor]:
    state = GameState(
        "game",
        {p: PlayerState(p) for p in player_ids},
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
) -> GameObject:
    identity = executor.identity
    slot_id = identity.new_id("deck-slot")
    instance_id = identity.new_id("card")
    executor.state.card_instances[instance_id] = CardInstance(
        instance_id, spec.card_spec_id, slot_id, owner, commander
    )
    characteristics = {
        "name": spec.name,
        "card_spec_id": spec.card_spec_id,
        "mana_cost": spec.mana_cost,
        "mana_value": spec.mana_value,
        "card_types": list(spec.card_types),
        "faces": list(spec.faces),
        "abilities": list(spec.abilities),
        "oracle_record_sha256": spec.oracle_record_sha256,
    }
    obj = GameObject(
        identity.new_id("object"),
        ObjectKind.PERMANENT if zone is Zone.BATTLEFIELD else ObjectKind.CARD_IN_ZONE,
        zone,
        owner,
        owner if zone is Zone.BATTLEFIELD else None,
        (instance_id,),
        current_characteristics=characteristics,
        permanent_status={"tap": "UNTAPPED", "face": "FACE_UP", "phase": "PHASED_IN"}
        if zone is Zone.BATTLEFIELD
        else None,
        identity_visible_to=visible_to if visible_to is not None else set(executor.state.players),
    )
    executor.state.objects[obj.object_id] = obj
    executor.zones.register(obj)
    return obj
