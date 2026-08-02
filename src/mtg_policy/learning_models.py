"""Immutable data contracts for offline strategic-evaluator learning."""
from __future__ import annotations
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEARNING_PLAN = ROOT / "configs/evaluators/learning_plan_v1.yaml"
CHECKPOINTS = (5, 6, 8, 10)
FORBIDDEN_RAW_KEYS = {"object_id","object_ids","card_instance_id","card_instance_ids","library_order","future_events","future_random_outcomes"}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _rounded(value: float) -> float:
    """Canonicalize learned numeric output for stable content addressing."""

    rounded = round(float(value), 12)
    return 0.0 if rounded == -0.0 else rounded


@dataclass(frozen=True, order=True)
class OutcomeVector:
    """Frozen lexicographic label plus non-ordering outcome guardrail fields."""

    full_table_kill: int
    legal_table_win_access: int
    protected_access: int
    independent_second_line: int
    negative_terminal_turn: int
    negative_earliest_legal_attempt_turn: int
    checkpoint_table_kill_access: tuple[int, int, int, int] = field(
        default=(0, 0, 0, 0), compare=False
    )
    terminal_turn: int | None = field(default=None, compare=False)
    earliest_legal_attempt_turn: int | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        for value in (
            self.full_table_kill,
            self.legal_table_win_access,
            self.protected_access,
            self.independent_second_line,
            *self.checkpoint_table_kill_access,
        ):
            if value not in {0, 1}:
                raise ValueError("binary outcome-vector fields must be zero or one")
        if len(self.checkpoint_table_kill_access) != len(CHECKPOINTS):
            raise ValueError("outcome checkpoints must represent Turns 5, 6, 8, and 10")
        if self.terminal_turn is not None and self.terminal_turn < 1:
            raise ValueError("terminal turn must be positive")
        if self.earliest_legal_attempt_turn is not None and self.earliest_legal_attempt_turn < 1:
            raise ValueError("earliest legal attempt turn must be positive")


@dataclass(frozen=True, order=True)
class VisibleCardRecord:
    """One policy-visible card identity without an internal object identifier."""

    identity: str
    zone: str
    card_types: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.identity or not self.zone:
            raise ValueError("visible card records require identity and zone")


@dataclass(frozen=True, order=True)
class ActionSignature:
    """Stable public description of a legal or selected action."""

    kind: str
    identity: str
    mode: str = "default"
    tags: tuple[str, ...] = ()
    target_identities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.kind or not self.identity:
            raise ValueError("action signatures require kind and identity")

    @property
    def key(self) -> str:
        tags = ",".join(sorted(self.tags))
        targets = ",".join(sorted(self.target_identities))
        return f"{self.kind}|{self.identity}|{self.mode}|{tags}|{targets}"


@dataclass(frozen=True)
class DecisionContext:
    """Hidden-information-safe raw context preserved for later hypothesis mining."""

    decision_index: int
    turn: int
    phase: str
    visible_cards: tuple[VisibleCardRecord, ...]
    legal_actions: tuple[ActionSignature, ...]
    prior_actions: tuple[ActionSignature, ...]
    mana_by_symbol: tuple[tuple[str, int], ...]
    lands_in_play: int
    land_drop_remaining: int
    combo_access: tuple[str, ...] = ()
    protected_combo_access: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.decision_index < 1 or self.turn < 1:
            raise ValueError("decision context requires positive decision index and turn")
        if not self.phase:
            raise ValueError("decision context requires a phase")
        if self.lands_in_play < 0 or self.land_drop_remaining not in {0, 1}:
            raise ValueError("decision context has invalid land state")
        if any(amount < 0 for _, amount in self.mana_by_symbol):
            raise ValueError("decision context mana cannot be negative")


@dataclass(frozen=True)
class CounterfactualContract:
    """Proof fields binding both alternatives to one deterministic comparison."""

    initial_state_sha256: str
    future_rng_sha256: str
    continuation_policy_id: str
    continuation_policy_sha256: str
    evaluation_horizon_turn: int = 10
    same_initial_state: bool = True
    same_future_rng_streams: bool = True
    same_continuation_policy: bool = True
    hidden_information_boundary: str = "POLICY_OBSERVATION_ONLY"
    tie_handling: str = "EXCLUDE_FROM_ACCURACY_REPORT_SEPARATELY"

    def __post_init__(self) -> None:
        hashes = (
            self.initial_state_sha256,
            self.future_rng_sha256,
            self.continuation_policy_sha256,
        )
        if any(len(value) != 64 for value in hashes):
            raise ValueError("counterfactual contract hashes must be SHA-256 digests")
        if not self.continuation_policy_id:
            raise ValueError("counterfactual contract requires a continuation policy")
        if self.evaluation_horizon_turn != 10:
            raise ValueError("counterfactual learning horizon must remain Turn 10")
        if not all(
            (self.same_initial_state, self.same_future_rng_streams, self.same_continuation_policy)
        ):
            raise ValueError("paired alternatives must differ only in the selected decision")
        if self.hidden_information_boundary != "POLICY_OBSERVATION_ONLY":
            raise ValueError("counterfactual comparison exposes an invalid information boundary")
        if self.tie_handling != "EXCLUDE_FROM_ACCURACY_REPORT_SEPARATELY":
            raise ValueError("counterfactual tie handling differs from the frozen contract")


