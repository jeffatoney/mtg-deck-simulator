"""Rules-correct cast-time mode and target handling for Prismari Command."""

from __future__ import annotations

from typing import Any, Callable, cast

from mtg_kernel.errors import IllegalAction
from mtg_kernel.models import Action, Choice, GameObject, ObjectKind, TargetRef
from mtg_kernel.phase_b_runtime_effects_prismari import _draw_then_discard
from mtg_kernel.phase_b_runtime_helpers import _destroy
from mtg_kernel.phase_b_runtime_support import (
    _ensure_player_target_objects,
    _permanent_has_hexproof_from,
    _player_has_hexproof,
    _types,
)

PRISMARI_MODE_ORDER = (
    "DAMAGE",
    "DRAW_DISCARD",
    "CREATE_TREASURE",
    "DESTROY_ARTIFACT",
)
_PLAYER_ONLY_MODES = {"DRAW_DISCARD", "CREATE_TREASURE"}
_ORIGINALS: dict[str, Callable[..., Any]] = {}


def _effect_kind(
    executor: Any,
    card_object_id: str,
    face: int,
    mode: str | None,
) -> str:
    card = executor.state.objects.get(card_object_id)
    if card is None or card.retired or card.ceased_to_exist:
        return ""
    face_data = executor._selected_face(card, face)
    ability = executor._selected_spell_ability(face_data, mode)
    effect = ability.get("effect", {})
    return str(effect.get("kind", "")) if isinstance(effect, dict) else ""


def _selected_modes(choices: dict[str, Any]) -> tuple[str, str]:
    raw = choices.get("prismari_modes")
    if not isinstance(raw, (list, tuple)):
        raise IllegalAction("Prismari Command requires two explicit modes while casting")
    modes = tuple(str(value) for value in raw)
    if len(modes) != 2 or len(set(modes)) != 2:
        raise IllegalAction("Prismari Command requires exactly two distinct modes while casting")
    if not set(modes) <= set(PRISMARI_MODE_ORDER):
        raise IllegalAction("Prismari Command includes an unsupported mode")
    return cast(tuple[str, str], modes)


def _target_data(choices: dict[str, Any], mode: str) -> dict[str, Any]:
    raw_targets = choices.get("prismari_targets")
    if not isinstance(raw_targets, dict):
        raise IllegalAction("Prismari Command requires explicit targets while casting")
    raw_target = raw_targets.get(mode)
    if not isinstance(raw_target, dict):
        raise IllegalAction(
            f"Prismari Command mode {mode} requires an explicit target while casting"
        )
    return {str(key): value for key, value in raw_target.items()}


def _player_ref(executor: Any, actor: str, target: dict[str, Any]) -> TargetRef:
    player_id = target.get("player_id")
    if not isinstance(player_id, str) or player_id not in executor.state.players:
        raise IllegalAction("Prismari Command requires a legal player target")
    if not executor.state.players[player_id].in_game:
        raise IllegalAction("Prismari Command cannot target a player outside the game")
    if player_id != actor and _player_has_hexproof(executor, player_id):
        raise IllegalAction("Prismari Command player target has hexproof")
    proxies = _ensure_player_target_objects(executor)
    return TargetRef(proxies[player_id].object_id)


def _permanent_ref(
    executor: Any,
    actor: str,
    target: dict[str, Any],
    *,
    required_types: set[str],
) -> TargetRef:
    object_id = target.get("object_id")
    if not isinstance(object_id, str):
        raise IllegalAction("Prismari Command requires a legal permanent target")
    obj = executor.state.objects.get(object_id)
    if (
        obj is None
        or obj.retired
        or obj.ceased_to_exist
        or not executor._is_permanent(obj)
        or not _types(obj).intersection(required_types)
    ):
        raise IllegalAction("Prismari Command permanent target is illegal")
    if _permanent_has_hexproof_from(executor, actor, obj):
        raise IllegalAction("Prismari Command permanent target has hexproof")
    return TargetRef(object_id)


