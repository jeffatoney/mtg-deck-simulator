"""Hidden-future-safe directed mulligan choices for Phase C Exploratory V2."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from mtg_policy import StandardPolicy
from mtg_runs.phase_c_runner import OpeningHandRecord, _candidate_hand_from_probe
from mtg_search.directed_v2 import (
    CandidateScoreVector,
    DirectedArmConfig,
    DirectedCandidate,
    canonical_sha256,
    select_directed_candidate,
)

_KEEP = "MULLIGAN_KEEP"
_TAKE = "MULLIGAN_TAKE"
_SIZES = (7, 7, 6, 5, 4)


def _package_progress(names: Sequence[str], packages: Mapping[str, Sequence[str]]) -> int:
    visible = set(names)
    best = 0
    for cards in packages.values():
        pieces = set(cards)
        if not pieces:
            continue
        best = max(best, len(visible.intersection(pieces)) * 100 // len(pieces))
    return best


def _keep_score(
    *,
    names: tuple[str, ...],
    types: tuple[tuple[str, ...], ...],
    packages: Mapping[str, Sequence[str]],
    baseline_keep: bool,
    novelty: int,
) -> CandidateScoreVector:
    features = StandardPolicy.hand_features(names, types)
    return CandidateScoreVector(
        immediate_deterministic_access=False,
        projected_deterministic_access=False,
        earliest_projected_access_turn=None,
        known_package_progress=_package_progress(names, packages),
        mana_development_value=min(100, features["mana"] * 30),
        relevant_resource_preservation=min(100, len(names) * 12 + features["actions"] * 2),
        card_selection_or_tutor_value=min(100, features["tutors"] * 30 + features["combo"] * 20),
        conditional_access_status="NONE",
        novelty_value=novelty,
        arm_constraint_status="ALLOWED",
        action_cost=0,
        reason_codes=(
            "VISIBLE_OPENING_HAND_ONLY",
            "STANDARD_BASELINE_KEEP" if baseline_keep else "STANDARD_BASELINE_MULLIGAN",
        ),
    )


def _mulligan_score(
    *,
    names: tuple[str, ...],
    types: tuple[tuple[str, ...], ...],
    baseline_keep: bool,
    mulligans_taken: int,
    novelty: int,
) -> CandidateScoreVector:
    features = StandardPolicy.hand_features(names, types)
    mana_deficit = max(0, 2 - features["mana"])
    action_deficit = max(0, 1 - features["actions"])
    improvement_need = min(100, mana_deficit * 45 + action_deficit * 35 + (0 if baseline_keep else 35))
    return CandidateScoreVector(
        immediate_deterministic_access=False,
        projected_deterministic_access=False,
        earliest_projected_access_turn=None,
        known_package_progress=0,
        mana_development_value=improvement_need,
        relevant_resource_preservation=max(0, 84 - (mulligans_taken + 1) * 12),
        card_selection_or_tutor_value=100 if not baseline_keep else 0,
        conditional_access_status="NONE",
        novelty_value=novelty,
        arm_constraint_status="ALLOWED",
        action_cost=mulligans_taken + 1,
        reason_codes=(
            "NO_FUTURE_HAND_INSPECTION",
            "EXPECTED_REPLACEMENT_ONLY",
            "STANDARD_BASELINE_KEEP" if baseline_keep else "STANDARD_BASELINE_MULLIGAN",
        ),
    )


def choose_exploratory_mulligan(
    *,
    initial_state: Any,
    seed_text: str,
    policy: StandardPolicy,
    config: DirectedArmConfig,
    exploration_seed: int,
    environment_seed: int,
    game_index: int,
    combo_packages: Mapping[str, Sequence[str]],
) -> tuple[int, tuple[OpeningHandRecord, ...], tuple[Mapping[str, Any], ...]]:
    """Choose sequentially; the next candidate hand is never generated before TAKE."""

    records: list[OpeningHandRecord] = []
    audit: list[Mapping[str, Any]] = []
    selected_index = len(_SIZES) - 1
    for index, nominal_size in enumerate(_SIZES):
        names, types = _candidate_hand_from_probe(initial_state, seed_text, index)
        standard = policy.decide_keep(nominal_size, names, types)
        forced_keep = index == len(_SIZES) - 1
        baseline_handle = _KEEP if standard.keep or forced_keep else _TAKE
        public_hand = {
            "candidate_index": index,
            "nominal_size": nominal_size,
            "card_names": names,
            "card_types": types,
        }
        public_digest = canonical_sha256(public_hand)
        decision_id = hashlib.sha256(
            f"mulligan-v2:{config.arm_id}:{game_index}:{index}:{public_digest}".encode()
        ).hexdigest()[:24]
        candidates = [
            DirectedCandidate(
                _KEEP,
                _KEEP,
                _keep_score(
                    names=names,
                    types=types,
                    packages=combo_packages,
                    baseline_keep=baseline_handle == _KEEP,
                    novelty=0,
                ),
            )
        ]
        if not forced_keep:
            candidates.append(
                DirectedCandidate(
                    _TAKE,
                    _TAKE,
                    _mulligan_score(
                        names=names,
                        types=types,
                        baseline_keep=baseline_handle == _KEEP,
                        mulligans_taken=index,
                        novelty=0,
                    ),
                )
            )
        selection = select_directed_candidate(
            config,
            candidates,
            baseline_handle=baseline_handle,
            exploration_seed=exploration_seed,
            decision_id=decision_id,
        )
        keep = selection.selected_handle == _KEEP or forced_keep
        records.append(OpeningHandRecord(index, nominal_size, names, keep))
        ranked = {candidate.handle: candidate for candidate in selection.candidates}
        audit.append(
            {
                "schema_version": "phase-c-exploratory-v2-strategic-choice-v1",
                "arm_id": config.arm_id,
                "game_index": game_index,
                "environment_seed": environment_seed,
                "exploration_seed": exploration_seed,
                "decision_id": decision_id,
                "turn": 1,
                "phase": "MULLIGAN",
                "public_observation_digest": public_digest,
                "strategic_choice_purpose": "MULLIGAN",
                "legal_candidate_handles": [candidate.handle for candidate in candidates],
                "standard_baseline_handle": baseline_handle,
                "standard_baseline_score_vector": ranked[baseline_handle].score.to_dict(),
                "candidate_evaluations": [
                    {
                        "handle": candidate.handle,
                        "semantic_key": candidate.semantic_key,
                        "score": candidate.score.to_dict(),
                        "pruned_reason": candidate.pruned_reason,
                    }
                    for candidate in selection.candidates
                ],
                "pruned_candidates": [],
                "arm_specific_exclusions": [],
                "novelty_state_before": {},
                "equivalence_window": dict(config.equivalence_window),
                "eligible_top_k": list(selection.eligible_top_k),
                "selected_action": selection.selected_handle,
                "selection_reason": selection.selection_reason,
                "randomness_affected_selection": selection.randomness_affected_selection,
                "selected_plan_or_package_id": None,
                "continuation_method": "EXPECTED_REPLACEMENT_NO_FUTURE_HAND_INSPECTION",
                "continuation_horizon": {"future_candidate_hands_inspected": 0},
                "plan_termination_or_fallback_reason": "KEEP" if keep else "NEXT_HAND_BECOMES_VISIBLE",
                "resulting_public_state_digest": public_digest if keep else None,
                "replay_binding": {"mulligan_candidate_index": index},
            }
        )
        if keep:
            selected_index = index
            break
    return selected_index, tuple(records), tuple(audit)


__all__ = ["choose_exploratory_mulligan"]
