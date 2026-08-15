from __future__ import annotations

from dataclasses import replace

from mtg_policy.broker_core import ObservedAction
from mtg_policy.exploratory_v2 import canonical_interaction_signature, semantic_action_key
from mtg_search.directed_v2 import (
    AGGRESSIVE_ARM,
    INTERACTION_ARM,
    CandidateScoreVector,
    DirectedCandidate,
    load_directed_arm_config,
    select_directed_candidate,
)


def _score(**overrides: object) -> CandidateScoreVector:
    values: dict[str, object] = {
        "immediate_deterministic_access": False,
        "projected_deterministic_access": False,
        "earliest_projected_access_turn": None,
        "known_package_progress": 50,
        "mana_development_value": 50,
        "relevant_resource_preservation": 50,
        "card_selection_or_tutor_value": 50,
        "conditional_access_status": "NONE",
        "novelty_value": 0,
        "arm_constraint_status": "ALLOWED",
        "action_cost": 1,
        "reason_codes": ("TEST",),
    }
    values.update(overrides)
    return CandidateScoreVector(**values)  # type: ignore[arg-type]


def test_immediate_deterministic_access_cannot_be_overridden_by_novelty() -> None:
    config = load_directed_arm_config(AGGRESSIVE_ARM)
    win = DirectedCandidate("win", "CAST:WIN", _score(immediate_deterministic_access=True))
    novel = DirectedCandidate("novel", "CAST:NOVEL", _score(novelty_value=10))
    selection = select_directed_candidate(
        config,
        (win, novel),
        baseline_handle="novel",
        exploration_seed=123,
        decision_id="d1",
    )
    assert selection.selected_handle == "win"
    assert selection.eligible_top_k == ("win",)
    assert selection.randomness_affected_selection is False


def test_baseline_is_retained_and_every_candidate_receives_a_rank() -> None:
    config = load_directed_arm_config(AGGRESSIVE_ARM)
    candidates = (
        DirectedCandidate("standard", "PLAY_LAND:Island", _score(mana_development_value=100)),
        DirectedCandidate("cast", "CAST:Rock", _score(mana_development_value=95)),
    )
    selection = select_directed_candidate(
        config,
        candidates,
        baseline_handle="standard",
        exploration_seed=99,
        decision_id="d2",
    )
    assert selection.baseline_handle == "standard"
    assert {item.score.final_candidate_rank for item in selection.candidates} == {1, 2}


def test_seeded_selection_reproduces_for_same_public_decision() -> None:
    config = load_directed_arm_config(INTERACTION_ARM)
    candidates = tuple(
        DirectedCandidate(
            f"h{index}",
            f"CAST:OPTION:{index}",
            _score(novelty_value=10, known_package_progress=50),
        )
        for index in range(3)
    )
    first = select_directed_candidate(
        config,
        candidates,
        baseline_handle="h0",
        exploration_seed=2026,
        decision_id="public-decision",
    )
    second = select_directed_candidate(
        config,
        candidates,
        baseline_handle="h0",
        exploration_seed=2026,
        decision_id="public-decision",
    )
    assert first.selected_handle == second.selected_handle
    assert first.exploration_seed_digest == second.exploration_seed_digest


def test_hidden_handle_changes_do_not_change_semantic_selection() -> None:
    config = load_directed_arm_config(INTERACTION_ARM)
    left = (
        DirectedCandidate("hidden-a1", "CAST:A", _score(novelty_value=10)),
        DirectedCandidate("hidden-b1", "CAST:B", _score(novelty_value=10)),
    )
    right = (
        replace(left[0], handle="hidden-a2"),
        replace(left[1], handle="hidden-b2"),
    )
    first = select_directed_candidate(
        config,
        left,
        baseline_handle="hidden-a1",
        exploration_seed=77,
        decision_id="same-public-observation",
    )
    second = select_directed_candidate(
        config,
        right,
        baseline_handle="hidden-a2",
        exploration_seed=77,
        decision_id="same-public-observation",
    )
    semantic_first = next(
        item.semantic_key for item in first.candidates if item.handle == first.selected_handle
    )
    semantic_second = next(
        item.semantic_key for item in second.candidates if item.handle == second.selected_handle
    )
    assert semantic_first == semantic_second


def test_canonical_interaction_signature_ignores_raw_handles_and_object_ids() -> None:
    first = canonical_interaction_signature(
        purpose="TUTOR",
        action_kind="TUTOR_TARGET",
        identity="Dualcaster Mage",
        metadata={"target_handle": "abc", "object_id": "object-1", "mode": "A"},
    )
    second = canonical_interaction_signature(
        purpose="TUTOR",
        action_kind="TUTOR_TARGET",
        identity="Dualcaster Mage",
        metadata={"target_handle": "xyz", "object_id": "object-9", "mode": "A"},
    )
    assert first == second


def test_semantic_action_key_excludes_opaque_action_handle() -> None:
    first = ObservedAction("a", "PLAY_LAND", "Island", 0, ("Land",), 0, {})
    second = ObservedAction("b", "PLAY_LAND", "Island", 0, ("Land",), 0, {})
    assert semantic_action_key(first) == semantic_action_key(second)
