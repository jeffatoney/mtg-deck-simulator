#!/usr/bin/env python3
"""Validate the frozen strategic evaluator and discovery-only learning boundary."""

from __future__ import annotations

import json

from mtg_policy.config import load_policy_matrix
from mtg_policy.evaluation import declared_effect_kinds, load_evaluator_config
from mtg_policy.learning import load_learning_plan


def main() -> int:
    try:
        evaluator = load_evaluator_config()
        plan = load_learning_plan()
        policies = load_policy_matrix()
        mismatched = [
            bundle.policy_config_id
            for bundle in policies
            if bundle.value("evaluator_snapshot_id") != evaluator.evaluator_id
            or bundle.value("evaluator_snapshot_sha256") != evaluator.config_sha256
            or bundle.value("learning_plan_sha256") != plan.plan_sha256
        ]
        if mismatched:
            raise ValueError(f"policy bundles select a different evaluator: {mismatched}")
        if set(plan.required_feature_schema) != set(evaluator.weights) - {"intentional_neutral"}:
            raise ValueError("learning-plan feature schema differs from the baseline evaluator")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "reason": str(exc)}, indent=2))
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "evaluator_id": evaluator.evaluator_id,
                "evaluator_sha256": evaluator.config_sha256,
                "classified_effect_kind_count": len(declared_effect_kinds()),
                "unknown_effect_policy": "FAIL_CLOSED",
                "learning_plan_sha256": plan.plan_sha256,
                "discovery_example_count": plan.discovery_example_count,
                "validation_example_count": plan.validation_example_count,
                "discovery_seed_count": plan.discovery_seed_count,
                "validation_seed_count": plan.validation_seed_count,
                "comparisons_per_discovery_seed": plan.comparisons_per_discovery_seed,
                "comparisons_per_validation_seed": plan.comparisons_per_validation_seed,
                "mining_seed_count": plan.mining_seed_count,
                "confirmation_seed_count": plan.confirmation_seed_count,
                "minimum_relative_accuracy_improvement": plan.minimum_relative_accuracy_improvement,
                "interaction_activation_mode": "REVIEW_ONLY",
                "statistical_claim_mode": "HYPOTHESIS_RANKING_ONLY",
                "holdout_influence_allowed": False,
                "canonical_live_learning_allowed": False,
                "policy_bundle_count": len(policies),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