def _cast_target_ref(
    executor: Any,
    actor: str,
    mode: str,
    target: dict[str, Any],
) -> TargetRef:
    if mode in _PLAYER_ONLY_MODES:
        if set(target) != {"player_id"}:
            raise IllegalAction(f"Prismari Command mode {mode} requires exactly one player target")
        return _player_ref(executor, actor, target)
    if mode == "DESTROY_ARTIFACT":
        if set(target) != {"object_id"}:
            raise IllegalAction(
                "Prismari Command artifact mode requires exactly one artifact target"
            )
        return _permanent_ref(executor, actor, target, required_types={"Artifact"})
    if mode == "DAMAGE":
        if set(target) == {"player_id"}:
            return _player_ref(executor, actor, target)
        if set(target) == {"object_id"}:
            return _permanent_ref(
                executor,
                actor,
                target,
                required_types={"Creature", "Planeswalker", "Battle"},
            )
        raise IllegalAction("Prismari Command damage mode requires exactly one legal target")
    raise IllegalAction("Prismari Command mode dispatch failed")


def _replace_cast_action(
    executor: Any,
    spell: GameObject,
    raw_modes: tuple[str, str],
    target_modes: tuple[str, str],
    target_refs: tuple[TargetRef, TargetRef],
) -> Action:
    original = executor._created_action(spell)
    metadata = dict(original.metadata)
    metadata["prismari_target_modes"] = list(target_modes)
    replacement = Action(
        original.action_id,
        original.kind,
        original.actor_id,
        original.source_object_id,
        target_refs,
        raw_modes,
        original.x_value,
        original.payments,
        metadata,
    )
    index = next(
        index
        for index, candidate in enumerate(executor.state.actions)
        if candidate.action_id == original.action_id
    )
    executor.state.actions[index] = replacement
    for record in executor.state.target_records:
        if record.get("action_id") == original.action_id:
            record["targets"] = [executor._target_data(ref) for ref in target_refs]
            break
    spell.current_characteristics["modes"] = list(raw_modes)
    return replacement