@dataclass(frozen=True)
class PairwiseTrainingExample:
    example_id: str
    seed: int
    decision_kind: str
    features_a: Mapping[str, float]
    features_b: Mapping[str, float]
    outcome_a: OutcomeVector
    outcome_b: OutcomeVector
    decision_index: int = 0
    context: DecisionContext | None = None
    action_a: ActionSignature | None = None
    action_b: ActionSignature | None = None
    available_card_identities_a: tuple[str, ...] = ()
    available_card_identities_b: tuple[str, ...] = ()
    counterfactual_contract: CounterfactualContract | None = None

    def __post_init__(self) -> None:
        if not self.example_id or not self.decision_kind:
            raise ValueError("learning examples require an ID and decision kind")
        if self.seed < 0 or self.decision_index < 0:
            raise ValueError("learning example seed and decision index cannot be negative")
        if self.context is not None and self.decision_index not in {0, self.context.decision_index}:
            raise ValueError("example and context decision indexes differ")
        if len(set(self.available_card_identities_a)) != len(self.available_card_identities_a):
            raise ValueError("alternative A card identities contain duplicates")
        if len(set(self.available_card_identities_b)) != len(self.available_card_identities_b):
            raise ValueError("alternative B card identities contain duplicates")

    @property
    def preferred_side(self) -> int:
        if self.outcome_a == self.outcome_b:
            return 0
        return 1 if self.outcome_a > self.outcome_b else -1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LearningPlan:
    plan_sha256: str
    algorithm: str
    discovery_example_count: int
    validation_example_count: int
    regularization: float
    minimum_validation_accuracy: float
    feature_cross_candidate_min_support: int
    feature_cross_candidate_top_n: int
    required_feature_schema: tuple[str, ...] = ()
    discovery_seed_count: int = 300
    validation_seed_count: int = 200
    comparisons_per_discovery_seed: int = 16
    comparisons_per_validation_seed: int = 5
    mining_seed_count: int = 200
    confirmation_seed_count: int = 100
    minimum_relative_accuracy_improvement: float = 0.03
    confidence_z: float = 1.96
    require_clustered_ci_lower_above_zero: bool = True
    require_outcome_non_regression: bool = True
    require_raw_context: bool = True
    organic_candidate_min_support: int = 50
    organic_candidate_min_distinct_seeds: int = 20
    organic_candidate_min_mining_support: int = 34
    organic_candidate_min_confirmation_support: int = 16
    organic_candidate_top_n: int = 20


@dataclass(frozen=True)
class InteractionCandidate:
    """Review-only nonlinear generic-feature candidate."""

    feature_a: str
    feature_b: str
    support: int
    residual_coefficient: float
    mean_absolute_signal: float
    status: str = "REVIEW_REQUIRED"


@dataclass(frozen=True)
class OrganicInteractionCandidate:
    """Review-only card-pair or action-sequence hypothesis."""

    candidate_type: Literal["CARD_PAIR", "ACTION_SEQUENCE"]
    members: tuple[str, ...]
    mining_support: int
    mining_distinct_seeds: int
    mining_residual_coefficient: float
    confirmation_support: int
    confirmation_distinct_seeds: int
    confirmation_residual_coefficient: float
    same_direction_confirmed: bool
    representative_example_ids: tuple[str, ...]
    status: str = "REVIEW_REQUIRED"
    statistical_claim: str = "HYPOTHESIS_RANKING_ONLY_NO_SIGNIFICANCE_CLAIM"
    auto_activation_allowed: bool = False


@dataclass(frozen=True)
class OutcomeGuardrailSummary:
    baseline_checkpoint_access: tuple[float, float, float, float]
    learned_checkpoint_access: tuple[float, float, float, float]
    baseline_full_table_kill_rate: float
    learned_full_table_kill_rate: float
    baseline_median_earliest_attempt_turn: float
    learned_median_earliest_attempt_turn: float
    passed: bool


