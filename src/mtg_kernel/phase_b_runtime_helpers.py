"""Shared state-mutation helpers for the Phase B runtime."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mtg_kernel.errors import IllegalAction
from mtg_kernel.models import Action, GameObject, TargetRef, Zone
from mtg_kernel.phase_b_runtime_support import _ORIGINALS, _subtypes, _types


def _permanents(executor: Any) -> list[GameObject]:
    return [
        obj
        for obj in executor.state.objects.values()
        if not obj.retired and not obj.ceased_to_exist and executor._is_permanent(obj)
    ]


def _return_to_hand(executor: Any, obj: GameObject, action: Action, cause: str) -> None:
    executor.zones.move(
        obj.object_id,
        Zone.HAND,
        cause,
        executor._event("OBJECT_RETURNED_TO_HAND", action, object_id=obj.object_id),
    )


def _attached_umbra(executor: Any, target: GameObject) -> GameObject | None:
    for aura in _permanents(executor):
        if aura.attached_to_ref is None or aura.attached_to_ref.object_id != target.object_id:
            continue
        if any(
            ability.get("kind") == "REPLACEMENT"
            and ability.get("event") == "ENCHANTED_CREATURE_DESTROY"
            and dict(ability.get("effect", {})).get("kind") == "UMBRA_ARMOR"
            for ability in aura.current_characteristics.get("abilities", ())
        ):
            return aura
    return None


def _destroy(executor: Any, obj: GameObject, action: Action, cause: str) -> None:
    aura = _attached_umbra(executor, obj)
    if aura is not None:
        event = executor._event(
            "UMBRA_ARMOR_REPLACED_DESTROY",
            action,
            protected_object_id=obj.object_id,
            aura_object_id=aura.object_id,
        )
        executor.zones.move(aura.object_id, Zone.GRAVEYARD, "UMBRA_ARMOR", event)
        obj.marked_damage = 0
        return
    executor.zones.move(
        obj.object_id,
        Zone.GRAVEYARD,
        cause,
        executor._event("PERMANENT_DESTROYED", action, object_id=obj.object_id),
    )


def _counter_to(executor: Any, target: GameObject, action: Action, destination: Zone) -> None:
    if target.zone is not Zone.STACK:
        raise IllegalAction("counter effect requires a stack target")
    created = executor._created_action(target)
    event = executor._event(
        "STACK_OBJECT_COUNTERED",
        action,
        object_id=target.object_id,
        destination=destination.value,
    )
    executor.zones.move(
        target.object_id,
        destination if target.component_card_instance_ids else Zone.NONE,
        "COUNTERED",
        event,
    )
    executor._remove_pending_action(created)


def _spell_satisfies(target: GameObject, predicate: Mapping[str, Any]) -> bool:
    types = _types(target)
    colors = set(str(value) for value in target.current_characteristics.get("colors", ()))
    mana_value = int(target.current_characteristics.get("mana_value", 0))
    if "mana_value_lte" in predicate and mana_value > int(predicate["mana_value_lte"]):
        return False
    if "colors_any" in predicate and not colors.intersection(
        str(value) for value in predicate.get("colors_any", ())
    ):
        return False
    if "card_types_any" in predicate and not types.intersection(
        str(value) for value in predicate.get("card_types_any", ())
    ):
        return False
    if "card_types_none" in predicate and types.intersection(
        str(value) for value in predicate.get("card_types_none", ())
    ):
        return False
    if predicate.get("cast_from_not_owner_hand"):
        return str(target.current_characteristics.get("cast_from_zone", "")) != Zone.HAND.value
    return True


def _untap(executor: Any, objects: Sequence[GameObject], action: Action) -> None:
    for obj in objects:
        if obj.permanent_status is None:
            raise IllegalAction("untap effect requires a permanent")
        obj.permanent_status["tap"] = "UNTAPPED"
        executor._event("PERMANENT_UNTAPPED", action, object_id=obj.object_id)


def _mark_eot_original(obj: GameObject) -> dict[str, Any]:
    existing = obj.current_characteristics.get("until_end_of_turn")
    values: dict[str, Any]
    if isinstance(existing, dict):
        values = existing
    else:
        values = {}
        obj.current_characteristics["until_end_of_turn"] = values
    values.setdefault("original_power", obj.current_characteristics.get("power"))
    values.setdefault("original_toughness", obj.current_characteristics.get("toughness"))
    values.setdefault("original_keywords", list(obj.current_characteristics.get("keywords", ())))
    return values


def _draw_card(self: Any, player_id: str, *, action: Action | None = None) -> GameObject | None:
    moved = _ORIGINALS["draw_card"](self, player_id, action=action)
    if moved is not None and not isinstance(moved, GameObject):
        raise TypeError("draw_card returned a non-GameObject value")
    if moved is None or self.state.terminal.status != "ACTIVE":
        return moved
    event = self.state.events[-1]
    hints = dict(action.metadata.get("choices", {})) if action is not None else {}
    for source in _permanents(self):
        if source.controller != player_id:
            continue
        for ability in source.current_characteristics.get("abilities", ()):
            if ability.get("kind") == "TRIGGERED" and ability.get("trigger") == "CONTROLLER_DRAWS":
                self._queue_trigger(source, dict(ability), {"draw_event_id": event.event_id}, hints)
    self.put_waiting_triggers_on_stack()
    return moved


def _cast(
    self: Any,
    actor: str,
    card_object_id: str,
    targets: tuple[TargetRef, ...] = (),
    face: int = 0,
    x_value: int = 0,
    mode: str | None = None,
    choices: dict[str, Any] | None = None,
    *,
    _record: bool = True,
) -> GameObject:
    choices = dict(choices or {})
    spell = _ORIGINALS["cast"](
        self,
        actor,
        card_object_id,
        targets,
        face,
        x_value,
        mode,
        choices,
        _record=_record,
    )
    if not isinstance(spell, GameObject):
        raise TypeError("cast returned a non-GameObject value")
    is_pirate = "Pirate" in _subtypes(spell)
    for source in _permanents(self):
        if source.controller != actor:
            continue
        for ability in source.current_characteristics.get("abilities", ()):
            if ability.get("trigger") == "CONTROLLER_CASTS_PIRATE" and is_pirate:
                self._queue_trigger(
                    source,
                    dict(ability),
                    {"spell_object_id": spell.object_id},
                    choices,
                )
    self.put_waiting_triggers_on_stack()
    return spell


def _check_state_based_actions(self: Any) -> None:
    for obj in _permanents(self):
        for ability in obj.current_characteristics.get("abilities", ()):
            effect = dict(ability.get("effect", {}))
            if (
                ability.get("kind") == "STATIC"
                and effect.get("kind") == "HAND_SIZE_POWER_TOUGHNESS"
            ):
                player_id = obj.controller or obj.owner
                if player_id is not None:
                    count = len(self.state.zones.get(f"{Zone.HAND.value}:{player_id}", ()))
                    obj.current_characteristics["power"] = count
                    obj.current_characteristics["toughness"] = count
    if not self._resolution_depth:
        for obj in list(_permanents(self)):
            if "Planeswalker" not in _types(obj):
                continue
            loyalty = obj.counters.get("LOYALTY")
            if isinstance(loyalty, int) and loyalty <= 0:
                self.zones.move(
                    obj.object_id,
                    Zone.GRAVEYARD,
                    "STATE_BASED_PLANESWALKER_LOYALTY",
                    self._event("SBA_PLANESWALKER_TO_GRAVEYARD", object_id=obj.object_id),
                )
    for obj in list(_permanents(self)):
        toughness = obj.current_characteristics.get("toughness")
        if "Creature" in _types(obj) and isinstance(toughness, int) and toughness > 0:
            if obj.marked_damage >= toughness:
                aura = _attached_umbra(self, obj)
                if aura is not None:
                    event = self._event(
                        "UMBRA_ARMOR_REPLACED_LETHAL_DESTRUCTION",
                        protected_object_id=obj.object_id,
                        aura_object_id=aura.object_id,
                    )
                    self.zones.move(aura.object_id, Zone.GRAVEYARD, "UMBRA_ARMOR", event)
                    obj.marked_damage = 0
    _ORIGINALS["check_state_based_actions"](self)


def _cleanup_iteration(self: Any, discard_ids: tuple[str, ...]) -> None:
    for obj in self.state.objects.values():
        values = obj.current_characteristics.get("until_end_of_turn")
        if not isinstance(values, dict):
            continue
        if "original_power" in values:
            obj.current_characteristics["power"] = values["original_power"]
        if "original_toughness" in values:
            obj.current_characteristics["toughness"] = values["original_toughness"]
        if "original_keywords" in values:
            obj.current_characteristics["keywords"] = list(values["original_keywords"])
    _ORIGINALS["cleanup_iteration"](self, discard_ids)
