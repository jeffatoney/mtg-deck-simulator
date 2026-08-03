"""Exact-deck mana-option effects for the Phase B runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mtg_kernel.errors import IllegalAction
from mtg_kernel.mana import add_mana
from mtg_kernel.models import Action, GameObject

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


def apply_effect_mana(
    self: Any,
    source: GameObject | None,
    action: Action,
    effect: dict[str, Any],
    targets: list[GameObject],
    choices: dict[str, Any],
) -> bool:
    """Apply explicit multi-mana choices without card-name dispatch."""

    del source, targets
    if str(effect.get("kind", "NONE")) != "FILTER_MANA_OPTIONS":
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
