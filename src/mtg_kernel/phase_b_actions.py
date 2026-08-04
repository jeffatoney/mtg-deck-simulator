"""Public Phase B action facade with fail-closed Slice 3 effect support."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mtg_kernel.models import Choice, GameObject
from mtg_kernel.phase_b_actions_core import (
    activate_hand_ability,
    foretell,
    legal_tutor_names,
)
from mtg_kernel.phase_b_marked_mana import PATH_SHARED_TYPE_TRIGGER
from mtg_kernel.phase_b_runtime_support import (
    automatic_ability_execution_supported as _automatic_ability_execution_supported,
    effect_execution_supported as _effect_execution_supported,
    object_automatic_execution_supported,
)

if TYPE_CHECKING:
    from mtg_kernel.engine_core import GameExecutor
    from mtg_kernel.models import Action


def effect_execution_supported(effect: dict[str, Any]) -> bool:
    """Return whether one effect has a reviewed production implementation."""

    if str(effect.get("kind", "NONE")) in {
        "ADD_COMMANDER_COLOR_AND_MARK",
        "COUNTER_WITH_DELAYED_DRAWS",
        "DEMOLITION_FIELD",
        "DRAW_THEN_DISCARD_UNLESS_ATTACKED",
        "EXILE_AND_MANIFEST",
    }:
        return True
    return _effect_execution_supported(effect)


def automatic_ability_execution_supported(ability: dict[str, Any], *, entering: bool) -> bool:
    """Recognize automatic paths whose explicit choices are captured elsewhere."""

    if (
        ability.get("kind") == "TRIGGERED"
        and ability.get("trigger") == PATH_SHARED_TYPE_TRIGGER
        and not ability.get("optional")
    ):
        schema = dict(ability.get("target_schema", {}))
        effect = dict(ability.get("effect", {}))
        return bool(
            str(schema.get("kind", "NONE")) == "NONE"
            and int(schema.get("min", 0) or 0) == 0
            and int(schema.get("max", 0) or 0) == 0
            and effect.get("kind") == "SCRY"
            and int(effect.get("count", 1)) == 1
        )
    return _automatic_ability_execution_supported(ability, entering=entering)


def apply_phase_b_effect(
    executor: GameExecutor,
    source: GameObject | None,
    action: Action,
    effect: dict[str, Any],
    targets: list[GameObject],
    choices: dict[str, Any],
) -> bool:
    """Apply the public Phase B primitive set without silent fallback."""

    kind = str(effect.get("kind", ""))
    if kind == "DEMOLITION_FIELD":
        from mtg_kernel.phase_b_runtime_effects_demolition import apply_demolition_field

        apply_demolition_field(executor, action, targets)
        return True
    if kind != "RECORD_UNKNOWN_BREECHES_EXILES":
        from mtg_kernel.phase_b_actions_core import apply_phase_b_effect as apply_core

        return apply_core(executor, source, action, effect, targets, choices)
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
