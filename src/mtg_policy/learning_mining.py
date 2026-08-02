"""Review-only generic, card-pair, and action-sequence hypothesis mining."""
from __future__ import annotations
import math
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, cast
import numpy as np
from mtg_policy.learning_models import ActionSignature, InteractionCandidate, LearningPlan, OrganicInteractionCandidate, PairwiseTrainingExample, _rounded
from mtg_policy.learning_validation import _matrix


def mine_interaction_candidates(
    examples: Sequence[PairwiseTrainingExample],
    feature_schema: Sequence[str],
    base_weights: np.ndarray,
    *,
    minimum_support: int,
    top_n: int,
) -> tuple[InteractionCandidate, ...]:
    """Mine generic residual pairs without activating them in the learned model."""

    x, y, _ = _matrix(examples, feature_schema)
    residual = y - x @ base_weights
    support: Counter[tuple[int, int]] = Counter()
    numerator: defaultdict[tuple[int, int], float] = defaultdict(float)
    denominator: defaultdict[tuple[int, int], float] = defaultdict(float)
    signal_sum: defaultdict[tuple[int, int], float] = defaultdict(float)
    for row, error in zip(x, residual, strict=True):
        active = [index for index, value in enumerate(row) if value != 0.0]
        for offset, first in enumerate(active):
            for second in active[offset + 1 :]:
                pair = (first, second)
                signal = float(row[first] * row[second])
                if signal == 0.0:
                    continue
                support[pair] += 1
                numerator[pair] += signal * float(error)
                denominator[pair] += signal * signal
                signal_sum[pair] += abs(signal)
    candidates: list[InteractionCandidate] = []
    for pair, count in support.items():
        if count < minimum_support or denominator[pair] == 0.0:
            continue
        candidates.append(
            InteractionCandidate(
                str(feature_schema[pair[0]]),
                str(feature_schema[pair[1]]),
                count,
                _rounded(numerator[pair] / denominator[pair]),
                _rounded(signal_sum[pair] / count),
            )
        )
    candidates.sort(
        key=lambda item: (
            -abs(item.residual_coefficient),
            -item.support,
            item.feature_a,
            item.feature_b,
        )
    )
    return tuple(candidates[:top_n])


def _card_pair_keys(identities: Sequence[str]) -> set[tuple[str, ...]]:
    names = sorted(set(str(value) for value in identities if value))
    return {(names[first], names[second]) for first in range(len(names)) for second in range(first + 1, len(names))}


def _sequence_keys(example: PairwiseTrainingExample, action: ActionSignature | None) -> set[tuple[str, ...]]:
    if action is None:
        return set()
    previous = example.context.prior_actions[-1].key if example.context and example.context.prior_actions else "START"
    return {(previous, action.key)}


def _organic_signals(
    example: PairwiseTrainingExample,
) -> dict[tuple[str, tuple[str, ...]], float]:
    signals: dict[tuple[str, tuple[str, ...]], float] = {}
    pairs_a = _card_pair_keys(example.available_card_identities_a)
    pairs_b = _card_pair_keys(example.available_card_identities_b)
    for members in pairs_a | pairs_b:
        difference = float(int(members in pairs_a) - int(members in pairs_b))
        if difference:
            signals[("CARD_PAIR", members)] = difference
    sequences_a = _sequence_keys(example, example.action_a)
    sequences_b = _sequence_keys(example, example.action_b)
    for members in sequences_a | sequences_b:
        difference = float(int(members in sequences_a) - int(members in sequences_b))
        if difference:
            signals[("ACTION_SEQUENCE", members)] = difference
    return signals


@dataclass(frozen=True)
class _CandidateStats:
    support: int
    distinct_seeds: int
    coefficient: float
    examples: tuple[str, ...]


