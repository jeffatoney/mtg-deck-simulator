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

PUBLIC_ZONES = {Zone.BATTLEFIELD, Zone.STACK, Zone.GRAVEYARD, Zone.EXILE, Zone.COMMAND}


def base_characteristics(spec: CardSpec, face: int | None = None) -> dict[str, object]:
    selected = spec.faces[face] if face is not None and spec.faces else None
    power = selected.get("power") if selected else spec.power
    toughness = selected.get("toughness") if selected else spec.toughness
    characteristics: dict[str, object] = {
        "name": selected.get("name", spec.name) if selected else spec.name,
        "card_spec_id": spec.card_spec_id,
        "oracle_id": spec.oracle_id,
        "oracle_record_sha256": spec.oracle_record_sha256,
        "source_version": spec.source_version,
        "mana_cost": selected.get("mana_cost", spec.mana_cost) if selected else spec.mana_cost,
        "mana_value": selected.get("mana_value", spec.mana_value) if selected else spec.mana_value,
        "supertypes": list(selected.get("supertypes", spec.supertypes)) if selected else list(spec.supertypes),
        "card_types": list(selected.get("card_types", spec.card_types)) if selected else list(spec.card_types),
        "subtypes": list(selected.get("subtypes", spec.subtypes)) if selected else list(spec.subtypes),
        "colors": list(spec.colors),
        "color_identity": list(spec.color_identity),
        "keywords": list(selected.get("keywords", spec.keywords)) if selected else list(spec.keywords),
        "oracle_text": selected.get("oracle_text", spec.oracle_text) if selected else spec.oracle_text,
        "abilities": list(selected.get("abilities", spec.abilities)) if selected else list(spec.abilities),
    }
    if power is not None:
        characteristics["power"] = int(power) if str(power).lstrip("-").isdigit() else power
    if toughness is not None:
        characteristics["toughness"] = (
            int(toughness) if str(toughness).lstrip("-").isdigit() else toughness
        )
    return characteristics


def default_visibility(zone: Zone, owner: str, players: set[str], face_down: bool = False) -> set[str]:
    if face_down or zone in {Zone.HAND, Zone.LIBRARY}:
        return {owner}
    if zone in PUBLIC_ZONES:
        return set(players)
    return {owner}


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
        nonbattlefield_orientation=orientation if zone is not Zone.BATTLEFIELD else "NOT_APPLICABLE",
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
