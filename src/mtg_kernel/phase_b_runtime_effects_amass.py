"""Amass and temporary hexproof resolution for the exact-deck runtime."""

from __future__ import annotations

from typing import Any

from mtg_kernel.errors import IllegalAction
from mtg_kernel.models import Action, Choice, GameObject, ObjectKind, Zone
from mtg_kernel.phase_b_runtime_helpers import _permanents
from mtg_kernel.phase_b_runtime_support import _subtypes

HEXPROOF_EFFECT_KIND = "PLAYER_AND_CONTROLLED_PERMANENTS_HEXPROOF"


def _create_zombie_army(executor: Any, action: Action) -> GameObject:
    event = executor._event(
        "TOKEN_CREATED",
        action,
        controller=action.actor_id,
        token_name="Zombie Army",
    )
    token = GameObject(
        executor.identity.new_id("object"),
        ObjectKind.TOKEN_OBJECT,
        Zone.BATTLEFIELD,
        action.actor_id,
        action.actor_id,
        created_by_event_id=event.event_id,
        current_characteristics={
            "name": "Zombie Army",
            "card_types": ["Creature"],
            "subtypes": ["Zombie", "Army"],
            "colors": ["B"],
            "keywords": [],
            "abilities": [],
            "power": 0,
            "toughness": 0,
        },
        permanent_status={
            "tap": "UNTAPPED",
            "face": "FACE_UP",
            "phase": "PHASED_IN",
        },
        identity_visible_to=set(executor.state.players),
    )
    executor.state.objects[token.object_id] = token
    executor.zones.register(token)
    executor._queue_etb(token)
    return token


def _choose_army(
    executor: Any,
    action: Action,
    choices: dict[str, Any],
) -> GameObject:
    armies = [
        obj
        for obj in _permanents(executor)
        if obj.controller == action.actor_id and "Army" in _subtypes(obj)
    ]
    if not armies:
        armies = [_create_zombie_army(executor, action)]

    requested = choices.get("amass_army_object_id")
    if requested is None:
        if len(armies) != 1:
            raise IllegalAction("amass requires an explicit Army choice when multiple Armies exist")
        selected = armies[0]
    else:
        requested_id = str(requested)
        matches = [army for army in armies if army.object_id == requested_id]
        if len(matches) != 1:
            raise IllegalAction("amass selected an unavailable Army")
        selected = matches[0]

    choice_event = executor._event(
        "AMASS_ARMY_CHOSEN",
        action,
        army_object_id=selected.object_id,
    )
    executor.state.choices.append(
        Choice(
            executor.identity.new_id("choice"),
            action.actor_id,
            "AMASS_ARMY",
            selected.object_id,
            choice_event.event_id,
        )
    )
    return selected


def apply_amass_and_hexproof(
    executor: Any,
    action: Action,
    effect: dict[str, Any],
    targets: list[GameObject],
    choices: dict[str, Any],
) -> None:
    """Amass Zombies, then protect the player and controlled permanents until cleanup."""

    if targets:
        raise IllegalAction("amass and hexproof does not use targets")
    amount = int(effect.get("amass", 0))
    if amount < 0:
        raise IllegalAction("amass amount cannot be negative")

    army = _choose_army(executor, action, choices)
    power = army.current_characteristics.get("power")
    toughness = army.current_characteristics.get("toughness")
    if not isinstance(power, int) or not isinstance(toughness, int):
        raise IllegalAction("amass requires an Army with numeric power and toughness")
    army.counters["+1/+1"] = army.counters.get("+1/+1", 0) + amount
    army.current_characteristics["power"] = power + amount
    army.current_characteristics["toughness"] = toughness + amount
    executor._event(
        "AMASS_COUNTERS_ADDED",
        action,
        army_object_id=army.object_id,
        amount=amount,
    )

    duration = str(effect.get("duration", "END_OF_TURN"))
    if duration != "END_OF_TURN":
        raise IllegalAction("exact-deck hexproof supports only end-of-turn duration")
    executor.state.continuous_effects.append(
        {
            "kind": HEXPROOF_EFFECT_KIND,
            "player_id": action.actor_id,
            "protect_player": True,
            "protect_controlled_permanents": True,
            "duration": duration,
            "source_action_id": action.action_id,
        }
    )
    executor._event(
        "PLAYER_AND_CONTROLLED_PERMANENTS_GAINED_HEXPROOF",
        action,
        player_id=action.actor_id,
        duration=duration,
    )
