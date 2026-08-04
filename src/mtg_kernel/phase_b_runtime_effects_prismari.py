"""Prismari Command modal effect support for the exact-deck Phase B runtime."""

from __future__ import annotations

from typing import Any, cast

from mtg_kernel.errors import IllegalAction
from mtg_kernel.models import Action, Choice, GameObject, Zone
from mtg_kernel.phase_b_runtime_helpers import _destroy
from mtg_kernel.phase_b_runtime_support import (
    _permanent_has_hexproof_from,
    _player_has_hexproof,
    _types,
)
from mtg_kernel.strategic_choices import (
    CardSelectionRequest,
    PublicCard,
    require_provider,
)

PRISMARI_MODE_ORDER = (
    "DAMAGE",
    "DRAW_DISCARD",
    "CREATE_TREASURE",
    "DESTROY_ARTIFACT",
)


def _selected_modes(
    executor: Any,
    action: Action,
    choices: dict[str, Any],
) -> tuple[str, str]:
    raw_modes = choices.get("prismari_modes")
    if not isinstance(raw_modes, (list, tuple)):
        raise IllegalAction("Prismari Command requires two explicit modes")
    modes = tuple(str(value) for value in raw_modes)
    if len(modes) != 2 or len(set(modes)) != 2:
        raise IllegalAction("Prismari Command requires exactly two distinct modes")
    if not set(modes) <= set(PRISMARI_MODE_ORDER):
        raise IllegalAction("Prismari Command includes an unsupported mode")
    event = executor._event("PRISMARI_MODES_CHOSEN", action, modes=list(modes))
    executor.state.choices.append(
        Choice(
            executor.identity.new_id("choice"),
            action.actor_id,
            "PRISMARI_COMMAND_MODES",
            list(modes),
            event.event_id,
        )
    )
    selected = tuple(mode for mode in PRISMARI_MODE_ORDER if mode in modes)
    if len(selected) != 2:
        raise IllegalAction("Prismari Command mode ordering failed")
    return selected[0], selected[1]


