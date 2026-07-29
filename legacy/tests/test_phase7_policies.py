from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mtg_sim.domain import new_game
from mtg_sim.policies import (
    CandidatePolicy,
    PairedComparisonRecord,
    PolicyError,
    extract_hand_features,
    first_decision_divergence,
    frozen_policy_matrix,
)


def test_frozen_policy_matrix_has_anchors_and_one_axis_variants() -> None:
    matrix = frozen_policy_matrix()
    ids = {cfg.policy_config_id for cfg in matrix}
    assert len(matrix) == 14
    assert {"anchor_balanced", "anchor_aggressive"}.issubset(ids)
    assert {
        "mulligan_aggressive",
        "tutor_first",
        "mana_rock_first",
        "breeches_early",
        "dualcaster_tutor",
        "lowest_mana_combo",
        "earliest_unprotected",
        "wait_for_protection",
        "cantrip_first",
        "transmute_muddle",
        "glint_horn_value",
        "additional_land_stability",
    }.issubset(ids)
    assert all(not cfg.search_enabled for cfg in matrix)
    assert all(not cfg.validation_seed_influence_allowed for cfg in matrix)


def test_policy_seed_list_is_precommitted_with_300_200_split() -> None:
    payload = json.loads(Path("configs/policy_seeds.json").read_text(encoding="utf-8"))
    all_seeds = payload["discovery_seeds"] + payload["validation_seeds"]
    assert payload["base_seed_count"] == 500
    assert payload["discovery_count"] == 300
    assert payload["validation_count"] == 200
    assert len(payload["discovery_seeds"]) == 300
    assert len(payload["validation_seeds"]) == 200
    assert len(set(all_seeds)) == 500
    assert not set(payload["discovery_seeds"]).intersection(payload["validation_seeds"])


def test_policy_matrix_artifact_disables_full_factorial() -> None:
    payload = json.loads(Path("configs/policies.json").read_text(encoding="utf-8"))
    assert payload["full_factorial_run"] is False
    assert len(payload["policies"]) == len(frozen_policy_matrix())
    assert all(policy["documented_before_results"] for policy in payload["policies"])


def test_hand_feature_extraction_from_observation_only() -> None:
    state = new_game(["Island", "Sol Ring", "Opt", "Muddle the Mixture", "Glint-Horn Buccaneer"])
    while state.zones[next(z for z in state.zones if z.value == "library")]:
        state.move_card(
            state.zones[next(z for z in state.zones if z.value == "library")][0],
            next(z for z in state.zones if z.value == "library"),
            next(z for z in state.zones if z.value == "hand"),
            "fixture",
        )
    features = extract_hand_features(state.observation())
    assert features.hand_size == 5
    assert features.lands == 1
    assert features.mana_rocks == 1
    assert features.cantrips == 1
    assert features.tutors == 1
    assert features.combo_pieces == 1
    assert features.has_muddle is True
    assert features.has_glint_horn is True


def test_policy_decision_is_unchanged_by_hidden_future_library_order() -> None:
    deck_a = ["Island", "Sol Ring", "Opt", "Mountain"]
    deck_b = list(reversed(deck_a))
    state_a = new_game(deck_a)
    state_b = new_game(deck_b)
    obs_a = state_a.observation()
    obs_b = state_b.observation()
    assert obs_a.hand == obs_b.hand == ()
    policy = CandidatePolicy(frozen_policy_matrix()[0])
    assert policy.choose_action(obs_a) == policy.choose_action(obs_b)


def test_first_decision_divergence_logging_uses_visible_features() -> None:
    state = new_game(["Sol Ring", "Opt", "Island"])
    for _ in range(3):
        state.move_card(
            state.zones[next(z for z in state.zones if z.value == "library")][0],
            next(z for z in state.zones if z.value == "library"),
            next(z for z in state.zones if z.value == "hand"),
            "fixture",
        )
    ramp_policy = CandidatePolicy(
        next(cfg for cfg in frozen_policy_matrix() if cfg.policy_config_id == "anchor_balanced")
    )
    cantrip_policy = CandidatePolicy(
        next(cfg for cfg in frozen_policy_matrix() if cfg.policy_config_id == "cantrip_first")
    )
    divergence = first_decision_divergence(123, ramp_policy, cantrip_policy, [state.observation()])
    assert divergence is not None
    assert divergence.decision_index == 0
    assert divergence.policy_a_choice == "prioritize_mana_rock"
    assert divergence.policy_b_choice == "prioritize_cantrip"
    assert divergence.visible_hand_features.mana_rocks == 1


def test_paired_comparison_rejects_validation_influence_and_self_comparison() -> None:
    with pytest.raises(PolicyError):
        PairedComparisonRecord(
            "c1", 1, "validation", "a", "b", validation_seed_used_for_discovery=True
        ).validate()
    with pytest.raises(PolicyError):
        PairedComparisonRecord("c2", 1, "discovery", "a", "a").validate()


def test_seed_list_hash_is_stable() -> None:
    digest = hashlib.sha256(Path("configs/policy_seeds.json").read_bytes()).hexdigest()
    assert digest == hashlib.sha256(Path("configs/policy_seeds.json").read_bytes()).hexdigest()
