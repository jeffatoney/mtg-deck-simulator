"""Targeted rules-conformance guards for frozen-deck interaction choices.

These guards close interaction-contract gaps that are purely rules-semantic and do
not require the engine to invent a strategic preference. They intentionally fail
closed when the Comprehensive Rules require an explicit player choice.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, cast

import mtg_kernel.land_actions as land_actions
from mtg_kernel.errors import IllegalAction
from mtg_kernel.mana import parse_mana_cost, pay_mana
from mtg_kernel.models import Action, Choice, GameObject, Zone
from mtg_kernel.specs import base_characteristics

_ORIGINALS: dict[str, Callable[..., Any]] = {}


def _spell_effect(
    executor: Any,
    card_object_id: str,
    face: int,
    mode: str | None,
) -> dict[str, Any] | None:
    card = executor.state.objects.get(card_object_id)
    if card is None or card.retired or card.ceased_to_exist:
        return None
    face_data = executor._selected_face(card, face)
    ability = executor._selected_spell_ability(face_data, mode)
    effect = ability.get("effect", {})
    return dict(effect) if isinstance(effect, dict) else None


def _spell_requires_x(
    executor: Any,
    card_object_id: str,
    face: int,
    mode: str | None,
) -> bool:
    card = executor.state.objects.get(card_object_id)
    if card is None or card.retired or card.ceased_to_exist:
        return False
    face_data = executor._selected_face(card, face)
    ability = executor._selected_spell_ability(face_data, mode)
    cost_text = str(ability.get("alternative_cost", face_data.get("mana_cost", ""))).upper()
    effect = ability.get("effect", {})
    effect_data = dict(effect) if isinstance(effect, dict) else {}
    return (
        "{X}" in cost_text
        or bool(effect_data.get("target_count_from_x"))
        or bool(effect_data.get("amount_from_x"))
    )


def _cast(
    self: Any,
    actor: str,
    card_object_id: str,
    targets: tuple[Any, ...] = (),
    face: int = 0,
    x_value: int | None = None,
    mode: str | None = None,
    choices: dict[str, Any] | None = None,
    *,
    _record: bool = True,
) -> GameObject:
    """Require represented cast-time declarations before the spell is proposed."""

    selected_choices = dict(choices or {})
    if _spell_requires_x(self, card_object_id, face, mode) and x_value is None:
        raise IllegalAction("X requires an explicit nonnegative integer declaration")
    resolved_x = 0 if x_value is None else x_value

    effect = _spell_effect(self, card_object_id, face, mode)
    if effect is not None and str(effect.get("kicker", "")):
        if "kicked" not in selected_choices or not isinstance(selected_choices["kicked"], bool):
            raise IllegalAction("kicker requires an explicit boolean declaration")
    return cast(
        GameObject,
        _ORIGINALS["cast"](
            self,
            actor,
            card_object_id,
            targets,
            face,
            resolved_x,
            mode,
            selected_choices,
            _record=_record,
        ),
    )


def _additional_sacrifice_subtype(ability: dict[str, Any]) -> str:
    effect = ability.get("effect", {})
    if not isinstance(effect, dict):
        return ""
    return str(effect.get("additional_sacrifice_subtype", ""))


def _qualifying_sacrifice(
    executor: Any,
    actor: str,
    object_id: str,
    subtype: str,
) -> GameObject:
    candidate = executor.state.objects.get(object_id)
    if (
        candidate is None
        or candidate.retired
        or candidate.ceased_to_exist
        or not executor._is_permanent(candidate)
        or candidate.controller != actor
        or subtype not in candidate.current_characteristics.get("subtypes", ())
    ):
        raise IllegalAction(f"additional activation cost requires a controlled {subtype} permanent")
    return cast(GameObject, candidate)


def _patched_without_source_sacrifice(
    source: GameObject,
    ability_id: str,
) -> tuple[list[Any], int, dict[str, Any]]:
    abilities = list(source.current_characteristics.get("abilities", ()))
    matches = [
        index
        for index, ability in enumerate(abilities)
        if isinstance(ability, dict)
        and ability.get("ability_id") == ability_id
        and ability.get("kind") == "ACTIVATED"
    ]
    if len(matches) != 1:
        raise IllegalAction("additional-sacrifice activated ability is unavailable")
    index = matches[0]
    original = dict(abilities[index])
    patched = deepcopy(original)
    cost = dict(patched.get("cost", {}))
    cost["sacrifice_source"] = False
    patched["cost"] = cost
    abilities[index] = patched
    source.current_characteristics["abilities"] = abilities
    return abilities, index, original


def _activate(
    self: Any,
    actor: str,
    source_id: str,
    ability: str | dict[str, Any],
    targets: tuple[Any, ...] = (),
    choices: dict[str, Any] | None = None,
    *,
    _record: bool = True,
) -> GameObject | None:
    """Pay represented qualifying-permanent sacrifice costs explicitly."""

    source = self.state.objects.get(source_id)
    if source is None or source.retired or source.ceased_to_exist:
        return cast(
            GameObject | None,
            _ORIGINALS["activate"](
                self,
                actor,
                source_id,
                ability,
                targets,
                choices,
                _record=_record,
            ),
        )

    ability_id = str(ability.get("ability_id")) if isinstance(ability, dict) else ability
    selected = self._ability_by_id(source, ability_id)
    subtype = _additional_sacrifice_subtype(selected)
    if not subtype:
        return cast(
            GameObject | None,
            _ORIGINALS["activate"](
                self,
                actor,
                source_id,
                ability,
                targets,
                choices,
                _record=_record,
            ),
        )

    selected_choices = dict(choices or {})
    selected_id = selected_choices.get("additional_sacrifice_object_id")
    if not isinstance(selected_id, str):
        raise IllegalAction("additional sacrifice cost requires an explicit permanent choice")
    _qualifying_sacrifice(self, actor, selected_id, subtype)

    before = self._begin_atomic()
    try:
        _, index, original_ability = _patched_without_source_sacrifice(source, ability_id)
        ability_object = cast(
            GameObject | None,
            _ORIGINALS["activate"](
                self,
                actor,
                source_id,
                ability_id,
                targets,
                selected_choices,
                _record=_record,
            ),
        )

        current_source = self.state.objects.get(source_id)
        if current_source is not None and not current_source.retired:
            current_abilities = list(current_source.current_characteristics.get("abilities", ()))
            current_abilities[index] = original_ability
            current_source.current_characteristics["abilities"] = current_abilities

        action = next(
            (
                candidate
                for candidate in reversed(self.state.actions)
                if candidate.kind == "ACTIVATE"
                and candidate.actor_id == actor
                and candidate.source_object_id == source_id
                and candidate.metadata.get("ability_id") == ability_id
            ),
            None,
        )
        if action is None:
            raise IllegalAction("additional sacrifice cost has no activation action")

        choice_event = self._event(
            "ADDITIONAL_SACRIFICE_CHOSEN",
            action,
            object_id=selected_id,
            required_subtype=subtype,
            timing="COST_PAYMENT",
        )
        self.state.choices.append(
            Choice(
                self.identity.new_id("choice"),
                actor,
                "ADDITIONAL_SACRIFICE_SELECTION",
                selected_id,
                choice_event.event_id,
            )
        )
        self.zones.move(
            selected_id,
            Zone.GRAVEYARD,
            "ACTIVATION_COST_SACRIFICE",
            self._event(
                "PERMANENT_SACRIFICED",
                action,
                object_id=selected_id,
                required_subtype=subtype,
            ),
        )
        return ability_object
    except Exception:
        self._rollback(before)
        raise


def _play_land(
    executor: Any,
    actor: str,
    card_object_id: str,
    choices: dict[str, Any] | None = None,
    *,
    record: bool = True,
) -> GameObject:
    """Require an explicit reveal-or-decline replacement-effect choice."""

    selected_choices = dict(choices or {})
    card = executor.state.objects.get(card_object_id)
    if card is not None and not card.retired and not card.ceased_to_exist:
        has_reveal_choice = any(
            isinstance(ability, dict)
            and ability.get("kind") == "REPLACEMENT"
            and ability.get("event") == "ENTERS_BATTLEFIELD"
            and isinstance(ability.get("effect"), dict)
            and ability["effect"].get("kind") == "REVEAL_OR_ENTER_TAPPED"
            for ability in card.current_characteristics.get("abilities", ())
        )
        if has_reveal_choice and "reveal_object_id" not in selected_choices:
            raise IllegalAction("land entry requires an explicit reveal-or-decline choice")
    return cast(
        GameObject,
        _ORIGINALS["play_land"](
            executor,
            actor,
            card_object_id,
            selected_choices,
            record=record,
        ),
    )


def _turn_manifest_face_up(
    self: Any,
    actor: str,
    object_id: str,
    *,
    _record: bool = True,
) -> GameObject:
    """Perform rule 701.40b's manifest face-up special action."""

    self._ensure_active()
    before = self._begin_atomic()
    try:
        if self.state.turn.priority_holder_id != actor:
            raise IllegalAction("manifest face-up special action requires priority")
        obj = self.state.objects.get(object_id)
        if (
            obj is None
            or obj.retired
            or obj.ceased_to_exist
            or obj.zone is not Zone.BATTLEFIELD
            or not self._is_permanent(obj)
            or obj.controller != actor
        ):
            raise IllegalAction("manifest face-up special action requires a controlled permanent")
        status = obj.permanent_status
        if (
            status is None
            or status.get("face") != "FACE_DOWN"
            or obj.current_characteristics.get("manifested") is not True
        ):
            raise IllegalAction("permanent is not a face-down manifested card")
        if len(obj.component_card_instance_ids) != 1:
            raise IllegalAction("manifest face-up special action requires one physical card")

        instance = self.state.card_instances[obj.component_card_instance_ids[0]]
        spec = self.state.card_specs[instance.card_spec_id]
        characteristics = base_characteristics(spec, 0 if spec.faces else None)
        card_types = set(str(value) for value in characteristics.get("card_types", ()))
        mana_cost = str(characteristics.get("mana_cost", ""))
        if "Creature" not in card_types or not mana_cost:
            raise IllegalAction("manifested card cannot be turned face up by the manifest action")

        cost = parse_mana_cost(mana_cost)
        payment = pay_mana(self.state.players[actor].mana_pool, cost)
        action = Action(
            self.identity.new_id("action"),
            "MANIFEST_FACE_UP_SPECIAL_ACTION",
            actor,
            object_id,
            payments={"mana": payment, "cost": cost},
        )
        self.state.actions.append(action)

        obj.current_characteristics = characteristics
        status["face"] = "FACE_UP"
        obj.identity_visible_to = set(self.state.players)
        self.identity.validate_object_schema()
        self._event(
            "MANIFEST_TURNED_FACE_UP",
            action,
            object_id=object_id,
            payment=payment,
        )
        self.check_state_based_actions()
        if self.state.terminal.status == "ACTIVE":
            self.put_waiting_triggers_on_stack()
            self.state.turn.priority_holder_id = actor
            self.state.turn.consecutive_priority_passes = 0
        if _record:
            self._record_command("turn_manifest_face_up", actor=actor, object_id=object_id)
        return obj
    except Exception:
        self._rollback(before)
        raise


def _execute_replay_command(self: Any, command: dict[str, Any]) -> None:
    operation = str(command["operation"])
    if operation == "turn_manifest_face_up":
        arguments = dict(command.get("arguments", {}))
        _turn_manifest_face_up(
            self,
            str(arguments["actor"]),
            str(arguments["object_id"]),
            _record=False,
        )
        return
    _ORIGINALS["execute_replay_command"](self, command)


def install_interaction_rules_conformance(executor_class: type[Any]) -> None:
    """Install narrow fail-closed guards after the Phase B runtime extensions."""

    if getattr(executor_class, "_interaction_rules_conformance_installed", False):
        return
    _ORIGINALS.update(
        {
            "cast": executor_class.cast,
            "activate": executor_class.activate,
            "play_land": land_actions.play_land,
            "execute_replay_command": executor_class.execute_replay_command,
        }
    )
    executor_class.cast = _cast
    executor_class.activate = _activate
    setattr(executor_class, "turn_manifest_face_up", _turn_manifest_face_up)
    executor_class.execute_replay_command = _execute_replay_command
    setattr(land_actions, "play_land", _play_land)
    executor_class._interaction_rules_conformance_installed = True


__all__ = ["install_interaction_rules_conformance"]
