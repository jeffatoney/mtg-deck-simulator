"""Installer for exact-deck Phase B capabilities on the single public executor."""

from __future__ import annotations

from typing import Any

from mtg_kernel.errors import UnsupportedCapability
from mtg_kernel.models import Action, GameObject
from mtg_kernel.phase_b_runtime_effects_common import apply_effect_common
from mtg_kernel.phase_b_runtime_effects_interaction import apply_effect_interaction
from mtg_kernel.phase_b_runtime_helpers import (
    _cast,
    _check_state_based_actions,
    _cleanup_iteration,
    _draw_card,
)
from mtg_kernel.phase_b_runtime_support import _ORIGINALS, _target_matches


def _apply_effect(
    self: Any,
    source: GameObject | None,
    action: Action,
    effect: dict[str, Any],
    targets: list[GameObject],
    choices: dict[str, Any],
) -> None:
    if apply_effect_common(self, source, action, effect, targets, choices):
        return
    if apply_effect_interaction(self, source, action, effect, targets, choices):
        return
    kind = str(effect.get("kind", "NONE"))
    raise UnsupportedCapability(f"unsupported exact-deck effect primitive: {kind}")


def install_phase_b_runtime(executor_class: type[Any]) -> None:
    """Install explicit exact-deck extensions without creating a second executor."""

    if getattr(executor_class, "_phase_b_runtime_installed", False):
        return
    _ORIGINALS.update(
        {
            "target_matches": executor_class._target_matches,
            "apply_effect": executor_class._apply_effect,
            "draw_card": executor_class.draw_card,
            "cast": executor_class.cast,
            "check_state_based_actions": executor_class.check_state_based_actions,
            "cleanup_iteration": executor_class._cleanup_iteration,
        }
    )
    executor_class._target_matches = _target_matches
    executor_class._apply_effect = _apply_effect
    executor_class.draw_card = _draw_card
    executor_class.cast = _cast
    executor_class.check_state_based_actions = _check_state_based_actions
    executor_class._cleanup_iteration = _cleanup_iteration
    executor_class._phase_b_runtime_installed = True