@dataclass(frozen=True)
class EvaluatorSnapshot:
    schema_version: str
    snapshot_id: str
    snapshot_sha256: str
    parent_evaluator_id: str
    parent_evaluator_sha256: str
    plan_sha256: str
    feature_schema: tuple[str, ...]
    learned_weights: Mapping[str, float]
    discovery_examples: int
    mining_examples: int
    confirmation_examples: int
    validation_examples: int
    discovery_data_sha256: str
    mining_data_sha256: str
    confirmation_data_sha256: str
    validation_data_sha256: str
    feature_set_sha256: str
    candidate_report_sha256: str
    baseline_validation_accuracy: float
    learned_validation_accuracy: float
    validation_accuracy_improvement: float
    clustered_ci_lower: float
    clustered_ci_upper: float
    tie_count: int
    generic_interaction_candidates: tuple[InteractionCandidate, ...]
    organic_interaction_candidates: tuple[OrganicInteractionCandidate, ...]
    outcome_guardrails: OutcomeGuardrailSummary
    promotion_failures: tuple[str, ...]
    status: str

    @property
    def validation_accuracy(self) -> float:
        """Compatibility alias for the learned validation accuracy."""

        return self.learned_validation_accuracy

    @property
    def interaction_candidates(self) -> tuple[InteractionCandidate, ...]:
        """Compatibility alias for the generic review-only candidates."""

        return self.generic_interaction_candidates

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_learning_plan(path: Path | None = None) -> LearningPlan:
    payload = json.loads((path or DEFAULT_LEARNING_PLAN).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "evaluator-learning-plan-v2":
        raise ValueError("unsupported evaluator learning plan")
    recorded = str(payload.get("plan_sha256", ""))
    body = {key: value for key, value in payload.items() if key != "plan_sha256"}
    if recorded != _digest(body):
        raise ValueError("evaluator learning plan hash mismatch")
    if payload.get("training_mode") != "DISCOVERY_ONLY":
        raise ValueError("evaluator training must be discovery-only")
    if payload.get("holdout_influence_allowed") is not False:
        raise ValueError("validation examples may not influence learned weights")
    if payload.get("interaction_activation_mode") != "REVIEW_ONLY":
        raise ValueError("organic interactions must remain review-only")
    if payload.get("statistical_claim_mode") != "HYPOTHESIS_RANKING_ONLY":
        raise ValueError("interaction miner may not claim uncorrected significance")
    schema = tuple(str(value) for value in payload.get("required_feature_schema", ()))
    if not schema or len(schema) != len(set(schema)):
        raise ValueError("learning plan requires a unique nonempty feature schema")
    return LearningPlan(
        plan_sha256=recorded,
        algorithm=str(payload["algorithm"]),
        discovery_example_count=int(payload["discovery_example_count"]),
        validation_example_count=int(payload["validation_example_count"]),
        regularization=float(payload["regularization"]),
        minimum_validation_accuracy=float(payload.get("minimum_validation_accuracy", 0.0)),
        feature_cross_candidate_min_support=int(payload["feature_cross_candidate_min_support"]),
        feature_cross_candidate_top_n=int(payload["feature_cross_candidate_top_n"]),
        required_feature_schema=schema,
        discovery_seed_count=int(payload["discovery_seed_count"]),
        validation_seed_count=int(payload["validation_seed_count"]),
        comparisons_per_discovery_seed=int(payload["comparisons_per_discovery_seed"]),
        comparisons_per_validation_seed=int(payload["comparisons_per_validation_seed"]),
        mining_seed_count=int(payload["mining_seed_count"]),
        confirmation_seed_count=int(payload["confirmation_seed_count"]),
        minimum_relative_accuracy_improvement=float(
            payload["minimum_relative_accuracy_improvement"]
        ),
        confidence_z=float(payload["confidence_z"]),
        require_clustered_ci_lower_above_zero=bool(
            payload["require_clustered_ci_lower_above_zero"]
        ),
        require_outcome_non_regression=bool(payload["require_outcome_non_regression"]),
        require_raw_context=bool(payload["require_raw_context"]),
        organic_candidate_min_support=int(payload["organic_candidate_min_support"]),
        organic_candidate_min_distinct_seeds=int(
            payload["organic_candidate_min_distinct_seeds"]
        ),
        organic_candidate_min_mining_support=int(
            payload["organic_candidate_min_mining_support"]
        ),
        organic_candidate_min_confirmation_support=int(
            payload["organic_candidate_min_confirmation_support"]
        ),
        organic_candidate_top_n=int(payload["organic_candidate_top_n"]),
    )


def _ordered(examples: Sequence[PairwiseTrainingExample]) -> tuple[PairwiseTrainingExample, ...]:
    return tuple(sorted(examples, key=lambda item: (item.seed, item.decision_index, item.example_id)))


def _validate_safe_raw_payload(value: Any, path: str = "record") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            text = str(key)
            if text in FORBIDDEN_RAW_KEYS:
                raise ValueError(f"learning raw record exposes forbidden key {path}.{text}")
            _validate_safe_raw_payload(child, f"{path}.{text}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _validate_safe_raw_payload(child, f"{path}[{index}]")
