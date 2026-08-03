"""Interaction, continuous-duration, and exile Phase B effects."""

from __future__ import annotations

from typing import Any

from mtg_kernel.errors import IllegalAction
from mtg_kernel.models import Action, GameObject, ObjectKind, Zone
from mtg_kernel.phase_b_runtime_helpers import (
    _counter_to,
    _mark_eot_original,
    _spell_satisfies,
)


def apply_effect_interaction(
    self: Any,
    source: GameObject | None,
    action: Action,
    effect: dict[str, Any],
    targets: list[GameObject],
    choices: dict[str, Any],
) -> bool:
    del source, choices
    kind = str(effect.get("kind", "NONE"))

    if kind == "GRANT_HASTE":
        if len(targets) != 1:
            raise IllegalAction("haste effect requires one target")
        target = targets[0]
        _mark_eot_original(target)
        keywords = set(str(value) for value in target.current_characteristics.get("keywords", ()))
        keywords.add("Haste")
        target.current_characteristics["keywords"] = sorted(keywords)
        self._event("KEYWORD_GRANTED", action, object_id=target.object_id, keyword="Haste")
        return True

    if kind == "MODIFY_POWER_TOUGHNESS":
        if len(targets) != 1:
            raise IllegalAction("power/toughness effect requires one target")
        target = targets[0]
        power = target.current_characteristics.get("power")
        toughness = target.current_characteristics.get("toughness")
        if not isinstance(power, int) or not isinstance(toughness, int):
            raise IllegalAction("power/toughness modification requires numeric characteristics")
        _mark_eot_original(target)
        target.current_characteristics["power"] = power + int(effect.get("power", 0))
        target.current_characteristics["toughness"] = toughness + int(effect.get("toughness", 0))
        self._event("POWER_TOUGHNESS_MODIFIED", action, object_id=target.object_id)
        return True

    if kind == "SWITCH_POWER_TOUGHNESS":
        for target in targets:
            power = target.current_characteristics.get("power")
            toughness = target.current_characteristics.get("toughness")
            if not isinstance(power, int) or not isinstance(toughness, int):
                raise IllegalAction("switch effect requires numeric power and toughness")
            _mark_eot_original(target)
            target.current_characteristics["power"] = toughness
            target.current_characteristics["toughness"] = power
        self._event("POWER_TOUGHNESS_SWITCHED", action, count=len(targets))
        return True

    if kind in {"COUNTER", "COUNTER_IF"}:
        if len(targets) != 1:
            raise IllegalAction("counter effect requires one target")
        target = targets[0]
        if kind == "COUNTER" or _spell_satisfies(target, dict(effect.get("predicate", {}))):
            _counter_to(self, target, action, Zone.GRAVEYARD)
        return True

    if kind == "COUNTER_TARGETING_CONTROLLER":
        if len(targets) != 1:
            raise IllegalAction("Stormtammer counter requires one stack target")
        target = targets[0]
        created = self._created_action(target)
        protected = action.actor_id
        targets_controller = any(
            ref.object_id in self.state.objects
            and (
                self.state.objects[ref.object_id].controller == protected
                or self.state.objects[ref.object_id].owner == protected
            )
            for ref in created.targets
        )
        if not targets_controller:
            raise IllegalAction("target spell or ability does not target the protected player")
        _counter_to(self, target, action, Zone.GRAVEYARD)
        return True

    if kind == "EXILE_THEN_CONTROLLER_DRAWS":
        if len(targets) != 1:
            raise IllegalAction("exile-and-draw requires one target")
        controller = targets[0].controller or targets[0].owner
        self.zones.move(
            targets[0].object_id,
            Zone.EXILE,
            kind,
            self._event("OBJECT_EXILED", action, object_id=targets[0].object_id),
        )
        if controller is not None:
            self.draw_card(controller, action=action)
        return True

    if kind == "EXILE_CREATURES_CREATE_BOARS":
        for target in targets:
            controller = target.controller or target.owner
            self.zones.move(
                target.object_id,
                Zone.EXILE,
                kind,
                self._event("OBJECT_EXILED", action, object_id=target.object_id),
            )
            if controller is None:
                continue
            event = self._event("TOKEN_CREATED", action, controller=controller, token_name="Boar")
            token = GameObject(
                self.identity.new_id("object"),
                ObjectKind.TOKEN_OBJECT,
                Zone.BATTLEFIELD,
                controller,
                controller,
                created_by_event_id=event.event_id,
                current_characteristics={
                    "name": "Boar",
                    "card_types": ["Creature"],
                    "subtypes": ["Boar"],
                    "colors": ["G"],
                    "keywords": [],
                    "abilities": [],
                    "power": 2,
                    "toughness": 2,
                },
                permanent_status={
                    "tap": "UNTAPPED",
                    "face": "FACE_UP",
                    "phase": "PHASED_IN",
                },
                identity_visible_to=set(self.state.players),
            )
            self.state.objects[token.object_id] = token
            self.zones.register(token)
        return True

    if kind == "EXILE_ALL_GRAVEYARDS":
        for obj in list(self.state.objects.values()):
            if not obj.retired and obj.zone is Zone.GRAVEYARD:
                self.zones.move(
                    obj.object_id,
                    Zone.EXILE,
                    kind,
                    self._event("GRAVEYARD_CARD_EXILED", action, object_id=obj.object_id),
                )
        return True

    return False
