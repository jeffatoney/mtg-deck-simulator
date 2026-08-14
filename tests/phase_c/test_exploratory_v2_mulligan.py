from __future__ import annotations

from copy import deepcopy

from mtg_deck import build_exact_game
from mtg_runs.phase_c_mulligan_v2 import choose_exploratory_mulligan
from mtg_runs.phase_c_runner import PLAYER_IDS, _bound_policy
from mtg_search.directed_v2 import AGGRESSIVE_ARM, load_directed_arm_config


def test_mulligan_records_standard_baseline_and_complete_vectors() -> None:
    seed_text = "phase-c:standard:880001"
    state, executor, _ = build_exact_game(seed_text, PLAYER_IDS)
    policy, _provider, evaluator = _bound_policy(executor, "anchor_balanced")
    _index, _opening, audit = choose_exploratory_mulligan(
        initial_state=deepcopy(state),
        seed_text=seed_text,
        policy=policy,
        config=load_directed_arm_config(AGGRESSIVE_ARM),
        exploration_seed=980001,
        environment_seed=880001,
        game_index=1,
        combo_packages=evaluator.combo_packages,
    )
    assert audit
    for record in audit:
        handles = set(record["legal_candidate_handles"])
        assert record["standard_baseline_handle"] in handles
        assert len(record["candidate_evaluations"]) == len(handles)
        assert record["continuation_horizon"]["future_candidate_hands_inspected"] == 0


def test_current_mulligan_decision_does_not_depend_on_unobserved_later_candidate() -> None:
    seed_text = "phase-c:standard:880002"
    state, executor, _ = build_exact_game(seed_text, PLAYER_IDS)
    policy, _provider, evaluator = _bound_policy(executor, "anchor_balanced")
    first = choose_exploratory_mulligan(
        initial_state=deepcopy(state),
        seed_text=seed_text,
        policy=policy,
        config=load_directed_arm_config(AGGRESSIVE_ARM),
        exploration_seed=980002,
        environment_seed=880002,
        game_index=1,
        combo_packages=evaluator.combo_packages,
    )[2][0]
    # A different future environment seed may produce different later hands, but the
    # current choice is bound only to the current visible-hand digest and search seed.
    second = choose_exploratory_mulligan(
        initial_state=deepcopy(state),
        seed_text=seed_text,
        policy=policy,
        config=load_directed_arm_config(AGGRESSIVE_ARM),
        exploration_seed=980002,
        environment_seed=123456789,
        game_index=1,
        combo_packages=evaluator.combo_packages,
    )[2][0]
    assert first["public_observation_digest"] == second["public_observation_digest"]
    assert first["selected_action"] == second["selected_action"]
