"""Stable facade for Phase B hand actions and resolution primitives."""

from mtg_kernel.phase_b_actions_choices import apply_phase_b_effect
from mtg_kernel.phase_b_actions_common import (
    activate_hand_ability,
    automatic_ability_execution_supported,
    effect_execution_supported,
    foretell,
    legal_tutor_names,
    object_automatic_execution_supported,
)

__all__ = [
    "activate_hand_ability",
    "apply_phase_b_effect",
    "automatic_ability_execution_supported",
    "effect_execution_supported",
    "foretell",
    "legal_tutor_names",
    "object_automatic_execution_supported",
]
