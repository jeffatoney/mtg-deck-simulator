"""Feature freezing, refitting, holdout validation, and promotion decisions."""
from __future__ import annotations
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any, cast
import numpy as np
from mtg_policy.learning_models import CHECKPOINTS, EvaluatorSnapshot, LearningPlan, OutcomeGuardrailSummary, OutcomeVector, PairwiseTrainingExample, _digest, _ordered, _rounded
from mtg_policy.learning_mining import mine_interaction_candidates, mine_organic_interaction_candidates
from mtg_policy.learning_validation import _accuracy_details, _clustered_difference_interval, _fit_ridge, _matrix, _validate_examples, _weight_vector


def _selected_outcomes(
    examples: Sequence[PairwiseTrainingExample], predictions: Sequence[float]
) -> tuple[OutcomeVector, ...]:
    return tuple(
        example.outcome_a if int(prediction) == 1 else example.outcome_b
        for example, prediction in zip(examples, predictions, strict=True)
    )


def _outcome_guardrails(
    examples: Sequence[PairwiseTrainingExample],
    baseline_predictions: Sequence[float],
    learned_predictions: Sequence[float],
    *,
    required: bool,
) -> OutcomeGuardrailSummary:
    baseline = _selected_outcomes(examples, baseline_predictions)
    learned = _selected_outcomes(examples, learned_predictions)

    def checkpoint_rates(values: Sequence[OutcomeVector]) -> tuple[float, float, float, float]:
        result = tuple(
            _rounded(statistics.fmean(value.checkpoint_table_kill_access[index] for value in values))
            for index in range(len(CHECKPOINTS))
        )
        if len(result) != 4:
            raise AssertionError("checkpoint guardrail shape changed")
        return cast(tuple[float, float, float, float], result)

    def earliest(values: Sequence[OutcomeVector]) -> float:
        turns = [
            value.earliest_legal_attempt_turn
            if value.earliest_legal_attempt_turn is not None
            else 11
            for value in values
        ]
        return _rounded(float(statistics.median(turns)))

    baseline_checkpoints = checkpoint_rates(baseline)
    learned_checkpoints = checkpoint_rates(learned)
    baseline_kills = _rounded(statistics.fmean(value.full_table_kill for value in baseline))
    learned_kills = _rounded(statistics.fmean(value.full_table_kill for value in learned))
    baseline_earliest = earliest(baseline)
    learned_earliest = earliest(learned)
    passed = (
        not required
        or (
            all(new >= old for new, old in zip(learned_checkpoints, baseline_checkpoints, strict=True))
            and learned_kills >= baseline_kills
            and learned_earliest <= baseline_earliest
        )
    )
    return OutcomeGuardrailSummary(
        baseline_checkpoints,
        learned_checkpoints,
        baseline_kills,
        learned_kills,
        baseline_earliest,
        learned_earliest,
        passed,
    )


def _snapshot_body(snapshot_fields: Mapping[str, Any]) -> dict[str, Any]:
    return dict(snapshot_fields)


