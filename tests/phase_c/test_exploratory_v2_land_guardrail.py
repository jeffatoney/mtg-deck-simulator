from __future__ import annotations

from mtg_policy.broker_core import ObservedAction
from mtg_policy.exploratory_v2 import (
    LandHoldEvidence,
    LandHoldReason,
    PublicProjection,
    score_priority_candidate,
    validate_land_hold_reason,
)
from mtg_search.directed_v2 import AGGRESSIVE_ARM, load_directed_arm_config


def _projection() -> PublicProjection:
    return PublicProjection(False, False, None, (), "STANDARD_PASS", 0)


def test_normal_turn_one_land_development_beats_meaningless_pass() -> None:
    config = load_directed_arm_config(AGGRESSIVE_ARM)
    land = ObservedAction("land", "PLAY_LAND", "Island", 0, ("Land",), 0, {})
    passed = ObservedAction("pass", "PASS_PRIORITY", None, 0, (), 0, {})
    observation = {
        "generation": 1,
        "turn": 1,
        "phase": "PRECOMBAT_MAIN",
        "objects": (),
    }
    land_score, land_prune, _ = score_priority_candidate(
        action=land,
        observation=observation,
        all_actions=(land, passed),
        config=config,
        projection=_projection(),
        novelty_value=0,
        combo_packages={},
    )
    pass_score, pass_prune, _ = score_priority_candidate(
        action=passed,
        observation=observation,
        all_actions=(land, passed),
        config=config,
        projection=_projection(),
        novelty_value=10,
        combo_packages={},
    )
    assert land_score.mana_development_value == 100
    assert land_prune is None
    assert pass_score.arm_constraint_status == "FAIL_CLOSED_MANA_DEVELOPMENT"
    assert pass_prune == "MAIN_PHASE_LAND_AVAILABLE_WITHOUT_VALID_HOLD_REASON"


def test_all_land_hold_reason_codes_require_their_factual_preconditions() -> None:
    valid = {
        LandHoldReason.GLINT_HORN_DISCARD_RESOURCE: LandHoldEvidence(
            glint_horn_visible=True, discard_resource_shortage=True
        ),
        LandHoldReason.BOUNCE_LAND_SEQUENCE: LandHoldEvidence(
            bounce_land_candidate=True, land_return_sequence_pending=True
        ),
        LandHoldReason.REVEAL_LAND_BASIC_PRESERVATION: LandHoldEvidence(
            reveal_land_candidate=True,
            basic_land_candidate=True,
            reveal_requirement_relevant=True,
        ),
        LandHoldReason.LAND_SEARCH_OR_CYCLING_SEQUENCE: LandHoldEvidence(
            land_search_or_cycling_action_available=True
        ),
        LandHoldReason.COLOR_FIXING_SEQUENCE: LandHoldEvidence(
            color_fixing_action_available=True, required_color_missing=True
        ),
        LandHoldReason.RULES_OR_RESOURCE_CONFLICT: LandHoldEvidence(
            documented_conflict_code="REQUIRED_RETURN_RESOURCE_CONFLICT"
        ),
    }
    for reason, evidence in valid.items():
        assert validate_land_hold_reason(reason, evidence)
        assert not validate_land_hold_reason(reason, LandHoldEvidence())


def test_bounce_reveal_basic_and_landcycling_are_explicit_finite_reasons() -> None:
    values = {reason.value for reason in LandHoldReason}
    assert "BOUNCE_LAND_SEQUENCE" in values
    assert "REVEAL_LAND_BASIC_PRESERVATION" in values
    assert "LAND_SEARCH_OR_CYCLING_SEQUENCE" in values
    assert "COLOR_FIXING_SEQUENCE" in values
    assert "OTHER" not in values
