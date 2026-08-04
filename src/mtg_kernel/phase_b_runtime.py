"""Installer for exact-deck Phase B capabilities on the single public executor."""

from __future__ import annotations

from typing import Any, cast

from mtg_kernel.errors import IllegalAction, UnsupportedCapability
from mtg_kernel.models import Action, GameObject, ObjectKind, TargetRef, Zone
from mtg_kernel.phase_b_counter_validation import cast_with_counter_predicate
from mtg_kernel.phase_b_runtime_effects_common import apply_effect_common
from mtg_kernel.phase_b_runtime_effects_delayed import apply_effect_delayed
from mtg_kernel.phase_b_runtime_effects_interaction import apply_effect_interaction
from mtg_kernel.phase_b_runtime_effects_mana import apply_effect_mana
from mtg_kernel.phase_b_runtime_effects_manifest import apply_effect_manifest
from mtg_kernel.phase_b_runtime_effects_search import apply_effect_search
from mtg_kernel.phase_b_runtime_effects_selection import apply_effect_selection
from mtg_kernel.phase_b_runtime_helpers import (
    _check_state_based_actions,
    _cleanup_iteration,
    _draw_card,
)
from mtg_kernel.phase_b_runtime_support import _ORIGINALS, _is_permanent, _target_matches


def _apply_effect(
    self: Any,
    source: GameObject | None,
    action: Action,
    effect: dict[str, Any],
    targets: list[GameObject],
    choices: dict[str, Any],
) -> None:
    kind = str(effect.get("kind", "NONE"))
    if kind == "SACRIFICE_OBJECTS":
        for ref_data in effect.get("objects", ()):
            ref = self._target_from_data(dict(ref_data))
            try:
                resolved = self.identity.resolve_reference(ref)
            except IllegalAction:
                continue
            if (
                isinstance(resolved, GameObject)
                and self._is_permanent(resolved)
                and resolved.controller == action.actor_id
            ):
                self.zones.move(
                    resolved.object_id,
                    Zone.GRAVEYARD,
                    "DELAYED_SACRIFICE",
                    self._event("PERMANENT_SACRIFICED", action, object_id=resolved.object_id),
                )
        return
    if apply_effect_common(self, source, action, effect, targets, choices):
        return
    if apply_effect_delayed(self, source, action, effect, targets, choices):
        return
    if apply_effect_interaction(self, source, action, effect, targets, choices):
        return
    if apply_effect_mana(self, source, action, effect, targets, choices):
        return
    if apply_effect_manifest(self, source, action, effect, targets, choices):
        return
    if apply_effect_search(self, source, action, effect, targets, choices):
        return
    if apply_effect_selection(self, source, action, effect, targets, choices):
        return
    raise UnsupportedCapability(f"unsupported exact-deck effect primitive: {kind}")


def _copy_permanent_token(
    self: Any,
    original: GameObject,
    controller: str,
    cause_action: Action,
    *,
    haste: bool,
    delayed: str,
) -> GameObject:
    original_copy = _ORIGINALS["copy_permanent_token"]
    token = cast(
        GameObject,
        original_copy(
            self,
            original,
            controller,
            cause_action,
            haste=haste,
            delayed="" if delayed == "SACRIFICE_AT_NEXT_END_STEP" else delayed,
        ),
    )
    self._queue_etb(token)
    if delayed != "SACRIFICE_AT_NEXT_END_STEP":
        return token

    delayed_event = self._event("DELAYED_TRIGGER_CREATED", cause_action)
    trigger = GameObject(
        self.identity.new_id("object"),
        ObjectKind.TRIGGERED_ABILITY,
        Zone.NONE,
        None,
        controller,
        source_object_id=token.object_id,
        created_by_event_id=delayed_event.event_id,
        current_characteristics={
            "ability": {
                "ability_id": "electroduplicate:delayed-sacrifice",
                "kind": "TRIGGERED",
                "trigger": "NEXT_END_STEP",
                "target_schema": {"kind": "NONE", "min": 0, "max": 0, "unique": True},
                "effect": {
                    "kind": "SACRIFICE_OBJECTS",
                    "objects": [self._target_data(TargetRef(token.object_id))],
                },
            },
            "trigger_context": {},
            "choice_hints": {},
        },
        was_cast=False,
    )
    self.state.objects[trigger.object_id] = trigger
    self.state.delayed_triggers.append(trigger.object_id)
    return token


