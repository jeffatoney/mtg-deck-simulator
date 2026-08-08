"""Targeted rules-conformance guards for frozen-deck interaction choices.

These guards close interaction-contract gaps that are purely rules-semantic and do
not require the engine to invent a strategic preference. They intentionally fail
closed when the Comprehensive Rules require an explicit player choice.
"""

from __future__ import annotations

from typing import Any, Callable, cast

import mtg_kernel.land_actions as land_actions
from mtg_kernel.errors import IllegalAction
from mtg_kernel.mana import parse_mana_cost, pay_mana
from mtg_kernel.models import Action, Choice, GameObject, ObjectKind, Zone
from mtg_kernel.specs import base_characteristics

_ORIGINALS: dict[str, Callable[..., Any]] = {}


def _resolved_face(executor: Any, card_object_id: str, face: int | None) -> int:
    card = executor.state.objects.get(card_object_id)
    if card is None or card.retired or card.ceased_to_exist:
        return 0 if face is None else face
    faces = card.current_characteristics.get("faces", ())
    if face is None and isinstance(faces, (list, tuple)) and len(faces) > 1:
        raise IllegalAction("cast path requires an explicit card face")
    return 0 if face is None else face


def _spell_context(
    executor: Any,
    card_object_id: str,
    face: int,
    mode: str | None,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    card = executor.state.objects.get(card_object_id)
    if card is None or card.retired or card.ceased_to_exist:
        return None
    face_data = executor._selected_face(card, face)
    ability = executor._selected_spell_ability(face_data, mode)
    return face_data, ability


def _spell_effect(
    executor: Any,
    card_object_id: str,
    face: int,
    mode: str | None,
) -> dict[str, Any] | None:
    context = _spell_context(executor, card_object_id, face, mode)
    if context is None:
        return None
    _, ability = context
    effect = ability.get("effect", {})
    return dict(effect) if isinstance(effect, dict) else None


def _spell_requires_x(
    executor: Any,
    card_object_id: str,
    face: int,
    mode: str | None,
) -> bool:
    context = _spell_context(executor, card_object_id, face, mode)
    if context is None:
        return False
    face_data, ability = context
    cost_text = str(ability.get("alternative_cost", face_data.get("mana_cost", ""))).upper()
    effect = ability.get("effect", {})
    effect_data = dict(effect) if isinstance(effect, dict) else {}
    return (
        "{X}" in cost_text
        or bool(effect_data.get("target_count_from_x"))
        or bool(effect_data.get("amount_from_x"))
    )


def _spell_has_variable_target_count(
    executor: Any,
    card_object_id: str,
    face: int,
    mode: str | None,
) -> bool:
    context = _spell_context(executor, card_object_id, face, mode)
    if context is None:
        return False
    _, ability = context
    schema = dict(ability.get("target_schema", {}))
    minimum = int(schema.get("min", 0))
    maximum = schema.get("max", 0)
    return maximum is None or int(maximum) != minimum


def _cast(
    self: Any,
    actor: str,
    card_object_id: str,
    targets: tuple[Any, ...] | None = None,
    face: int | None = None,
    x_value: int | None = None,
    mode: str | None = None,
    choices: dict[str, Any] | None = None,
    *,
    _record: bool = True,
) -> GameObject:
    """Require represented cast-time declarations before the spell is proposed."""

    selected_choices = dict(choices or {})
    resolved_face = _resolved_face(self, card_object_id, face)
    if _spell_has_variable_target_count(self, card_object_id, resolved_face, mode) and targets is None:
        raise IllegalAction("variable target count requires an explicit target selection")
    resolved_targets = () if targets is None else targets
    if _spell_requires_x(self, card_object_id, resolved_face, mode) and x_value is None:
        raise IllegalAction("X requires an explicit nonnegative integer declaration")
    resolved_x = 0 if x_value is None else x_value

    effect = _spell_effect(self, card_object_id, resolved_face, mode)
    if effect is not None and str(effect.get("kicker", "")):
        if "kicked" not in selected_choices or not isinstance(selected_choices["kicked"], bool):
            raise IllegalAction("kicker requires an explicit boolean declaration")
    return cast(
        GameObject,
        _ORIGINALS["cast"](
            self,
            actor,
            card_object_id,
            resolved_targets,
            resolved_face,
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


def _activate_with_qualifying_sacrifice(
    self: Any,
    actor: str,
    source_id: str,
    ability_id: str,
    targets: tuple[Any, ...],
    choices: dict[str, Any],
    subtype: str,
    *,
    _record: bool,
) -> GameObject | None:
    """Run the activation pipeline with the selected permanent paid in cost order."""

    self._ensure_active()
    before = self._begin_atomic()
    try:
        source = self.state.objects[source_id]
        if source.retired or source.ceased_to_exist or source.zone is not Zone.BATTLEFIELD:
            raise IllegalAction("activated ability source is unavailable")
        if source.controller != actor:
            raise IllegalAction("a player may activate only an ability they control")
        selected = self._ability_by_id(source, ability_id)
        if self.state.turn.priority_holder_id != actor:
            raise IllegalAction("the activating player does not have priority")
        mana_ability = bool(selected.get("mana_ability"))
        if selected.get("restriction") == "SOURCE_ATTACKING" and not source.current_characteristics.get(
            "attacking", False
        ):
            raise IllegalAction("this ability may be activated only while the source attacks")

        schema = dict(
            selected.get("target_schema", {"kind": "NONE", "min": 0, "max": 0, "unique": True})
        )
        self._validate_targets(actor, targets, schema)
        cost = dict(selected.get("cost", {}))
        mana_cost = parse_mana_cost(str(cost.get("mana", "")))
        payment = pay_mana(self.state.players[actor].mana_pool, mana_cost)
        if cost.get("tap"):
            status = source.permanent_status
            if status is None or status.get("tap") != "UNTAPPED":
                raise IllegalAction("tap cost requires an untapped permanent")
            status["tap"] = "TAPPED"

        action = Action(
            self.identity.new_id("action"),
            "ACTIVATE",
            actor,
            source_id,
            targets,
            (),
            0,
            {"mana": payment, "cost": mana_cost},
            {"ability_id": ability_id, "target_schema": schema, "choices": choices},
        )
        self.state.actions.append(action)
        self.state.target_records.append(
            {
                "action_id": action.action_id,
                "targets": [self._target_data(target) for target in targets],
            }
        )
        activated_event = self._event("ABILITY_ACTIVATED", action, ability_id=ability_id)
        ability_object: GameObject | None = None
        if not mana_ability:
            ability_object = GameObject(
                self.identity.new_id("object"),
                ObjectKind.ACTIVATED_ABILITY,
                Zone.STACK,
                None,
                actor,
                source_object_id=source_id,
                created_by_event_id=activated_event.event_id,
                current_characteristics={"ability": selected},
                was_cast=False,
            )
            self.state.objects[ability_object.object_id] = ability_object
            self.zones.register(ability_object)
            self.state.pending_actions.append(action.action_id)

        discard_count = int(cost.get("discard", 0))
        discard_ids = list(choices.get("discard_ids", []))
        if len(discard_ids) != discard_count:
            raise IllegalAction("activation requires explicit discard-cost choices")
        for discard_id in discard_ids:
            self._discard_card(actor, str(discard_id), action)

        selected_id = choices.get("additional_sacrifice_object_id")
        if not isinstance(selected_id, str):
            raise IllegalAction("additional sacrifice cost requires an explicit permanent choice")
        _qualifying_sacrifice(self, actor, selected_id, subtype)
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

        if mana_ability:
            self._apply_effect(None, action, dict(selected.get("effect", {})), [], choices)
            self.check_state_based_actions()
        else:
            self.put_waiting_triggers_on_stack()
            self.state.turn.priority_holder_id = actor
            self.state.turn.consecutive_priority_passes = 0
        if _record:
            self._record_command(
                "activate",
                actor=actor,
                source_id=source_id,
                ability_id=ability_id,
                targets=[self._target_data(target) for target in targets],
                choices=choices,
            )
        return ability_object
    except Exception:
        self._rollback(before)
        raise


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
    return _activate_with_qualifying_sacrifice(
        self,
        actor,
        source_id,
        ability_id,
        targets,
        selected_choices,
        subtype,
        _record=_record,
    )


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
        raw_card_types = characteristics.get("card_types", ())
        if not isinstance(raw_card_types, (list, tuple, set)):
            raise IllegalAction("manifested card has invalid printed card types")
        card_types = {str(value) for value in raw_card_types}
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
        return cast(GameObject, obj)
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
