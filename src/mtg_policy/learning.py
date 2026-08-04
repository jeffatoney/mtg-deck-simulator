"""Offline discovery-only learning public API."""

from mtg_policy.learning_io import (
    load_evaluator_snapshot,
    load_learning_dataset,
    write_learning_dataset,
    write_snapshot,
)
from mtg_policy.learning_mining import (
    mine_interaction_candidates,
    mine_organic_interaction_candidates,
)
from mtg_policy.learning_models import (
    ActionSignature,
    CounterfactualContract,
    DecisionContext,
    EvaluatorSnapshot,
    InteractionCandidate,
    LearningPlan,
    OrganicInteractionCandidate,
    OutcomeGuardrailSummary,
    OutcomeVector,
    PairwiseTrainingExample,
    VisibleCardRecord,
    load_learning_plan,
)
from mtg_policy.learning_training import train_evaluator_snapshot

__all__ = [
    "ActionSignature",
    "CounterfactualContract",
    "DecisionContext",
    "EvaluatorSnapshot",
    "InteractionCandidate",
    "LearningPlan",
    "OrganicInteractionCandidate",
    "OutcomeGuardrailSummary",
    "OutcomeVector",
    "PairwiseTrainingExample",
    "VisibleCardRecord",
    "load_evaluator_snapshot",
    "load_learning_dataset",
    "load_learning_plan",
    "mine_interaction_candidates",
    "mine_organic_interaction_candidates",
    "train_evaluator_snapshot",
    "write_learning_dataset",
    "write_snapshot",
]
