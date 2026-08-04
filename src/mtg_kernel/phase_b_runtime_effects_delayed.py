"""Delayed exact-deck effects and step-trigger scheduling."""

from __future__ import annotations

from typing import Any

from mtg_kernel.errors import IllegalAction
from mtg_kernel.models import Action, Choice, GameObject, ObjectKind, Zone
from mtg_kernel.phase_b_runtime_helpers import _counter_to


def _queue_next_upkeep_draws(
    self: Any,
    source: GameObject | None,
    action: Action,
    *,
    optional_player: str,
    mandatory_player: str,
) -> GameObject:
    event = self._event(
        "DELAYED_TRIGGER_CREATED",
        action,
        trigger="NEXT_UPKEEP",
        optional_player=optional_player,
        mandatory_player=mandatory_player,
        not_before_turn=self.state.turn.number + 1,
    )
    trigger = GameObject(
        self.identity.new_id("object"),
        ObjectKind.TRIGGERED_ABILITY,
        Zone.NONE,
        None,
        mandatory_player,
        source_object_id=(source.object_id if source is not None else action.source_object_id),
        created_by_event_id=event.event_id,
        current_characteristics={
            "ability": {
                "ability_id": "arcane-denial:delayed-draws",
                "kind": "TRIGGERED",
                "trigger": "NEXT_UPKEEP",
                "target_schema": {
                    "kind": "NONE",
                    "min": 0,
                    "max": 0,
                    "unique": True,
                },
                "effect": {
                    "kind": "ARCANE_DENIAL_DELAYED_DRAWS",
                    "optional_player": optional_player,
                    "mandatory_player": mandatory_player,
                },
            },
            "trigger_context": {"not_before_turn": self.state.turn.number + 1},
            "choice_hints": {},
        },
        was_cast=False,
    )
    self.state.objects[trigger.object_id] = trigger
    self.state.delayed_triggers.append(trigger.object_id)
    return trigger


def _resolve_arcane_denial_draws(
    self: Any,
    action: Action,
    effect: dict[str, Any],
    choices: dict[str, Any],
) -> None:
    optional_player = str(effect.get("optional_player", ""))
    mandatory_player = str(effect.get("mandatory_player", ""))
    if optional_player not in self.state.players or mandatory_player not in self.state.players:
        raise IllegalAction("Arcane Denial delayed draw players are unavailable")

    raw_choice = choices.get("arcane_denial_draw_count")
    if not isinstance(raw_choice, dict):
        raise IllegalAction("Arcane Denial requires an explicit draw-count choice")
    if raw_choice.get("player_id") != optional_player:
        raise IllegalAction("Arcane Denial draw choice must be anchored to the eligible player")
    count = raw_choice.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 2:
        raise IllegalAction("Arcane Denial draw count must be an integer from zero through two")

    choice_event = self._event(
        "ARCANE_DENIAL_DRAW_COUNT_CHOSEN",
        action,
        player_id=optional_player,
        count=count,
    )
    self.state.choices.append(
        Choice(
            self.identity.new_id("choice"),
            optional_player,
            "ARCANE_DENIAL_DRAW_COUNT",
            count,
            choice_event.event_id,
        )
    )
    for _ in range(count):
        self.draw_card(optional_player, action=action)
        if self.state.terminal.status != "ACTIVE":
            return
    self.draw_card(mandatory_player, action=action)


def apply_effect_delayed(
    self: Any,
    source: GameObject | None,
    action: Action,
    effect: dict[str, Any],
    targets: list[GameObject],
    choices: dict[str, Any],
) -> bool:
    """Apply delayed exact-deck primitives without card-name branching."""

    kind = str(effect.get("kind", "NONE"))
    if kind == "COUNTER_WITH_DELAYED_DRAWS":
        if len(targets) != 1:
            raise IllegalAction("Arcane Denial requires one spell target")
        target = targets[0]
        optional_player = target.controller or target.owner
        if optional_player is None or optional_player not in self.state.players:
            raise IllegalAction("countered spell has no available controller")
        _counter_to(self, target, action, Zone.GRAVEYARD)
        _queue_next_upkeep_draws(
            self,
            source,
            action,
            optional_player=optional_player,
            mandatory_player=action.actor_id,
        )
        return True

    if kind == "ARCANE_DENIAL_DELAYED_DRAWS":
        if targets:
            raise IllegalAction("Arcane Denial delayed draws do not target")
        _resolve_arcane_denial_draws(self, action, effect, choices)
        return True

    return False
