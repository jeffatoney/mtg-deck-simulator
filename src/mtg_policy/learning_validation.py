"""Deterministic dataset validation, fitting matrices, and uncertainty helpers."""

from __future__ import annotations
import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
import numpy as np
from mtg_policy.learning_models import (
    LearningPlan,
    PairwiseTrainingExample,
    _ordered,
    _rounded,
    _validate_safe_raw_payload,
)


def _validate_seed_quotas(
    examples: Sequence[PairwiseTrainingExample],
    expected_seeds: Sequence[int],
    comparisons_per_seed: int,
    label: str,
) -> None:
    counts = Counter(example.seed for example in examples)
    if set(counts) != set(expected_seeds):
        raise ValueError(f"{label} examples do not use the exact frozen seed set")
    wrong = {seed: count for seed, count in counts.items() if count != comparisons_per_seed}
    if wrong:
        raise ValueError(f"{label} comparisons per seed differ from the frozen quota: {wrong}")


def _validate_examples(
    discovery: Sequence[PairwiseTrainingExample],
    validation: Sequence[PairwiseTrainingExample],
    plan: LearningPlan,
    *,
    enforce_plan_counts: bool,
) -> tuple[str, ...]:
    discovery = _ordered(discovery)
    validation = _ordered(validation)
    if enforce_plan_counts and len(discovery) != plan.discovery_example_count:
        raise ValueError("discovery example count does not match the frozen plan")
    if enforce_plan_counts and len(validation) != plan.validation_example_count:
        raise ValueError("validation example count does not match the frozen plan")
    discovery_ids = {example.example_id for example in discovery}
    validation_ids = {example.example_id for example in validation}
    if len(discovery_ids) != len(discovery) or len(validation_ids) != len(validation):
        raise ValueError("learning examples contain duplicate IDs")
    if discovery_ids.intersection(validation_ids):
        raise ValueError("discovery and validation examples overlap")
    discovery_seeds = {example.seed for example in discovery}
    validation_seeds = {example.seed for example in validation}
    if discovery_seeds.intersection(validation_seeds):
        raise ValueError("discovery and validation seeds overlap")
    feature_names = {
        str(name)
        for example in (*discovery, *validation)
        for mapping in (example.features_a, example.features_b)
        for name in mapping
    }
    if not feature_names:
        raise ValueError("learning examples contain no features")
    if enforce_plan_counts and set(plan.required_feature_schema) != feature_names:
        raise ValueError(
            "learning feature schema differs from the frozen plan: "
            f"missing={sorted(set(plan.required_feature_schema) - feature_names)}, "
            f"extra={sorted(feature_names - set(plan.required_feature_schema))}"
        )
    if enforce_plan_counts:
        from mtg_policy.config import load_seed_split

        split = load_seed_split()
        if len(split.discovery) != plan.discovery_seed_count:
            raise ValueError("learning plan discovery seed count differs from frozen seed config")
        if len(split.validation) != plan.validation_seed_count:
            raise ValueError("learning plan validation seed count differs from frozen seed config")
        _validate_seed_quotas(
            discovery,
            split.discovery,
            plan.comparisons_per_discovery_seed,
            "discovery",
        )
        _validate_seed_quotas(
            validation,
            split.validation,
            plan.comparisons_per_validation_seed,
            "validation",
        )
    if plan.require_raw_context:
        for example in (*discovery, *validation):
            if (
                example.context is None
                or example.action_a is None
                or example.action_b is None
                or example.counterfactual_contract is None
            ):
                raise ValueError("learning example omits required raw decision context")
            if example.decision_index != example.context.decision_index:
                raise ValueError("learning example decision index differs from raw context")
            _validate_safe_raw_payload(example.to_dict())
    return tuple(sorted(feature_names))


def _matrix(
    examples: Sequence[PairwiseTrainingExample], feature_schema: Sequence[str]
) -> tuple[np.ndarray, np.ndarray, tuple[PairwiseTrainingExample, ...]]:
    rows: list[list[float]] = []
    labels: list[float] = []
    retained: list[PairwiseTrainingExample] = []
    for example in _ordered(examples):
        label = example.preferred_side
        if label == 0:
            continue
        rows.append(
            [
                float(example.features_a.get(name, 0.0)) - float(example.features_b.get(name, 0.0))
                for name in feature_schema
            ]
        )
        labels.append(float(label))
        retained.append(example)
    if not rows:
        raise ValueError("learning set contains no outcome-distinguishing comparisons")
    return np.asarray(rows, dtype=float), np.asarray(labels, dtype=float), tuple(retained)


def _fit_ridge(x: np.ndarray, y: np.ndarray, regularization: float) -> np.ndarray:
    identity = np.eye(x.shape[1], dtype=float)
    solved = np.linalg.solve(x.T @ x + regularization * identity, x.T @ y)
    return np.asarray([_rounded(value) for value in solved], dtype=float)


def _weight_vector(feature_schema: Sequence[str], weights: Mapping[str, float]) -> np.ndarray:
    return np.asarray([float(weights.get(name, 0.0)) for name in feature_schema], dtype=float)


def _prediction(score: float) -> int:
    """Return the frozen decision side; exact ties choose B and are reported."""

    return 1 if score > 0.0 else -1


def _accuracy_details(
    x: np.ndarray, y: np.ndarray, weights: np.ndarray
) -> tuple[float, np.ndarray, np.ndarray]:
    scores = x @ weights
    predictions = np.asarray([_prediction(float(value)) for value in scores], dtype=float)
    correct = predictions == y
    return float(np.mean(correct)), predictions, correct.astype(float)


def _clustered_difference_interval(
    examples: Sequence[PairwiseTrainingExample],
    learned_correct: np.ndarray,
    baseline_correct: np.ndarray,
    z_value: float,
) -> tuple[float, float, float]:
    by_seed: defaultdict[int, list[float]] = defaultdict(list)
    for example, learned, baseline in zip(examples, learned_correct, baseline_correct, strict=True):
        by_seed[example.seed].append(float(learned - baseline))
    cluster_means = [statistics.fmean(values) for _, values in sorted(by_seed.items())]
    if not cluster_means:
        raise ValueError("validation contains no non-tied examples")
    mean = statistics.fmean(cluster_means)
    if len(cluster_means) == 1:
        return _rounded(mean), _rounded(mean), _rounded(mean)
    standard_error = statistics.stdev(cluster_means) / math.sqrt(len(cluster_means))
    return (
        _rounded(mean),
        _rounded(mean - z_value * standard_error),
        _rounded(mean + z_value * standard_error),
    )