def _trigger_name(self: Any, object_id: str) -> str:
    trigger = self.state.objects.get(object_id)
    if trigger is None:
        return ""
    ability = trigger.current_characteristics.get("ability", {})
    return str(ability.get("trigger", "")) if isinstance(ability, dict) else ""


def _begin_step(
    self: Any,
    step: str,
    choices: dict[str, Any] | None = None,
    *,
    _record: bool = True,
) -> None:
    """Schedule exact delayed triggers and preserve indirect phasing."""

    original_begin_step = _ORIGINALS["begin_step"]
    step_choices = dict(choices or {})

    if step == "END":
        before = self._begin_atomic()
        delayed = list(self.state.delayed_triggers)
        due = [
            object_id for object_id in delayed if _trigger_name(self, object_id) == "NEXT_END_STEP"
        ]
        withheld = [object_id for object_id in delayed if object_id not in due]
        try:
            self.state.delayed_triggers = due
            original_begin_step(self, step, step_choices, _record=_record)
            self.state.delayed_triggers.extend(withheld)
        except Exception:
            self._rollback(before)
            raise
        return

    original_begin_step(self, step, step_choices, _record=_record)

    if step == "UPKEEP":
        due: list[str] = []
        remaining: list[str] = []
        for object_id in self.state.delayed_triggers:
            trigger = self.state.objects.get(object_id)
            context = (
                trigger.current_characteristics.get("trigger_context", {})
                if trigger is not None
                else {}
            )
            not_before_turn = (
                int(context.get("not_before_turn", self.state.turn.number))
                if isinstance(context, dict)
                else self.state.turn.number
            )
            if (
                _trigger_name(self, object_id) == "NEXT_UPKEEP"
                and self.state.turn.number >= not_before_turn
            ):
                due.append(object_id)
            else:
                remaining.append(object_id)
        self.state.delayed_triggers = remaining
        per_trigger = step_choices.get("delayed_trigger_choices", {})
        choice_map = per_trigger if isinstance(per_trigger, dict) else {}
        for object_id in due:
            trigger = self.state.objects[object_id]
            selected = choice_map.get(object_id, {})
            trigger.current_characteristics["choice_hints"] = (
                dict(selected) if isinstance(selected, dict) else {}
            )
            self.state.waiting_triggers.append(object_id)
        self.put_waiting_triggers_on_stack()
        return

    if step != "UNTAP":
        return
    for obj in self.state.objects.values():
        root_id = obj.current_characteristics.get("phased_out_with")
        if not isinstance(root_id, str) or obj.permanent_status is None:
            continue
        root = self.state.objects.get(root_id)
        root_status = root.permanent_status if root is not None else None
        root_phased_out = bool(root_status and root_status.get("phase") == "PHASED_OUT")
        obj.permanent_status["phase"] = "PHASED_OUT" if root_phased_out else "PHASED_IN"
        if not root_phased_out:
            obj.current_characteristics.pop("phased_out_with", None)


def install_phase_b_runtime(executor_class: type[Any]) -> None:
    """Install explicit exact-deck extensions without creating a second executor."""

    if getattr(executor_class, "_phase_b_runtime_installed", False):
        return
    _ORIGINALS.update(
        {
            "target_matches": executor_class._target_matches,
            "is_permanent": executor_class._is_permanent,
            "apply_effect": executor_class._apply_effect,
            "draw_card": executor_class.draw_card,
            "cast": executor_class.cast,
            "copy_permanent_token": executor_class.copy_permanent_token,
            "check_state_based_actions": executor_class.check_state_based_actions,
            "cleanup_iteration": executor_class._cleanup_iteration,
            "begin_step": executor_class.begin_step,
        }
    )
    executor_class._target_matches = _target_matches
    executor_class._is_permanent = staticmethod(_is_permanent)
    executor_class._apply_effect = _apply_effect
    executor_class.draw_card = _draw_card
    executor_class.cast = cast_with_counter_predicate
    executor_class.copy_permanent_token = _copy_permanent_token
    executor_class.check_state_based_actions = _check_state_based_actions
    executor_class._cleanup_iteration = _cleanup_iteration
    executor_class.begin_step = _begin_step
    executor_class._phase_b_runtime_installed = True
