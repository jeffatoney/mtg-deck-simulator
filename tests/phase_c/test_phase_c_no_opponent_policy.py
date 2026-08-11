from __future__ import annotations

import pytest

from mtg_policy.broker import ObservedAction
from mtg_policy.config import load_policy_matrix
from mtg_policy.standard import StandardPolicy


def _bundle():
    return next(
        bundle for bundle in load_policy_matrix() if bundle.policy_config_id == "anchor_balanced"
    )


def _no_opponent_policy() -> StandardPolicy:
    return StandardPolicy(_bundle(), opponent_interaction_modeled=False)


def _observation(*, include_target: bool = True, target_owner: str = "P0") -> dict[str, object]:
    objects: list[dict[str, object]] = []
    if include_target:
        objects.append(
            {
                "handle": "target",
                "owner": target_owner,
                "controller": target_owner,
                "zone": "STACK",
            }
        )
    return {
        "generation": 1,
        "turn": {"number": 1},
        "player": "P0",
        "objects": objects,
    }


def _pass() -> ObservedAction:
    return ObservedAction("pass", "PASS_PRIORITY", None, 0, (), 0, {})


def _targeted_action(handle: str, identity: str, *tags: str) -> ObservedAction:
    return ObservedAction(
        handle,
        "CAST",
        identity,
        1,
        tags,
        1,
        {"target_handles": ("target",)},
    )


def test_no_opponent_model_ranks_pure_defensive_self_effects_below_pass() -> None:
    policy = _no_opponent_policy()
    actions = tuple(
        _targeted_action(f"action-{index}", f"card-{index}", effect_kind)
        for index, effect_kind in enumerate(
            (
                "COUNTER",
                "COUNTER_IF",
                "COUNTER_UNLESS_PAY",
                "COUNTER_UNLESS_PAY_EXILE",
                "COUNTER_TARGETING_CONTROLLER",
                "LIBRARY_SECOND",
            )
        )
    )

    assert policy.select_action(_observation(), (_pass(), *actions)) == "pass"


def test_arcane_denial_self_target_ties_neutral_pass_in_standard() -> None:
    policy = _no_opponent_policy()
    arcane_denial = _targeted_action(
        "arcane-denial",
        "Arcane Denial",
        "COUNTER_WITH_DELAYED_DRAWS",
    )

    assert policy.select_action(_observation(), (_pass(), arcane_denial)) == "pass"


def test_arcane_denial_remains_a_legal_observed_action() -> None:
    arcane_denial = _targeted_action(
        "arcane-denial",
        "Arcane Denial",
        "COUNTER_WITH_DELAYED_DRAWS",
    )

    assert arcane_denial.handle == "arcane-denial"
    assert "COUNTER_WITH_DELAYED_DRAWS" in arcane_denial.tags


def test_no_opponent_model_preserves_zero_scored_nondefensive_baseline_action() -> None:
    policy = _no_opponent_policy()
    transmute = ObservedAction(
        "transmute",
        "ACTIVATE_HAND",
        "Muddle the Mixture",
        0,
        ("ACTIVATED", "TRANSMUTE"),
        0,
        {"tutor_identity": "Twinflame"},
    )

    assert policy.select_action(_observation(), (_pass(), transmute)) == "transmute"


def test_no_opponent_model_preserves_positive_nondefensive_action_value() -> None:
    policy = _no_opponent_policy()
    draw_action = ObservedAction(
        "draw",
        "ACTIVATE",
        "Mind Stone",
        0,
        ("DRAW",),
        0,
        {},
    )

    assert policy.select_action(_observation(), (_pass(), draw_action)) == "draw"


def test_reviewed_self_effect_with_unresolved_target_fails_closed() -> None:
    policy = _no_opponent_policy()
    spell_pierce = _targeted_action(
        "pierce",
        "Spell Pierce",
        "COUNTER_UNLESS_PAY",
    )

    with pytest.raises(ValueError, match="target handle is unresolved"):
        policy.select_action(_observation(include_target=False), (_pass(), spell_pierce))


def test_reviewed_effect_targeting_opponent_retains_normal_baseline_ranking() -> None:
    policy = _no_opponent_policy()
    spell_pierce = _targeted_action(
        "pierce",
        "Spell Pierce",
        "COUNTER_UNLESS_PAY",
    )

    assert policy.select_action(
        _observation(target_owner="P1"), (_pass(), spell_pierce)
    ) == "pierce"


def test_interactive_context_retains_existing_protection_preference() -> None:
    policy = StandardPolicy(_bundle())
    spell_pierce = _targeted_action(
        "pierce",
        "Spell Pierce",
        "COUNTER_UNLESS_PAY",
        "PROTECTION",
    )

    assert policy.select_action(_observation(), (_pass(), spell_pierce)) == "pierce"