def train_evaluator_snapshot(
    *,
    parent_evaluator_id: str,
    parent_evaluator_sha256: str,
    discovery: Sequence[PairwiseTrainingExample],
    validation: Sequence[PairwiseTrainingExample],
    plan: LearningPlan,
    baseline_weights: Mapping[str, float] | None = None,
    enforce_plan_counts: bool = True,
) -> EvaluatorSnapshot:
    """Mine, confirm, freeze, refit, then score once on untouched validation."""

    discovery = _ordered(discovery)
    validation = _ordered(validation)
    schema = _validate_examples(
        discovery,
        validation,
        plan,
        enforce_plan_counts=enforce_plan_counts,
    )
    if enforce_plan_counts:
        from mtg_policy.config import load_seed_split

        frozen_split = load_seed_split()
        discovery_seed_order = list(frozen_split.discovery)
        if baseline_weights is None:
            raise ValueError("authoritative learning requires the human baseline weights")
        if set(schema) - set(baseline_weights):
            raise ValueError("human baseline weights do not cover the frozen feature schema")
    else:
        discovery_seed_order = sorted({example.seed for example in discovery})
    if len(discovery_seed_order) < plan.mining_seed_count + plan.confirmation_seed_count:
        if enforce_plan_counts:
            raise ValueError("discovery examples cannot satisfy mining/confirmation split")
        mining_seeds = set(discovery_seed_order[: max(1, len(discovery_seed_order) // 2)])
    else:
        mining_seeds = set(discovery_seed_order[: plan.mining_seed_count])
    mining_examples = tuple(example for example in discovery if example.seed in mining_seeds)
    confirmation_examples = tuple(example for example in discovery if example.seed not in mining_seeds)
    if not confirmation_examples:
        confirmation_examples = mining_examples

    mining_x, mining_y, _ = _matrix(mining_examples, schema)
    mining_weights = _fit_ridge(mining_x, mining_y, plan.regularization)
    generic_candidates = mine_interaction_candidates(
        mining_examples,
        schema,
        mining_weights,
        minimum_support=plan.feature_cross_candidate_min_support,
        top_n=plan.feature_cross_candidate_top_n,
    )
    organic_candidates = mine_organic_interaction_candidates(
        mining_examples,
        confirmation_examples,
        schema,
        mining_weights,
        plan,
    )

    discovery_x, discovery_y, _ = _matrix(discovery, schema)
    learned_vector = _fit_ridge(discovery_x, discovery_y, plan.regularization)
    baseline_vector = _weight_vector(schema, baseline_weights or {})
    validation_x, validation_y, retained_validation = _matrix(validation, schema)
    learned_accuracy, learned_predictions, learned_correct = _accuracy_details(
        validation_x, validation_y, learned_vector
    )
    baseline_accuracy, baseline_predictions, baseline_correct = _accuracy_details(
        validation_x, validation_y, baseline_vector
    )
    improvement, ci_lower, ci_upper = _clustered_difference_interval(
        retained_validation,
        learned_correct,
        baseline_correct,
        plan.confidence_z,
    )
    guardrails = _outcome_guardrails(
        retained_validation,
        baseline_predictions,
        learned_predictions,
        required=plan.require_outcome_non_regression,
    )
    failures: list[str] = []
    if learned_accuracy < plan.minimum_validation_accuracy:
        failures.append("ABSOLUTE_VALIDATION_ACCURACY_BELOW_MINIMUM")
    if improvement < plan.minimum_relative_accuracy_improvement:
        failures.append("RELATIVE_VALIDATION_IMPROVEMENT_BELOW_THREE_POINTS")
    if plan.require_clustered_ci_lower_above_zero and ci_lower <= 0.0:
        failures.append("SEED_CLUSTERED_CONFIDENCE_LOWER_BOUND_NOT_ABOVE_ZERO")
    if not guardrails.passed:
        failures.append("DIRECT_OUTCOME_GUARDRAIL_REGRESSION")

    learned = {name: _rounded(learned_vector[index]) for index, name in enumerate(schema)}
    discovery_sha = _digest([example.to_dict() for example in discovery])
    mining_sha = _digest([example.to_dict() for example in _ordered(mining_examples)])
    confirmation_sha = _digest([example.to_dict() for example in _ordered(confirmation_examples)])
    validation_sha = _digest([example.to_dict() for example in validation])
    feature_set_sha = _digest({"feature_schema": schema, "candidate_activation": "NONE"})
    candidate_report = {
        "generic": [asdict(value) for value in generic_candidates],
        "organic": [asdict(value) for value in organic_candidates],
        "activation_mode": "REVIEW_ONLY",
        "statistical_claim_mode": "HYPOTHESIS_RANKING_ONLY",
    }
    candidate_report_sha = _digest(candidate_report)
    status = "FROZEN_VALIDATED" if not failures else "REJECTED_VALIDATION"
    fields: dict[str, Any] = {
        "schema_version": "learned-evaluator-snapshot-v2",
        "parent_evaluator_id": parent_evaluator_id,
        "parent_evaluator_sha256": parent_evaluator_sha256,
        "plan_sha256": plan.plan_sha256,
        "feature_schema": schema,
        "learned_weights": learned,
        "discovery_examples": len(discovery),
        "mining_examples": len(mining_examples),
        "confirmation_examples": len(confirmation_examples),
        "validation_examples": len(validation),
        "discovery_data_sha256": discovery_sha,
        "mining_data_sha256": mining_sha,
        "confirmation_data_sha256": confirmation_sha,
        "validation_data_sha256": validation_sha,
        "feature_set_sha256": feature_set_sha,
        "candidate_report_sha256": candidate_report_sha,
        "baseline_validation_accuracy": _rounded(baseline_accuracy),
        "learned_validation_accuracy": _rounded(learned_accuracy),
        "validation_accuracy_improvement": improvement,
        "clustered_ci_lower": ci_lower,
        "clustered_ci_upper": ci_upper,
        "tie_count": len(validation) - len(retained_validation),
        "generic_interaction_candidates": [asdict(value) for value in generic_candidates],
        "organic_interaction_candidates": [asdict(value) for value in organic_candidates],
        "outcome_guardrails": asdict(guardrails),
        "promotion_failures": tuple(failures),
        "status": status,
    }
    snapshot_sha = _digest(_snapshot_body(fields))
    snapshot_id = f"learned-evaluator-{snapshot_sha[:24]}"
    return EvaluatorSnapshot(
        schema_version="learned-evaluator-snapshot-v2",
        snapshot_id=snapshot_id,
        snapshot_sha256=snapshot_sha,
        parent_evaluator_id=parent_evaluator_id,
        parent_evaluator_sha256=parent_evaluator_sha256,
        plan_sha256=plan.plan_sha256,
        feature_schema=schema,
        learned_weights=learned,
        discovery_examples=len(discovery),
        mining_examples=len(mining_examples),
        confirmation_examples=len(confirmation_examples),
        validation_examples=len(validation),
        discovery_data_sha256=discovery_sha,
        mining_data_sha256=mining_sha,
        confirmation_data_sha256=confirmation_sha,
        validation_data_sha256=validation_sha,
        feature_set_sha256=feature_set_sha,
        candidate_report_sha256=candidate_report_sha,
        baseline_validation_accuracy=_rounded(baseline_accuracy),
        learned_validation_accuracy=_rounded(learned_accuracy),
        validation_accuracy_improvement=improvement,
        clustered_ci_lower=ci_lower,
        clustered_ci_upper=ci_upper,
        tie_count=len(validation) - len(retained_validation),
        generic_interaction_candidates=generic_candidates,
        organic_interaction_candidates=organic_candidates,
        outcome_guardrails=guardrails,
        promotion_failures=tuple(failures),
        status=status,
    )
