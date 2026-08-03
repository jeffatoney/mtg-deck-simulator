"""Content-addressed evaluator snapshot and raw learning-dataset I/O."""

from __future__ import annotations
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast
from mtg_policy.learning_models import (
    ActionSignature,
    CounterfactualContract,
    DecisionContext,
    EvaluatorSnapshot,
    InteractionCandidate,
    OrganicInteractionCandidate,
    OutcomeGuardrailSummary,
    OutcomeVector,
    PairwiseTrainingExample,
    VisibleCardRecord,
    _digest,
    _ordered,
    _validate_safe_raw_payload,
)
from mtg_policy.learning_training import _snapshot_body


def load_evaluator_snapshot(path: Path) -> EvaluatorSnapshot:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "learned-evaluator-snapshot-v2":
        raise ValueError("unsupported learned evaluator snapshot")
    generic = tuple(
        InteractionCandidate(**value) for value in payload.get("generic_interaction_candidates", ())
    )
    organic = tuple(
        OrganicInteractionCandidate(**value)
        for value in payload.get("organic_interaction_candidates", ())
    )
    guardrails = OutcomeGuardrailSummary(**payload["outcome_guardrails"])
    fields = {
        key: value
        for key, value in payload.items()
        if key not in {"snapshot_id", "snapshot_sha256"}
    }
    actual_sha = _digest(_snapshot_body(fields))
    if str(payload.get("snapshot_sha256", "")) != actual_sha:
        raise ValueError("learned evaluator snapshot hash mismatch")
    if str(payload.get("snapshot_id", "")) != f"learned-evaluator-{actual_sha[:24]}":
        raise ValueError("learned evaluator snapshot ID mismatch")
    return EvaluatorSnapshot(
        schema_version=str(payload["schema_version"]),
        snapshot_id=str(payload["snapshot_id"]),
        snapshot_sha256=actual_sha,
        parent_evaluator_id=str(payload["parent_evaluator_id"]),
        parent_evaluator_sha256=str(payload["parent_evaluator_sha256"]),
        plan_sha256=str(payload["plan_sha256"]),
        feature_schema=tuple(str(value) for value in payload["feature_schema"]),
        learned_weights={
            str(key): float(value) for key, value in payload["learned_weights"].items()
        },
        discovery_examples=int(payload["discovery_examples"]),
        mining_examples=int(payload["mining_examples"]),
        confirmation_examples=int(payload["confirmation_examples"]),
        validation_examples=int(payload["validation_examples"]),
        discovery_data_sha256=str(payload["discovery_data_sha256"]),
        mining_data_sha256=str(payload["mining_data_sha256"]),
        confirmation_data_sha256=str(payload["confirmation_data_sha256"]),
        validation_data_sha256=str(payload["validation_data_sha256"]),
        feature_set_sha256=str(payload["feature_set_sha256"]),
        candidate_report_sha256=str(payload["candidate_report_sha256"]),
        baseline_validation_accuracy=float(payload["baseline_validation_accuracy"]),
        learned_validation_accuracy=float(payload["learned_validation_accuracy"]),
        validation_accuracy_improvement=float(payload["validation_accuracy_improvement"]),
        clustered_ci_lower=float(payload["clustered_ci_lower"]),
        clustered_ci_upper=float(payload["clustered_ci_upper"]),
        tie_count=int(payload["tie_count"]),
        generic_interaction_candidates=generic,
        organic_interaction_candidates=organic,
        outcome_guardrails=guardrails,
        promotion_failures=tuple(str(value) for value in payload["promotion_failures"]),
        status=str(payload["status"]),
    )