def _candidate_stats(
    examples: Sequence[PairwiseTrainingExample],
    feature_schema: Sequence[str],
    weights: np.ndarray,
    allowed_keys: set[tuple[str, tuple[str, ...]]] | None = None,
) -> dict[tuple[str, tuple[str, ...]], _CandidateStats]:
    x, y, retained = _matrix(examples, feature_schema)
    residual = y - x @ weights
    support: Counter[tuple[str, tuple[str, ...]]] = Counter()
    seeds: defaultdict[tuple[str, tuple[str, ...]], set[int]] = defaultdict(set)
    numerator: defaultdict[tuple[str, tuple[str, ...]], float] = defaultdict(float)
    denominator: defaultdict[tuple[str, tuple[str, ...]], float] = defaultdict(float)
    representative: defaultdict[tuple[str, tuple[str, ...]], list[str]] = defaultdict(list)
    for example, error in zip(retained, residual, strict=True):
        for key, signal in _organic_signals(example).items():
            if allowed_keys is not None and key not in allowed_keys:
                continue
            support[key] += 1
            seeds[key].add(example.seed)
            numerator[key] += signal * float(error)
            denominator[key] += signal * signal
            if len(representative[key]) < 5:
                representative[key].append(example.example_id)
    result: dict[tuple[str, tuple[str, ...]], _CandidateStats] = {}
    for key, count in support.items():
        if denominator[key] == 0.0:
            continue
        result[key] = _CandidateStats(
            count,
            len(seeds[key]),
            _rounded(numerator[key] / denominator[key]),
            tuple(representative[key]),
        )
    return result


def mine_organic_interaction_candidates(
    mining_examples: Sequence[PairwiseTrainingExample],
    confirmation_examples: Sequence[PairwiseTrainingExample],
    feature_schema: Sequence[str],
    mining_weights: np.ndarray,
    plan: LearningPlan,
) -> tuple[OrganicInteractionCandidate, ...]:
    """Rank unscripted card/sequence hypotheses; never mutate the evaluator."""

    mining = _candidate_stats(mining_examples, feature_schema, mining_weights)
    eligible_keys = {
        key
        for key, stats in mining.items()
        if stats.support >= plan.organic_candidate_min_mining_support
        and stats.distinct_seeds >= plan.organic_candidate_min_distinct_seeds
    }
    confirmation = _candidate_stats(
        confirmation_examples,
        feature_schema,
        mining_weights,
        allowed_keys=eligible_keys,
    )
    candidates: list[OrganicInteractionCandidate] = []
    for key in sorted(eligible_keys):
        mining_stats = mining[key]
        confirmation_stats = confirmation.get(key)
        if confirmation_stats is None:
            continue
        total_support = mining_stats.support + confirmation_stats.support
        total_seeds = mining_stats.distinct_seeds + confirmation_stats.distinct_seeds
        same_direction = (
            mining_stats.coefficient != 0.0
            and confirmation_stats.coefficient != 0.0
            and math.copysign(1.0, mining_stats.coefficient)
            == math.copysign(1.0, confirmation_stats.coefficient)
        )
        if (
            total_support < plan.organic_candidate_min_support
            or total_seeds < plan.organic_candidate_min_distinct_seeds
            or confirmation_stats.support < plan.organic_candidate_min_confirmation_support
            or not same_direction
        ):
            continue
        candidate_type, members = key
        candidates.append(
            OrganicInteractionCandidate(
                candidate_type=cast(Literal["CARD_PAIR", "ACTION_SEQUENCE"], candidate_type),
                members=members,
                mining_support=mining_stats.support,
                mining_distinct_seeds=mining_stats.distinct_seeds,
                mining_residual_coefficient=mining_stats.coefficient,
                confirmation_support=confirmation_stats.support,
                confirmation_distinct_seeds=confirmation_stats.distinct_seeds,
                confirmation_residual_coefficient=confirmation_stats.coefficient,
                same_direction_confirmed=True,
                representative_example_ids=tuple(
                    dict.fromkeys((*mining_stats.examples, *confirmation_stats.examples))
                ),
            )
        )
    candidates.sort(
        key=lambda item: (
            -min(
                abs(item.mining_residual_coefficient),
                abs(item.confirmation_residual_coefficient),
            ),
            -(item.mining_support + item.confirmation_support),
            item.candidate_type,
            item.members,
        )
    )
    return tuple(candidates[: plan.organic_candidate_top_n])