def _record_cast_choices(
    executor: Any,
    action: Action,
    raw_modes: tuple[str, str],
    target_modes: tuple[str, str],
    selected_targets: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    event = executor._event(
        "PRISMARI_MODES_CHOSEN",
        action,
        modes=list(raw_modes),
        timing="CAST_PROPOSAL",
    )
    executor.state.choices.append(
        Choice(
            executor.identity.new_id("choice"),
            action.actor_id,
            "PRISMARI_COMMAND_MODES",
            list(raw_modes),
            event.event_id,
        )
    )
    for mode, target in zip(target_modes, selected_targets, strict=True):
        target_event = executor._event(
            "PRISMARI_TARGET_CHOSEN",
            action,
            mode=mode,
            target=dict(target),
            timing="CAST_PROPOSAL",
        )
        executor.state.choices.append(
            Choice(
                executor.identity.new_id("choice"),
                action.actor_id,
                "PRISMARI_COMMAND_TARGET",
                {"mode": mode, "target": dict(target)},
                target_event.event_id,
            )
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
    selected_choices = dict(choices or {})
    if _effect_kind(self, card_object_id, face, mode) != "PRISMARI_COMMAND":
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
    if targets:
        raise IllegalAction(
            "Prismari Command uses mode-associated cast choices, not generic targets"
        )

    before = self._begin_atomic()
    try:
        raw_modes = _selected_modes(selected_choices)
        target_modes = cast(
            tuple[str, str],
            tuple(candidate for candidate in PRISMARI_MODE_ORDER if candidate in raw_modes),
        )
        selected_targets = cast(
            tuple[dict[str, Any], dict[str, Any]],
            tuple(_target_data(selected_choices, selected_mode) for selected_mode in target_modes),
        )
        target_refs = cast(
            tuple[TargetRef, TargetRef],
            tuple(
                _cast_target_ref(self, actor, selected_mode, selected_target)
                for selected_mode, selected_target in zip(
                    target_modes, selected_targets, strict=True
                )
            ),
        )
        spell = cast(
            GameObject,
            _ORIGINALS["cast"](
                self,
                actor,
                card_object_id,
                (),
                face,
                x_value,
                mode,
                selected_choices,
                _record=_record,
            ),
        )
        action = _replace_cast_action(self, spell, raw_modes, target_modes, target_refs)
        _record_cast_choices(self, action, raw_modes, target_modes, selected_targets)
        return spell
    except Exception:
        self._rollback(before)
        raise


def _resolved_target(
    executor: Any,
    action: Action,
    mode: str,
    ref: TargetRef,
) -> GameObject | None:
    try:
        value = executor.identity.resolve_reference(ref)
    except IllegalAction:
        return None
    if not isinstance(value, GameObject):
        return None

    if mode in _PLAYER_ONLY_MODES or (
        mode == "DAMAGE"
        and value.object_kind is ObjectKind.EXTERNAL_PUBLIC_OBJECT
        and value.current_characteristics.get("target_kind") == "PLAYER"
    ):
        player_id = value.current_characteristics.get("player_id")
        if not isinstance(player_id, str) or player_id not in executor.state.players:
            return None
        if not executor.state.players[player_id].in_game:
            return None
        if player_id != action.actor_id and _player_has_hexproof(executor, player_id):
            return None
        return value

    required_types = (
        {"Artifact"} if mode == "DESTROY_ARTIFACT" else {"Creature", "Planeswalker", "Battle"}
    )
    if (
        not executor._is_permanent(value)
        or not _types(value).intersection(required_types)
        or _permanent_has_hexproof_from(executor, action.actor_id, value)
    ):
        return None
    return value


def _prismari_resolution_targets(
    executor: Any,
    action: Action,
) -> tuple[tuple[str, GameObject | None], ...]:
    raw_modes = action.metadata.get("prismari_target_modes")
    if not isinstance(raw_modes, list) or len(raw_modes) != len(action.targets):
        raise IllegalAction("Prismari Command cast action is missing mode-target associations")
    modes = tuple(str(value) for value in raw_modes)
    return tuple(
        (mode, _resolved_target(executor, action, mode, ref))
        for mode, ref in zip(modes, action.targets, strict=True)
    )


def _revalidate_targets(self: Any, action: Action) -> list[GameObject]:
    if "prismari_target_modes" not in action.metadata:
        return cast(list[GameObject], _ORIGINALS["revalidate_targets"](self, action))
    return [
        target for _, target in _prismari_resolution_targets(self, action) if target is not None
    ]


def _target_player_id(target: GameObject) -> str:
    player_id = target.current_characteristics.get("player_id")
    if not isinstance(player_id, str):
        raise IllegalAction("Prismari Command player target lost its player identity")
    return player_id


def _apply_effect(
    self: Any,
    source: GameObject | None,
    action: Action,
    effect: dict[str, Any],
    targets: list[GameObject],
    choices: dict[str, Any],
) -> None:
    if str(effect.get("kind", "NONE")) != "PRISMARI_COMMAND" or (
        "prismari_target_modes" not in action.metadata
    ):
        _ORIGINALS["apply_effect"](self, source, action, effect, targets, choices)
        return

    del targets
    resolution_targets = _prismari_resolution_targets(self, action)
    by_mode = {mode: target for mode, target in resolution_targets}
    for mode in PRISMARI_MODE_ORDER:
        if mode not in action.modes:
            continue
        target = by_mode.get(mode)
        if target is None:
            continue
        if mode == "DAMAGE":
            if target.object_kind is ObjectKind.EXTERNAL_PUBLIC_OBJECT:
                self._damage_players(
                    self._rules_source(source),
                    [(_target_player_id(target), 2)],
                    action,
                    combat=False,
                    choices=choices,
                )
            else:
                self._damage_batch(
                    self._rules_source(source),
                    [(target, 2)],
                    action,
                    combat=False,
                )
        elif mode == "DRAW_DISCARD":
            _draw_then_discard(self, action, _target_player_id(target))
        elif mode == "CREATE_TREASURE":
            self.create_treasure(_target_player_id(target), action)
        elif mode == "DESTROY_ARTIFACT":
            _destroy(self, target, action, "PRISMARI_COMMAND")
        else:
            raise IllegalAction("Prismari Command mode dispatch failed")


def install_prismari_rules_conformance(executor_class: type[Any]) -> None:
    """Install cast-time mode/target legality and resolution revalidation."""

    if getattr(executor_class, "_prismari_rules_conformance_installed", False):
        return
    _ORIGINALS.update(
        {
            "cast": executor_class.cast,
            "revalidate_targets": executor_class._revalidate_targets,
            "apply_effect": executor_class._apply_effect,
        }
    )
    executor_class.cast = _cast
    executor_class._revalidate_targets = _revalidate_targets
    executor_class._apply_effect = _apply_effect
    executor_class._prismari_rules_conformance_installed = True


__all__ = ["install_prismari_rules_conformance"]