def write_snapshot(snapshot: EvaluatorSnapshot, root: Path) -> Path:
    payload = snapshot.to_dict()
    body = {
        key: value
        for key, value in payload.items()
        if key not in {"snapshot_id", "snapshot_sha256"}
    }
    if _digest(body) != snapshot.snapshot_sha256:
        raise ValueError("snapshot object does not match its content digest")
    directory = root / f"{snapshot.snapshot_id}-{snapshot.snapshot_sha256[:12]}"
    directory.mkdir(parents=True, exist_ok=False)
    output = directory / "snapshot.json"
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def write_learning_dataset(examples: Sequence[PairwiseTrainingExample], path: Path) -> str:
    """Write a canonical hidden-information-safe dataset and return its digest."""

    ordered = [example.to_dict() for example in _ordered(examples)]
    _validate_safe_raw_payload(ordered)
    digest = _digest(ordered)
    payload = {
        "schema_version": "pairwise-learning-dataset-v1",
        "example_count": len(ordered),
        "examples_sha256": digest,
        "examples": ordered,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return digest


def _outcome_from_data(value: Mapping[str, Any]) -> OutcomeVector:
    return OutcomeVector(
        full_table_kill=int(value["full_table_kill"]),
        legal_table_win_access=int(value["legal_table_win_access"]),
        protected_access=int(value["protected_access"]),
        independent_second_line=int(value["independent_second_line"]),
        negative_terminal_turn=int(value["negative_terminal_turn"]),
        negative_earliest_legal_attempt_turn=int(value["negative_earliest_legal_attempt_turn"]),
        checkpoint_table_kill_access=cast(
            tuple[int, int, int, int],
            tuple(int(item) for item in value.get("checkpoint_table_kill_access", (0, 0, 0, 0))),
        ),
        terminal_turn=(
            int(value["terminal_turn"]) if value.get("terminal_turn") is not None else None
        ),
        earliest_legal_attempt_turn=(
            int(value["earliest_legal_attempt_turn"])
            if value.get("earliest_legal_attempt_turn") is not None
            else None
        ),
    )


def load_learning_dataset(path: Path) -> tuple[PairwiseTrainingExample, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "pairwise-learning-dataset-v1":
        raise ValueError("unsupported learning dataset")
    raw_examples = payload.get("examples")
    if not isinstance(raw_examples, list):
        raise ValueError("learning dataset omits examples")
    _validate_safe_raw_payload(raw_examples)
    if int(payload.get("example_count", -1)) != len(raw_examples):
        raise ValueError("learning dataset example count mismatch")
    if str(payload.get("examples_sha256", "")) != _digest(raw_examples):
        raise ValueError("learning dataset digest mismatch")
    result: list[PairwiseTrainingExample] = []
    for raw in raw_examples:
        context_raw = raw.get("context")
        context = None
        if context_raw is not None:
            context = DecisionContext(
                decision_index=int(context_raw["decision_index"]),
                turn=int(context_raw["turn"]),
                phase=str(context_raw["phase"]),
                visible_cards=tuple(
                    VisibleCardRecord(**value) for value in context_raw["visible_cards"]
                ),
                legal_actions=tuple(
                    ActionSignature(**value) for value in context_raw["legal_actions"]
                ),
                prior_actions=tuple(
                    ActionSignature(**value) for value in context_raw["prior_actions"]
                ),
                mana_by_symbol=tuple(
                    (str(key), int(amount)) for key, amount in context_raw["mana_by_symbol"]
                ),
                lands_in_play=int(context_raw["lands_in_play"]),
                land_drop_remaining=int(context_raw["land_drop_remaining"]),
                combo_access=tuple(str(value) for value in context_raw.get("combo_access", ())),
                protected_combo_access=tuple(
                    str(value) for value in context_raw.get("protected_combo_access", ())
                ),
            )
        action_a = ActionSignature(**raw["action_a"]) if raw.get("action_a") else None
        action_b = ActionSignature(**raw["action_b"]) if raw.get("action_b") else None
        contract = (
            CounterfactualContract(**raw["counterfactual_contract"])
            if raw.get("counterfactual_contract")
            else None
        )
        result.append(
            PairwiseTrainingExample(
                example_id=str(raw["example_id"]),
                seed=int(raw["seed"]),
                decision_kind=str(raw["decision_kind"]),
                features_a={str(key): float(value) for key, value in raw["features_a"].items()},
                features_b={str(key): float(value) for key, value in raw["features_b"].items()},
                outcome_a=_outcome_from_data(raw["outcome_a"]),
                outcome_b=_outcome_from_data(raw["outcome_b"]),
                decision_index=int(raw.get("decision_index", 0)),
                context=context,
                action_a=action_a,
                action_b=action_b,
                available_card_identities_a=tuple(
                    str(value) for value in raw.get("available_card_identities_a", ())
                ),
                available_card_identities_b=tuple(
                    str(value) for value in raw.get("available_card_identities_b", ())
                ),
                counterfactual_contract=contract,
            )
        )
    return _ordered(result)