def _mode_target(
    executor: Any,
    action: Action,
    choices: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    raw_targets = choices.get("prismari_targets")
    if not isinstance(raw_targets, dict):
        raise IllegalAction("Prismari Command requires explicit mode targets")
    raw_target = raw_targets.get(mode)
    if not isinstance(raw_target, dict):
        raise IllegalAction(f"Prismari Command mode {mode} requires an explicit target")
    target = {str(key): value for key, value in raw_target.items()}
    event = executor._event(
        "PRISMARI_TARGET_CHOSEN",
        action,
        mode=mode,
        target=dict(target),
    )
    executor.state.choices.append(
        Choice(
            executor.identity.new_id("choice"),
            action.actor_id,
            "PRISMARI_COMMAND_TARGET",
            {"mode": mode, "target": dict(target)},
            event.event_id,
        )
    )
    return target


def _target_player(
    executor: Any,
    action: Action,
    target: dict[str, Any],
) -> str:
    player_id = target.get("player_id")
    if not isinstance(player_id, str) or player_id not in executor.state.players:
        raise IllegalAction("Prismari Command requires a legal player target")
    if not executor.state.players[player_id].in_game:
        raise IllegalAction("Prismari Command cannot target a player outside the game")
    if player_id != action.actor_id and _player_has_hexproof(executor, player_id):
        raise IllegalAction("Prismari Command player target has hexproof")
    return player_id


def _target_permanent(
    executor: Any,
    action: Action,
    target: dict[str, Any],
    *,
    required_types: set[str],
) -> GameObject:
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
    if _permanent_has_hexproof_from(executor, action.actor_id, obj):
        raise IllegalAction("Prismari Command permanent target has hexproof")
    return cast(GameObject, obj)


def _hand_objects(executor: Any, player_id: str) -> list[GameObject]:
    key = executor.zones.zone_key(Zone.HAND, player_id)
    return [
        executor.state.objects[object_id]
        for object_id in executor.state.zones.get(key, ())
        if not executor.state.objects[object_id].retired
        and not executor.state.objects[object_id].ceased_to_exist
    ]


def _select_discards(
    executor: Any,
    action: Action,
    player_id: str,
    candidates: list[GameObject],
    count: int,
) -> list[GameObject]:
    required = min(count, len(candidates))
    if required == 0:
        return []
    request_id = executor.identity.new_id("strategic-request")
    handles = {
        candidate.object_id: executor._strategic_handle(request_id, candidate.object_id)
        for candidate in candidates
    }
    public_cards = tuple(
        PublicCard(
            handle=handles[candidate.object_id],
            identity=str(candidate.current_characteristics.get("name", "")),
            mana_value=int(candidate.current_characteristics.get("mana_value", 0)),
            card_types=tuple(
                str(value) for value in candidate.current_characteristics.get("card_types", ())
            ),
            effect_kinds=executor._strategic_effect_kinds(candidate),
        )
        for candidate in candidates
    )
    provider = require_provider(
        getattr(executor, "strategic_choice_provider", None),
        "Prismari Command discard selection",
    )
    selection = provider.choose_cards(
        CardSelectionRequest(
            request_id=request_id,
            actor_id=player_id,
            ability_id=str(action.metadata.get("ability_id", "")),
            purpose="PRISMARI_DISCARD",
            turn_number=executor.state.turn.number,
            observation=executor._strategic_observation(player_id),
            candidates=public_cards,
            minimum=required,
            maximum=required,
        )
    )
    selected_handles = tuple(selection.selected_handles)
    legal_handles = set(handles.values())
    if len(selected_handles) != len(set(selected_handles)):
        raise IllegalAction("strategic provider selected a Prismari discard more than once")
    if not set(selected_handles) <= legal_handles:
        raise IllegalAction("strategic provider selected an unavailable Prismari discard")
    if len(selected_handles) != required:
        raise IllegalAction("strategic provider selected an illegal Prismari discard count")
    objects_by_handle = {
        handle: executor.state.objects[object_id] for object_id, handle in handles.items()
    }
    selected = [objects_by_handle[handle] for handle in selected_handles]
    event = executor._event(
        "STRATEGIC_CARD_SELECTION",
        action,
        purpose="PRISMARI_DISCARD",
        selected_count=len(selected),
        player_id=player_id,
    )
    executor.state.choices.append(
        Choice(
            executor.identity.new_id("choice"),
            player_id,
            "CARD_SELECTION",
            {
                "purpose": "PRISMARI_DISCARD",
                "selected_handles": list(selected_handles),
                "evaluator_id": selection.evaluator_id,
                "evaluator_sha256": selection.evaluator_sha256,
                "diagnostics": dict(selection.diagnostics),
                "chosen_at": "RESOLUTION",
            },
            event.event_id,
        )
    )
    return selected


def _draw_then_discard(
    executor: Any,
    action: Action,
    player_id: str,
) -> None:
    for _ in range(2):
        executor.draw_card(player_id, action=action)
    selected = _select_discards(
        executor,
        action,
        player_id,
        _hand_objects(executor, player_id),
        2,
    )
    for card in selected:
        event = executor._event(
            "CARD_DISCARDED",
            action,
            player_id=player_id,
            object_id=card.object_id,
        )
        successor = executor.zones.move(
            card.object_id,
            Zone.GRAVEYARD,
            "PRISMARI_COMMAND_DISCARD",
            event,
        )
        if successor is None:
            raise IllegalAction("Prismari Command discard did not reach the graveyard")
        executor._scan_discard_triggers(player_id, action, event)


def apply_prismari_command(
    executor: Any,
    source: GameObject | None,
    action: Action,
    choices: dict[str, Any],
) -> None:
    """Execute exactly two reviewed Prismari Command modes in printed order."""

    for mode in _selected_modes(executor, action, choices):
        target = _mode_target(executor, action, choices, mode)
        if mode == "DAMAGE":
            if "player_id" in target:
                player_id = _target_player(executor, action, target)
                executor._damage_players(
                    executor._rules_source(source),
                    [(player_id, 2)],
                    action,
                    combat=False,
                    choices=choices,
                )
            else:
                permanent = _target_permanent(
                    executor,
                    action,
                    target,
                    required_types={"Creature", "Planeswalker", "Battle"},
                )
                executor._damage_batch(
                    executor._rules_source(source),
                    [(permanent, 2)],
                    action,
                    combat=False,
                )
        elif mode == "DRAW_DISCARD":
            _draw_then_discard(executor, action, _target_player(executor, action, target))
        elif mode == "CREATE_TREASURE":
            executor.create_treasure(_target_player(executor, action, target), action)
        elif mode == "DESTROY_ARTIFACT":
            artifact = _target_permanent(
                executor,
                action,
                target,
                required_types={"Artifact"},
            )
            _destroy(executor, artifact, action, "PRISMARI_COMMAND")
        else:
            raise IllegalAction("Prismari Command mode dispatch failed")
