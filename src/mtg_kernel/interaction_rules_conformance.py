"""Targeted rules-conformance guards for frozen-deck interaction choices.

These guards close interaction-contract gaps that are purely rules-semantic and do
not require the engine to invent a strategic preference.  They intentionally fail
closed when the Comprehensive Rules require an explicit player choice.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, cast

import mtg_kernel.land_actions as land_actions
from mtg_kernel.errors import IllegalAction
from mtg_kernel.models import Choice, GameObject, Zone

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


def _cast(
    self: Any,
    actor: str,
    card_object_id: str,
    targets: tuple[Any, ...] = (),
    face: int = 0,
    x_value: int = 0,
    mode: str | None = None,
    choices: dict[str, Any] | None = None,
    *,
    _record: bool = True,
) -> GameObject:
    """Require represented additional-cost declarations at cast proposal time."""

    selected_choices = dict(choices or {})
    effect = _spell_effect(self, card_object_id, face, mode)
    if effect is not None and str(effect.get("kicker", "")):
        if "kicked" not in selected_choices or not isinstance(
            selected_choices["kicked"], bool
        ):
            raise IllegalAction("kicker requires an explicit boolean declaration")
    return cast(
        GameObject,
        _ORIGINALS["cast"](
            self,
            actor,
            card_object_id,
            targets,
            face,
            x_value,
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
        raise IllegalAction(
            f"additional activation cost requires a controlled {subtype} permanent"
        )
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


def install_interaction_rules_conformance(executor_class: type[Any]) -> None:
    """Install narrow fail-closed guards after the Phase B runtime extensions."""

    if getattr(executor_class, "_interaction_rules_conformance_installed", False):
        return
    _ORIGINALS.update(
        {
            "cast": executor_class.cast,
            "activate": executor_class.activate,
            "play_land": land_actions.play_land,
        }
    )
    executor_class.cast = _cast
    executor_class.activate = _activate
    setattr(land_actions, "play_land", _play_land)
    executor_class._interaction_rules_conformance_installed = True


__all__ = ["install_interaction_rules_conformance"]
