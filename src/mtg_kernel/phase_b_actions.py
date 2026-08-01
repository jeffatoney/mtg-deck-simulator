"""Public Phase B action facade with fail-closed Slice 3 effect support."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mtg_kernel import phase_b_actions_core as _core
from mtg_kernel.models import Choice, GameObject
from mtg_kernel.phase_b_actions_core import (
    activate_hand_ability,
    automatic_ability_execution_supported,
    effect_execution_supported,
    foretell,
    legal_tutor_names,
    object_automatic_execution_supported,
)

if TYPE_CHECKING:
    from mtg_kernel.engine import GameExecutor
    from mtg_kernel.models import Action

_core._BROKER_SUPPORTED_EFFECTS = frozenset(
    {*_core._BROKER_SUPPORTED_EFFECTS, "RECORD_UNKNOWN_BREECHES_EXILES"}
)


def apply_phase_b_effect(
    executor: GameExecutor,
    source: GameObject | None,
    action: Action,
    effect: dict[str, Any],
    targets: list[GameObject],
    choices: dict[str, Any],
) -> bool:
    """Apply the public Phase B primitive set without silent fallback."""

    if str(effect.get("kind", "")) != "RECORD_UNKNOWN_BREECHES_EXILES":
        return _core.apply_phase_b_effect(executor, source, action, effect, targets, choices)
    opponents = (
        tuple(source.current_characteristics.get("trigger_context", {}).get("opponents", ()))
        if source is not None
        else ()
    )
    event = executor._event(
        "BREECHES_UNKNOWN_EXILES_RECORDED",
        action,
        opponents=list(opponents),
        deterministic_resources_added=0,
        hidden_identities_exposed=False,
    )
    executor.state.choices.append(
        Choice(
            executor.identity.new_id("choice"),
            action.actor_id,
            "BREECHES_UNKNOWN_EXCLUSION",
            {
                "opponents": list(opponents),
                "deterministic_resources_added": 0,
                "hidden_identities_exposed": False,
            },
            event.event_id,
        )
    )
    return True


__all__ = [
    "activate_hand_ability",
    "apply_phase_b_effect",
    "automatic_ability_execution_supported",
    "effect_execution_supported",
    "foretell",
    "legal_tutor_names",
    "object_automatic_execution_supported",
]
