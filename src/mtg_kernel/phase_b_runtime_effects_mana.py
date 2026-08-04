"""Exact-deck mana-option effects for the Phase B runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mtg_kernel.errors import IllegalAction
from mtg_kernel.mana import add_mana
from mtg_kernel.models import Action, GameObject
from mtg_kernel.phase_b_marked_mana import (
    MARKED_COMMANDER_MANA_KIND,
    PATH_SHARED_TYPE_TRIGGER,
    commander_color_identity,
)

_ALLOWED_MANA_SYMBOLS = frozenset({"W", "U", "B", "R", "G", "C"})


def _normalize_option(value: Mapping[str, Any]) -> dict[str, int]:
    option: dict[str, int] = {}
    for raw_symbol, raw_amount in value.items():
        symbol = str(raw_symbol)
        amount = int(raw_amount)
        if symbol not in _ALLOWED_MANA_SYMBOLS or amount <= 0:
            raise IllegalAction("filter-mana option contains an invalid mana amount")
        option[symbol] = amount
    if not option:
        raise IllegalAction("filter-mana option cannot be empty")
    return option


def _marked_trigger_ability(self: Any, action: Action) -> tuple[GameObject, dict[str, Any]]:
    source_id = action.source_object_id
    source = self.state.objects.get(source_id) if source_id is not None else None
    if source is None or not self._is_permanent(source) or source.controller != action.actor_id:
        raise IllegalAction("marked commander mana requires its battlefield source")
    matches = [
        dict(ability)
        for ability in source.current_characteristics.get("abilities", ())
        if ability.get("kind") == "TRIGGERED"
        and ability.get("trigger") == PATH_SHARED_TYPE_TRIGGER
    ]
    if len(matches) != 1:
        raise IllegalAction("marked commander mana requires one shared-type trigger")
    return source, matches[0]


def apply_effect_mana(
    self: Any,
    source: GameObject | None,
    action: Action,
    effect: dict[str, Any],
    targets: list[GameObject],
    choices: dict[str, Any],
) -> bool:
    """Apply explicit mana choices without card-name dispatch."""

    del source, targets
    kind = str(effect.get("kind", "NONE"))
    if kind == "ADD_COMMANDER_COLOR_AND_MARK":
        allowed = commander_color_identity(self, action.actor_id)
        selected = str(choices.get("mana_color", ""))
        if selected not in allowed:
            raise IllegalAction("commander-color mana requires an explicit legal color choice")
        source_permanent, trigger_ability = _marked_trigger_ability(self, action)
        add_mana(self.state.players[action.actor_id].mana_pool, {selected: 1})
        event = self._event(
            "MANA_ADDED",
            action,
            mana={selected: 1},
            source_kind=kind,
            marked=True,
        )
        self.state.continuous_effects.append(
            {
                "kind": MARKED_COMMANDER_MANA_KIND,
                "player_id": action.actor_id,
                "source_object_id": source_permanent.object_id,
                "color": selected,
                "amount": 1,
                "produced_event_id": event.event_id,
                "trigger_ability": trigger_ability,
            }
        )
        return True

    if kind != "FILTER_MANA_OPTIONS":
        return False

    configured = effect.get("options", ())
    if not isinstance(configured, (list, tuple)):
        raise IllegalAction("filter-mana options are malformed")
    options = tuple(
        _normalize_option(option) for option in configured if isinstance(option, Mapping)
    )
    if len(options) != len(configured):
        raise IllegalAction("filter-mana options are malformed")

    selected_raw = choices.get("mana_option")
    if not isinstance(selected_raw, Mapping):
        raise IllegalAction("filter-mana ability requires an explicit mana option")
    selected = _normalize_option(selected_raw)
    if selected not in options:
        raise IllegalAction("selected filter-mana option is unavailable")

    add_mana(self.state.players[action.actor_id].mana_pool, selected)
    self._event("MANA_ADDED", action, mana=selected, source_kind="FILTER_MANA_OPTIONS")
    return True
