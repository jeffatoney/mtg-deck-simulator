"""Reusable Phase 9F protection availability evaluator."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from mtg_sim.engine import (
    Action,
    ActionType,
    GameState,
    Permanent,
    StackObject,
    generate_legal_actions,
    solve_mana_payment,
)


class AnswerClass(StrEnum):
    REMOVAL_TARGETING_CREATURE = "removal_targeting_creature"
    REMOVAL_TARGETING_PLAYER = "removal_targeting_player"
    NONCREATURE_COUNTER = "noncreature_counter"
    SPELL_OR_ABILITY_TARGETING_US = "spell_or_ability_targeting_us"


@dataclass(frozen=True, slots=True)
class ProtectionEvaluation:
    available: bool
    action: Action | None
    protects: tuple[str, ...]
    answers: tuple[AnswerClass, ...]
    sufficient_mana_after_combo: bool
    independent_of_unspecified_opponent_choice: bool
    reserved_mana: dict[str, int]


def evaluate_protection(
    state: GameState,
    *,
    combo_mana_cost: dict[str, int] | None = None,
    protected_object: Permanent | None = None,
    threat: StackObject | None = None,
) -> ProtectionEvaluation:
    """Measure whether protection is legally available without assuming interaction happens."""
    combo_mana_cost = combo_mana_cost or {}
    actions = generate_legal_actions(state)
    protection_actions = [
        action
        for action in actions
        if (action.action_type is ActionType.CAST_SPELL and action.source_name == "Lazotep Plating")
        or (
            action.action_type is ActionType.ACTIVATE_ABILITY
            and action.source_name == "Siren Stormtamer"
        )
    ]
    if protected_object is not None:
        protection_actions = [
            a
            for a in protection_actions
            if a.source_name == "Lazotep Plating"
            or (
                threat is not None
                and a.stack_target is threat
                and protected_object in threat.targets
            )
        ]
    chosen = protection_actions[0] if protection_actions else None
    reserved = chosen.mana_cost or {} if chosen is not None else {}
    combined = dict(combo_mana_cost)
    for key, value in reserved.items():
        combined[key] = combined.get(key, 0) + value
    sufficient = solve_mana_payment(state.mana_pool, combined) is not None
    protects: tuple[str, ...] = ()
    answers: tuple[AnswerClass, ...] = ()
    if chosen is not None:
        if chosen.source_name == "Lazotep Plating":
            protects = ("you", "permanents_you_control")
            answers = (AnswerClass.REMOVAL_TARGETING_CREATURE, AnswerClass.REMOVAL_TARGETING_PLAYER)
        else:
            protects = ("you_or_creature_you_control",)
            answers = (AnswerClass.SPELL_OR_ABILITY_TARGETING_US, AnswerClass.NONCREATURE_COUNTER)
    return ProtectionEvaluation(
        chosen is not None and sufficient,
        chosen,
        protects,
        answers,
        sufficient,
        True,
        dict(reserved),
    )
