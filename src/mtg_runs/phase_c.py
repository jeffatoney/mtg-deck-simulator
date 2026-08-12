"""Fail-closed Phase C pilot configuration, readiness, and authorization controls."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from mtg_deck import load_exact_deck_package
from mtg_runs.phase_c_pairing import (
    OUTCOME_NAME,
    PAIR_SELECTION_RULE,
    PAIRED_BOOTSTRAP_RESAMPLES,
    PAIRED_CHECKPOINT_TURN,
    PAIRED_CI_CONFIDENCE,
    PAIRED_CI_METHOD,
    PAIRED_GAME_COUNT,
    PAIRS_PER_STANDARD_SHARD,
    PILOT_EFFECT_THRESHOLD_RULE,
    PRIMARY_OUTCOME,
    REPORTING_SENTENCE,
    SECONDARY_CENSORING_RULE,
    SECONDARY_OUTCOME,
    PairedAnalysisConfiguration,
    build_pairing_plan,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json"
DEFAULT_APPROVAL = ROOT / "docs/spec/phase-c/PHASE_C_PILOT_APPROVAL.json"
DEFAULT_WORKFLOW = ROOT / ".github/workflows/phase-c-pilot.yml"
CONFIRMATION_TOKEN = "AUTHORIZE_PHASE_C_500_STANDARD_200_EXPLORATORY"
STANDARD_GAMES = 500
EXPLORATORY_GAMES = 200
STANDARD_SHARDS = 10
EXPLORATORY_SHARDS = 10
PILOT_PRODUCTION_DECISION_LAYER_DEPTH = 1
_ACTIVATION_ALLOWLIST = {
    "docs/spec/phase-c/PHASE_C_PILOT_APPROVAL.json",
    "docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json",
}


class PhaseCControlError(ValueError):
    """Raised whenever Phase C validation fails closed."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def file_sha256(path: Path) -> str:
    if not path.is_file():
        raise PhaseCControlError(f"required Phase C file is missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PhaseCControlError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise PhaseCControlError(f"{label} must be a JSON object")
    return value


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PhaseCControlError(f"{label} must be an object")
    return value


def _exact(value: object, expected: object, label: str) -> None:
    if value != expected:
        raise PhaseCControlError(f"{label} must be {expected!r}, received {value!r}")


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _is_git_object_id(value: str) -> bool:
    return len(value) == 40 and all(char in "0123456789abcdef" for char in value)


def _is_rfc3339_utc(value: str) -> bool:
    return re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value) is not None


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise PhaseCControlError(f"Git validation failed: {' '.join(args)}") from exc


def _git_file(root: Path, commit: str, path: Path) -> bytes:
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    try:
        return subprocess.check_output(["git", "show", f"{commit}:{relative}"], cwd=root)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise PhaseCControlError(
            f"required file is unavailable at implementation commit: {relative}"
        ) from exc


def _git_file_sha256(root: Path, commit: str, path: Path) -> str:
    return hashlib.sha256(_git_file(root, commit, path)).hexdigest()


@dataclass(frozen=True)
class PilotShardAssignment:
    mode: str
    shard_index: int
    shard_count: int
    first_game_index: int
    last_game_index: int
    seeds: tuple[int, ...]
    pair_ids: tuple[str | None, ...]
    paired_standard_game_indexes: tuple[int | None, ...]
    search_seeds: tuple[int | None, ...]

    def __post_init__(self) -> None:
        if self.mode not in {"STANDARD", "EXPLORATORY"}:
            raise PhaseCControlError("pilot shard mode must be STANDARD or EXPLORATORY")
        if self.shard_count < 1 or not (0 <= self.shard_index < self.shard_count):
            raise PhaseCControlError("pilot shard index/count is invalid")
        if self.first_game_index < 1 or self.last_game_index < self.first_game_index:
            raise PhaseCControlError("pilot shard game-index range is invalid")
        if len(self.seeds) != self.last_game_index - self.first_game_index + 1:
            raise PhaseCControlError("pilot shard seed assignment does not match its range")
        if len(self.seeds) != len(set(self.seeds)):
            raise PhaseCControlError("pilot shard contains duplicate seeds")
        if not (
            len(self.pair_ids)
            == len(self.paired_standard_game_indexes)
            == len(self.search_seeds)
            == len(self.seeds)
        ):
            raise PhaseCControlError("pilot shard pairing metadata does not match seed count")
        if self.mode == "STANDARD":
            if any(value is not None for value in self.search_seeds):
                raise PhaseCControlError("standard shard cannot contain exploratory search seeds")
        else:
            if any(value is None for value in self.pair_ids):
                raise PhaseCControlError("exploratory shard requires pair IDs")
            if any(value is None for value in self.paired_standard_game_indexes):
                raise PhaseCControlError("exploratory shard requires paired standard indexes")
            if any(value is None for value in self.search_seeds):
                raise PhaseCControlError("exploratory shard requires search seeds")


@dataclass(frozen=True)
class PilotSeedPlan:
    standard: tuple[int, ...]
    exploratory: tuple[int, ...]
    exploratory_search: tuple[int, ...]
    paired_standard_game_indexes: tuple[int, ...]
    pair_ids: tuple[str, ...]
    standard_sha256: str
    exploratory_sha256: str
    exploratory_search_sha256: str
    pair_assignment_sha256: str

    def __post_init__(self) -> None:
        if len(self.standard) != STANDARD_GAMES:
            raise PhaseCControlError("standard seed count is not exactly 500")
        if len(self.exploratory) != EXPLORATORY_GAMES:
            raise PhaseCControlError("exploratory seed count is not exactly 200")
        if len(set(self.standard)) != len(self.standard):
            raise PhaseCControlError("standard pilot seed plan contains duplicates")
        if len(set(self.exploratory)) != len(self.exploratory):
            raise PhaseCControlError("exploratory paired environment seeds contain duplicates")
        if not set(self.exploratory).issubset(self.standard):
            raise PhaseCControlError("exploratory environment seeds must be a standard subset")
        if (
            len(self.exploratory_search) != EXPLORATORY_GAMES
            or len(set(self.exploratory_search)) != EXPLORATORY_GAMES
        ):
            raise PhaseCControlError("exploratory search seed plan must contain 200 unique seeds")
        if set(self.exploratory_search).intersection(self.standard):
            raise PhaseCControlError("environment and search seed domains must not overlap")
        if (
            len(self.paired_standard_game_indexes) != PAIRED_GAME_COUNT
            or len(self.pair_ids) != PAIRED_GAME_COUNT
        ):
            raise PhaseCControlError("paired pilot metadata must contain exactly 200 pairs")


@dataclass(frozen=True)
class PhaseCConfiguration:
    path: Path
    payload: Mapping[str, Any]
    sha256: str
    paired_analysis: PairedAnalysisConfiguration
    deck_exact_library_count: int
    deck_physical_card_count: int
    deck_commanders: tuple[str, ...]
    deck_source: str
    confirmation_token: str
    execution_allowed: bool
    authorization_status: str
    standard_games: int
    exploratory_games: int
    environment_seed_namespace: str
    exploratory_search_seed_namespace: str
    policy_config_id: str
    policy_config_hash: str
    evaluator_snapshot_id: str
    evaluator_snapshot_sha256: str
    learning_plan_sha256: str
    exploratory_production_decision_layer_depth: int
    standard_shards: int
    exploratory_shards: int


@dataclass(frozen=True)
class PhaseCApproval:
    path: Path
    payload: Mapping[str, Any]
    sha256: str
    status: str
    approved_by: str | None
    approved_at: str | None
    implementation_commit: str | None
    implementation_tree: str | None
    locked_pilot_config_sha256: str | None
    workflow_sha256: str | None
    confirmation_token_sha256: str
    production_decision_layer_depth: int
    standard_shards: int
    exploratory_shards: int
    approval_statement: str | None


@dataclass(frozen=True)
class PhaseCAuthorizationContext:
    implementation_commit: str
    implementation_tree: str
    activation_commit: str
    locked_config_sha256: str
    workflow_sha256: str

    def __post_init__(self) -> None:
        for label, value in (
            ("implementation commit", self.implementation_commit),
            ("implementation tree", self.implementation_tree),
            ("activation commit", self.activation_commit),
        ):
            if not _is_git_object_id(value):
                raise PhaseCControlError(f"{label} must be a lowercase 40-character Git object ID")
        if not _is_sha256(self.locked_config_sha256) or not _is_sha256(self.workflow_sha256):
            raise PhaseCControlError("authorization content bindings must be SHA-256 digests")


@dataclass(frozen=True)
class PhaseCDryRunReport:
    schema_version: str
    status: str
    config_sha256: str
    approval_record_sha256: str
    workflow_sha256: str
    policy_config_id: str
    evaluator_snapshot_id: str
    standard_game_count: int
    exploratory_game_count: int
    standard_seed_sha256: str
    exploratory_seed_sha256: str
    exploratory_search_seed_sha256: str
    pair_assignment_sha256: str
    paired_game_count: int
    execution_allowed: bool
    authorization_status: str
    readiness_blockers: tuple[str, ...]
    readiness_evidence: Mapping[str, Mapping[str, Any]]
    exploratory_production_decision_layer_depth: int
    game_results_created: int
    full_study_execution_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _required_text(mapping: Mapping[str, Any], key: str, label: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise PhaseCControlError(f"{label} must be a nonempty string")
    return value


def _required_int(mapping: Mapping[str, Any], key: str, label: str) -> int:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise PhaseCControlError(f"{label} must be an integer")
    return value


def _required_float(mapping: Mapping[str, Any], key: str, label: str) -> float:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhaseCControlError(f"{label} must be numeric")
    return float(value)


def _parse_paired_analysis_configuration(
    paired: Mapping[str, Any],
) -> PairedAnalysisConfiguration:
    return PairedAnalysisConfiguration(
        primary_outcome=_required_text(paired, "primary_outcome", "paired primary outcome"),
        outcome_name=_required_text(paired, "outcome_name", "paired outcome name"),
        secondary_outcome=_required_text(paired, "secondary_outcome", "paired secondary outcome"),
        secondary_censoring_rule=_required_text(
            paired, "secondary_censoring_rule", "paired secondary censoring rule"
        ),
        effect_threshold_rule=_required_text(
            paired, "effect_threshold_rule", "paired effect-threshold rule"
        ),
        required_reporting_sentence=_required_text(
            paired, "required_reporting_sentence", "paired reporting sentence"
        ),
        paired_game_count=_required_int(paired, "paired_game_count", "paired game count"),
        pairs_per_standard_shard=_required_int(
            paired, "pairs_per_standard_shard", "pairs per standard shard"
        ),
        pair_selection_rule=_required_text(paired, "pair_selection_rule", "pair selection rule"),
        checkpoint_turn=_required_int(paired, "checkpoint_turn", "paired checkpoint"),
        mcnemar_test=_required_text(paired, "mcnemar_test", "paired test"),
        confidence_interval_method=_required_text(
            paired, "confidence_interval_method", "paired confidence interval"
        ),
        confidence_level=_required_float(paired, "confidence_level", "paired confidence level"),
        bootstrap_resamples=_required_int(
            paired, "bootstrap_resamples", "paired bootstrap resamples"
        ),
    )


def _validate_scope(payload: Mapping[str, Any]) -> None:
    full_study = _mapping(payload.get("full_study"), "full_study")
    search = _mapping(payload.get("exploratory_search"), "exploratory_search")
    model = _mapping(payload.get("game_model"), "game_model")
    deck = _mapping(payload.get("deck"), "deck")
    measurement = _mapping(payload.get("measurement"), "measurement")
    mulligan = _mapping(payload.get("mulligan"), "mulligan")
    prerequisites = _mapping(payload.get("prerequisites"), "prerequisites")
    paired = _mapping(payload.get("paired_analysis"), "paired_analysis")

    _exact(full_study.get("execution_allowed"), False, "full-study flag")
    _exact(full_study.get("standard_games"), 20_000, "full-study count")
    _exact(full_study.get("exploratory_games"), 5_000, "full-study count")
    _exact(search.get("future_information_allowed"), False, "future information")
    _exact(search.get("post_result_optimization_allowed"), False, "post-result optimization")
    _exact(search.get("bounded"), True, "bounded search")
    _exact(search.get("rules_validation_required"), True, "search validation")
    _exact(search.get("reported_separately"), True, "separate reporting")
    _exact(
        search.get("production_decision_layer_depth"),
        PILOT_PRODUCTION_DECISION_LAYER_DEPTH,
        "exploratory production decision-layer depth",
    )

    _exact(model.get("players"), 4, "player count")
    _exact(model.get("opponents"), 3, "opponent count")
    _exact(model.get("end_after_controlled_turn"), 10, "turn horizon")
    _exact(model.get("controlled_player_draws_on_turn_one"), True, "Turn 1 draw")
    _exact(model.get("opponent_interaction_modeled"), False, "interaction")
    _exact(model.get("blocking_modeled"), False, "blocking")
    _exact(model.get("opponent_wins_modeled"), False, "opponent wins")
    _exact(
        model.get("breeches_unknown_cards_added_as_deterministic_resources"),
        False,
        "Breeches boundary",
    )

    package = load_exact_deck_package()
    _exact(deck.get("exact_library_count"), package.library_count, "exact library count")
    _exact(
        deck.get("physical_card_count"),
        package.physical_card_count,
        "physical card count",
    )
    _exact(
        deck.get("commanders"),
        [entry.name for entry in package.commanders],
        "deck commanders",
    )
    _exact(deck.get("source"), "docs/source/decklist.txt", "deck source")

    _exact(measurement.get("primary_checkpoint"), 8, "primary checkpoint")
    _exact(measurement.get("additional_checkpoints"), [5, 6, 10], "checkpoints")
    _exact(
        measurement.get("objective"),
        "MAXIMIZE_LEGAL_DETERMINISTIC_TABLE_WIN_ACCESS",
        "measurement objective",
    )
    _exact(mulligan.get("candidate_hand_sizes"), [7, 7, 6, 5, 4], "mulligan")
    _exact(mulligan.get("refill_kept_hand_to"), 7, "mulligan refill")
    _exact(mulligan.get("stop_below_four"), True, "mulligan floor")
    _exact(mulligan.get("rejected_hands_returned_and_shuffled"), True, "mulligan shuffle")

    _exact(prerequisites.get("clean_engine_only"), True, "clean engine")
    _exact(prerequisites.get("legacy_import_allowed"), False, "legacy import")
    _exact(prerequisites.get("phase_a_verifier_required"), "PASS", "Phase A")
    _exact(prerequisites.get("phase_b_verifier_required"), "PASS", "Phase B")
    _exact(prerequisites.get("phase_b_certification_required"), "PASS", "Phase B certification")
    _exact(prerequisites.get("post_merge_main_ci_required"), "PASS", "post-merge main CI")

    _exact(paired.get("primary_outcome"), PRIMARY_OUTCOME, "paired primary outcome")
    _exact(paired.get("outcome_name"), OUTCOME_NAME, "paired outcome name")
    _exact(paired.get("secondary_outcome"), SECONDARY_OUTCOME, "paired secondary outcome")
    _exact(
        paired.get("secondary_censoring_rule"),
        SECONDARY_CENSORING_RULE,
        "paired secondary censoring rule",
    )
    _exact(
        paired.get("effect_threshold_rule"),
        PILOT_EFFECT_THRESHOLD_RULE,
        "paired effect-threshold rule",
    )
    _exact(paired.get("paired_game_count"), PAIRED_GAME_COUNT, "paired game count")
    _exact(
        paired.get("pairs_per_standard_shard"), PAIRS_PER_STANDARD_SHARD, "pairs per standard shard"
    )
    _exact(paired.get("pair_selection_rule"), PAIR_SELECTION_RULE, "pair selection rule")
    _exact(paired.get("checkpoint_turn"), PAIRED_CHECKPOINT_TURN, "paired checkpoint")
    _exact(paired.get("mcnemar_test"), "EXACT_TWO_SIDED", "paired test")
    _exact(paired.get("confidence_interval_method"), PAIRED_CI_METHOD, "paired confidence interval")
    _exact(paired.get("confidence_level"), PAIRED_CI_CONFIDENCE, "paired confidence level")
    _exact(
        paired.get("bootstrap_resamples"), PAIRED_BOOTSTRAP_RESAMPLES, "paired bootstrap resamples"
    )
    _exact(
        paired.get("required_reporting_sentence"), REPORTING_SENTENCE, "paired reporting sentence"
    )


def load_phase_c_config(path: Path = DEFAULT_CONFIG) -> PhaseCConfiguration:
    payload = _load_object(path, "Phase C pilot configuration")
    _exact(payload.get("schema_version"), "phase-c-pilot-config-v2", "schema")
    authorization = _mapping(payload.get("authorization"), "authorization")
    pilot = _mapping(payload.get("pilot"), "pilot")
    policy = _mapping(payload.get("policy"), "policy")
    search = _mapping(payload.get("exploratory_search"), "exploratory_search")
    deck = _mapping(payload.get("deck"), "deck")
    paired = _mapping(payload.get("paired_analysis"), "paired_analysis")
    paired_analysis = _parse_paired_analysis_configuration(paired)
    _validate_scope(payload)

    _exact(authorization.get("confirmation_token"), CONFIRMATION_TOKEN, "confirmation token")
    _exact(pilot.get("standard_games"), STANDARD_GAMES, "standard pilot count")
    _exact(pilot.get("exploratory_games"), EXPLORATORY_GAMES, "exploratory pilot count")
    _exact(pilot.get("standard_shards"), STANDARD_SHARDS, "standard pilot shard count")
    _exact(pilot.get("exploratory_shards"), EXPLORATORY_SHARDS, "exploratory pilot shard count")
    environment_namespace = str(pilot.get("environment_seed_namespace", ""))
    search_namespace = str(pilot.get("exploratory_search_seed_namespace", ""))
    if not environment_namespace or not search_namespace:
        raise PhaseCControlError(
            "environment and exploratory search seed namespaces must be nonempty"
        )
    if environment_namespace == search_namespace:
        raise PhaseCControlError(
            "environment and exploratory search seed namespaces must be distinct"
        )

    policy_id = str(policy.get("standard_policy_config_id", ""))
    policy_hash = str(policy.get("standard_policy_config_hash", ""))
    evaluator_id = str(policy.get("evaluator_snapshot_id", ""))
    evaluator_hash = str(policy.get("evaluator_snapshot_sha256", ""))
    learning_hash = str(policy.get("learning_plan_sha256", ""))
    if not policy_id or not evaluator_id:
        raise PhaseCControlError("Phase C policy identity is incomplete")
    if not all(_is_sha256(value) for value in (policy_hash, evaluator_hash, learning_hash)):
        raise PhaseCControlError("Phase C policy digests are incomplete")
    _exact(policy.get("policy_mutation_allowed"), False, "policy mutation")
    _exact(
        policy.get("exploratory_continuation_policy_config_id"),
        policy_id,
        "exploratory continuation policy",
    )

    return PhaseCConfiguration(
        path=path,
        payload=payload,
        sha256=file_sha256(path),
        paired_analysis=paired_analysis,
        deck_exact_library_count=int(deck["exact_library_count"]),
        deck_physical_card_count=int(deck["physical_card_count"]),
        deck_commanders=tuple(str(value) for value in deck["commanders"]),
        deck_source=str(deck["source"]),
        confirmation_token=str(authorization["confirmation_token"]),
        execution_allowed=bool(authorization.get("execution_allowed")),
        authorization_status=str(authorization.get("status", "")),
        standard_games=int(pilot["standard_games"]),
        exploratory_games=int(pilot["exploratory_games"]),
        environment_seed_namespace=environment_namespace,
        exploratory_search_seed_namespace=search_namespace,
        policy_config_id=policy_id,
        policy_config_hash=policy_hash,
        evaluator_snapshot_id=evaluator_id,
        evaluator_snapshot_sha256=evaluator_hash,
        learning_plan_sha256=learning_hash,
        exploratory_production_decision_layer_depth=int(search["production_decision_layer_depth"]),
        standard_shards=int(pilot["standard_shards"]),
        exploratory_shards=int(pilot["exploratory_shards"]),
    )


def load_phase_c_approval(path: Path = DEFAULT_APPROVAL) -> PhaseCApproval:
    payload = _load_object(path, "Phase C pilot approval")
    _exact(payload.get("schema_version"), "phase-c-pilot-approval-v2", "schema")
    token_digest = str(payload.get("confirmation_token_sha256", ""))
    expected = hashlib.sha256(CONFIRMATION_TOKEN.encode()).hexdigest()
    if token_digest != expected:
        raise PhaseCControlError("approval uses a different confirmation token")
    counts = _mapping(payload.get("authorized_counts"), "authorized_counts")
    _exact(counts.get("standard"), STANDARD_GAMES, "approved standard count")
    _exact(counts.get("exploratory"), EXPLORATORY_GAMES, "approved exploratory count")
    shards = _mapping(payload.get("authorized_shards"), "authorized_shards")
    _exact(shards.get("standard"), STANDARD_SHARDS, "approved standard shard count")
    _exact(shards.get("exploratory"), EXPLORATORY_SHARDS, "approved exploratory shard count")
    _exact(
        payload.get("production_decision_layer_depth"),
        PILOT_PRODUCTION_DECISION_LAYER_DEPTH,
        "approved exploratory production depth",
    )

    def optional_text(key: str) -> str | None:
        value = payload.get(key)
        return str(value) if value is not None else None

    return PhaseCApproval(
        path=path,
        payload=payload,
        sha256=file_sha256(path),
        status=str(payload.get("status", "")),
        approved_by=optional_text("approved_by"),
        approved_at=optional_text("approved_at"),
        implementation_commit=optional_text("implementation_commit"),
        implementation_tree=optional_text("implementation_tree"),
        locked_pilot_config_sha256=optional_text("locked_pilot_config_sha256"),
        workflow_sha256=optional_text("workflow_sha256"),
        confirmation_token_sha256=token_digest,
        production_decision_layer_depth=int(payload["production_decision_layer_depth"]),
        standard_shards=int(shards["standard"]),
        exploratory_shards=int(shards["exploratory"]),
        approval_statement=optional_text("approval_statement"),
    )


def _derive_seeds(namespace: str, count: int) -> tuple[int, ...]:
    return tuple(
        int.from_bytes(hashlib.sha256(f"{namespace}:{index}".encode()).digest()[:8], "big")
        for index in range(1, count + 1)
    )


def build_pilot_seed_plan(config: PhaseCConfiguration) -> PilotSeedPlan:
    standard = _derive_seeds(config.environment_seed_namespace, config.standard_games)
    pairing = build_pairing_plan(
        standard,
        search_seed_namespace=config.exploratory_search_seed_namespace,
        standard_shards=config.standard_shards,
    )
    return PilotSeedPlan(
        standard=standard,
        exploratory=pairing.exploratory_environment_seeds,
        exploratory_search=pairing.exploratory_search_seeds,
        paired_standard_game_indexes=pairing.paired_standard_game_indexes,
        pair_ids=pairing.pair_ids,
        standard_sha256=hashlib.sha256(_canonical(standard)).hexdigest(),
        exploratory_sha256=pairing.exploratory_environment_sha256,
        exploratory_search_sha256=pairing.exploratory_search_sha256,
        pair_assignment_sha256=pairing.pair_assignment_sha256,
    )


def build_pilot_shard_assignment(
    config: PhaseCConfiguration,
    seeds: PilotSeedPlan,
    *,
    mode: str,
    shard_index: int,
) -> PilotShardAssignment:
    pair_by_standard_index = dict(
        zip(seeds.paired_standard_game_indexes, seeds.pair_ids, strict=True)
    )
    if mode == "STANDARD":
        values = seeds.standard
        shard_count = config.standard_shards
        if len(values) % shard_count:
            raise PhaseCControlError("pilot game count must divide evenly across frozen shards")
        if shard_index < 0 or shard_index >= shard_count:
            raise PhaseCControlError("pilot shard index is outside the frozen shard range")
        size = len(values) // shard_count
        start = shard_index * size
        selected = tuple(values[start : start + size])
        standard_indexes = tuple(range(start + 1, start + size + 1))
        return PilotShardAssignment(
            mode=mode,
            shard_index=shard_index,
            shard_count=shard_count,
            first_game_index=start + 1,
            last_game_index=start + size,
            seeds=selected,
            pair_ids=tuple(pair_by_standard_index.get(index) for index in standard_indexes),
            paired_standard_game_indexes=tuple(
                index if index in pair_by_standard_index else None for index in standard_indexes
            ),
            search_seeds=(None,) * size,
        )
    if mode == "EXPLORATORY":
        values = seeds.exploratory
        shard_count = config.exploratory_shards
        if len(values) % shard_count:
            raise PhaseCControlError("pilot game count must divide evenly across frozen shards")
        if shard_index < 0 or shard_index >= shard_count:
            raise PhaseCControlError("pilot shard index is outside the frozen shard range")
        size = len(values) // shard_count
        start = shard_index * size
        return PilotShardAssignment(
            mode=mode,
            shard_index=shard_index,
            shard_count=shard_count,
            first_game_index=start + 1,
            last_game_index=start + size,
            seeds=tuple(values[start : start + size]),
            pair_ids=tuple(seeds.pair_ids[start : start + size]),
            paired_standard_game_indexes=tuple(
                seeds.paired_standard_game_indexes[start : start + size]
            ),
            search_seeds=tuple(seeds.exploratory_search[start : start + size]),
        )
    raise PhaseCControlError("pilot shard mode must be STANDARD or EXPLORATORY")


def _combo_detector_smoke() -> Mapping[str, Any]:
    from mtg_cards.full_deck import load_full_deck_specs
    from mtg_kernel.factory import add_card, new_game
    from mtg_kernel.models import Zone
    from mtg_measure import bind_combo_access_tracker
    from mtg_policy import load_evaluator_config

    state, executor = new_game(("P0", "P1", "P2", "P3"), seed="phase-c-combo-readiness")
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    state.turn.number = 3
    state.turn.phase = "PRECOMBAT_MAIN"
    state.turn.step = "PRECOMBAT_MAIN"
    state.turn.priority_holder_id = "P0"
    state.players["P0"].mana_pool.update({"R": 4, "U": 3, "C": 8})
    for name in (
        "Dualcaster Mage",
        "Twinflame",
        "Electroduplicate",
        "Glint-Horn Buccaneer",
        "Curiosity",
        "Psychosis Crawler",
    ):
        add_card(executor, specs[name], Zone.HAND)
    for name in (
        "Malcolm, Keen-Eyed Navigator",
        "Lightning-Rig Crew",
        "Niv-Mizzet, the Firemind",
    ):
        obj = add_card(executor, specs[name], Zone.BATTLEFIELD)
        if obj.permanent_status is not None:
            obj.permanent_status["controller_since_turn"] = "1"
    add_card(executor, specs["Crab Umbra"], Zone.HAND)
    tracker = bind_combo_access_tracker(executor, "P0", load_evaluator_config().combo_packages)
    records = tracker.observe(executor)
    expected = set(load_evaluator_config().combo_packages)
    actual = {record.package for record in records}
    if actual != expected:
        raise PhaseCControlError(f"combo detector registry mismatch: {sorted(expected - actual)}")
    if any("UNIMPLEMENTED" in blocker for record in records for blocker in record.blockers):
        raise PhaseCControlError("combo detector still reports unimplemented package logic")
    return {
        "status": "PASS",
        "package_count": len(records),
        "packages": sorted(actual),
    }


def evaluate_phase_c_readiness() -> tuple[tuple[str, ...], dict[str, Mapping[str, Any]]]:
    """Derive readiness from bounded executable production checks, never a mutable label list."""
    from mtg_runs.phase_c_runner import (
        run_phase_c_combat_smoke,
        run_phase_c_exploratory_smoke,
        run_phase_c_paired_environment_smoke,
    )

    evidence: dict[str, Mapping[str, Any]] = {}
    blockers: list[str] = []

    def run(blocker: str, check: Callable[[], Mapping[str, Any]]) -> None:
        try:
            evidence[blocker] = dict(check())
        except Exception as exc:  # fail closed and expose the exact bounded check failure
            blockers.append(blocker)
            evidence[blocker] = {
                "status": "FAIL",
                "error_type": type(exc).__name__,
                "reason": str(exc),
            }

    def controlled_turn() -> Mapping[str, Any]:
        # Run the full policy-driven exact-deck smoke in a fresh process. This keeps
        # the readiness signal bound to real strategic choices and fresh replay while
        # avoiding retained game/replay state inside long pytest sessions.
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts/check_phase_c_turn10.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            diagnostic = (completed.stdout + completed.stderr).strip()
            raise PhaseCControlError(f"policy-driven Turn-10 smoke failed: {diagnostic}")
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise PhaseCControlError("policy-driven Turn-10 smoke returned malformed JSON") from exc
        if not isinstance(result, Mapping) or result.get("status") != "PASS":
            raise PhaseCControlError("policy-driven Turn-10 smoke did not report PASS")
        return dict(result)

    run("CONTROLLED_TURN_DRIVER_NOT_IMPLEMENTED", controlled_turn)
    run("COMBAT_ACTION_PATH_NOT_IMPLEMENTED", run_phase_c_combat_smoke)
    run("EXPLORATORY_PRODUCTION_EXPANSION_NOT_IMPLEMENTED", run_phase_c_exploratory_smoke)
    run("PAIRED_EXPLORATORY_DESIGN_NOT_IMPLEMENTED", run_phase_c_paired_environment_smoke)
    run("COMBO_ACCESS_DETECTORS_INCOMPLETE", _combo_detector_smoke)
    return tuple(blockers), evidence


def current_engine_blockers() -> tuple[str, ...]:
    blockers, _ = evaluate_phase_c_readiness()
    return blockers


def dry_run_phase_c(
    config_path: Path = DEFAULT_CONFIG,
    approval_path: Path = DEFAULT_APPROVAL,
    workflow_path: Path = DEFAULT_WORKFLOW,
) -> PhaseCDryRunReport:
    """Validate the locked control plane and bounded production smokes without pilot results."""
    config = load_phase_c_config(config_path)
    approval = load_phase_c_approval(approval_path)
    seeds = build_pilot_seed_plan(config)
    full_study = _mapping(config.payload.get("full_study"), "full_study")
    blockers, evidence = evaluate_phase_c_readiness()
    status = "READY_FOR_OWNER_REVIEW" if not blockers else "LOCKED_ENGINE_INCOMPLETE"
    return PhaseCDryRunReport(
        schema_version="phase-c-dry-run-v2",
        status=status,
        config_sha256=config.sha256,
        approval_record_sha256=approval.sha256,
        workflow_sha256=file_sha256(workflow_path),
        policy_config_id=config.policy_config_id,
        evaluator_snapshot_id=config.evaluator_snapshot_id,
        standard_game_count=config.standard_games,
        exploratory_game_count=config.exploratory_games,
        standard_seed_sha256=seeds.standard_sha256,
        exploratory_seed_sha256=seeds.exploratory_sha256,
        exploratory_search_seed_sha256=seeds.exploratory_search_sha256,
        pair_assignment_sha256=seeds.pair_assignment_sha256,
        paired_game_count=PAIRED_GAME_COUNT,
        execution_allowed=config.execution_allowed,
        authorization_status=config.authorization_status,
        readiness_blockers=blockers,
        readiness_evidence=evidence,
        exploratory_production_decision_layer_depth=config.exploratory_production_decision_layer_depth,
        game_results_created=0,
        full_study_execution_allowed=bool(full_study.get("execution_allowed")),
    )


def _validate_governance_only_activation(
    *,
    root: Path,
    implementation_commit: str,
    activation_commit: str,
    current_config: Mapping[str, Any],
    current_approval: Mapping[str, Any],
    config_path: Path,
    approval_path: Path,
) -> None:
    try:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", implementation_commit, activation_commit],
            cwd=root,
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise PhaseCControlError(
            "activation commit is not a descendant of the reviewed implementation"
        ) from exc
    changed = {
        value
        for value in _git(
            root, "diff", "--name-only", implementation_commit, activation_commit
        ).splitlines()
        if value
    }
    unexpected = changed - _ACTIVATION_ALLOWLIST
    if unexpected:
        raise PhaseCControlError(
            f"activation commit changes non-governance files: {sorted(unexpected)}"
        )

    locked_config = json.loads(_git_file(root, implementation_commit, config_path).decode("utf-8"))
    if not isinstance(locked_config, dict):
        raise PhaseCControlError("locked implementation config is malformed")
    locked_non_auth = {key: value for key, value in locked_config.items() if key != "authorization"}
    current_non_auth = {
        key: value for key, value in current_config.items() if key != "authorization"
    }
    if locked_non_auth != current_non_auth:
        raise PhaseCControlError(
            "activation changed the study configuration outside authorization fields"
        )
    locked_auth = _mapping(locked_config.get("authorization"), "locked authorization")
    current_auth = _mapping(current_config.get("authorization"), "current authorization")
    _exact(set(current_auth), set(locked_auth), "activation authorization field set")
    _exact(locked_auth.get("execution_allowed"), False, "implementation execution lock")
    _exact(locked_auth.get("status"), "LOCKED_PENDING_OWNER_APPROVAL", "implementation status")
    _exact(
        current_auth.get("confirmation_token"),
        locked_auth.get("confirmation_token"),
        "activation confirmation token",
    )
    _exact(current_auth.get("execution_allowed"), True, "activation execution flag")
    _exact(current_auth.get("status"), "AUTHORIZED", "activation status")
    _exact(
        current_auth.get("approved_by"),
        current_approval.get("approved_by"),
        "activation approved_by",
    )
    _exact(
        current_auth.get("approved_at"),
        current_approval.get("approved_at"),
        "activation approved_at",
    )

    pending_approval = json.loads(
        _git_file(root, implementation_commit, approval_path).decode("utf-8")
    )
    if not isinstance(pending_approval, dict):
        raise PhaseCControlError("implementation approval record is malformed")
    _exact(set(current_approval), set(pending_approval), "activation approval field set")
    _exact(
        pending_approval.get("status"), "PENDING_OWNER_APPROVAL", "implementation approval status"
    )
    immutable_approval_keys = {
        "authorized_counts",
        "authorized_shards",
        "confirmation_token_sha256",
        "production_decision_layer_depth",
        "schema_version",
    }
    for key in immutable_approval_keys:
        if pending_approval.get(key) != current_approval.get(key):
            raise PhaseCControlError(f"activation changed immutable approval field: {key}")


def validate_execution_authorization(
    *,
    confirmation: str,
    implementation_commit: str,
    activation_commit: str,
    expected_locked_config_sha256: str,
    expected_workflow_sha256: str,
    requested_standard_games: int = STANDARD_GAMES,
    requested_exploratory_games: int = EXPLORATORY_GAMES,
    config_path: Path = DEFAULT_CONFIG,
    approval_path: Path = DEFAULT_APPROVAL,
    workflow_path: Path = DEFAULT_WORKFLOW,
    root: Path = ROOT,
) -> tuple[PhaseCConfiguration, PhaseCApproval, PilotSeedPlan, PhaseCAuthorizationContext]:
    """Require a reviewed implementation plus governance-only owner activation."""
    if confirmation != CONFIRMATION_TOKEN:
        raise PhaseCControlError("Phase C confirmation token does not match")
    if requested_standard_games != STANDARD_GAMES:
        raise PhaseCControlError("Phase C requires exactly 500 standard games")
    if requested_exploratory_games != EXPLORATORY_GAMES:
        raise PhaseCControlError("Phase C requires exactly 200 exploratory games")
    if not _is_git_object_id(implementation_commit) or not _is_git_object_id(activation_commit):
        raise PhaseCControlError(
            "implementation and activation commits must be lowercase 40-character Git object IDs"
        )
    if not _is_sha256(expected_locked_config_sha256) or not _is_sha256(expected_workflow_sha256):
        raise PhaseCControlError("configuration and workflow bindings must be SHA-256 digests")
    if _git(root, "rev-parse", "HEAD") != activation_commit:
        raise PhaseCControlError("checked-out commit differs from the activation commit")

    implementation_tree = _git(root, "rev-parse", f"{implementation_commit}^{{tree}}")
    context = PhaseCAuthorizationContext(
        implementation_commit,
        implementation_tree,
        activation_commit,
        expected_locked_config_sha256,
        expected_workflow_sha256,
    )
    config = load_phase_c_config(config_path)
    approval = load_phase_c_approval(approval_path)
    seeds = build_pilot_seed_plan(config)
    locked_config_sha = _git_file_sha256(root, implementation_commit, config_path)
    if locked_config_sha != expected_locked_config_sha256:
        raise PhaseCControlError("reviewed locked configuration digest differs")
    implementation_workflow_sha = _git_file_sha256(root, implementation_commit, workflow_path)
    if implementation_workflow_sha != expected_workflow_sha256:
        raise PhaseCControlError("reviewed workflow digest differs")
    if file_sha256(workflow_path) != expected_workflow_sha256:
        raise PhaseCControlError("activation commit changed the reviewed workflow")

    _validate_governance_only_activation(
        root=root,
        implementation_commit=implementation_commit,
        activation_commit=activation_commit,
        current_config=config.payload,
        current_approval=approval.payload,
        config_path=config_path,
        approval_path=approval_path,
    )
    if not config.execution_allowed or config.authorization_status != "AUTHORIZED":
        raise PhaseCControlError("Phase C configuration remains locked")
    if approval.status != "APPROVED":
        raise PhaseCControlError("Phase C owner approval remains pending")
    if approval.approved_by != "Jeff Toney" or not approval.approved_at:
        raise PhaseCControlError(
            "Phase C approval must contain the exact owner identity and timestamp"
        )
    if not _is_rfc3339_utc(approval.approved_at):
        raise PhaseCControlError("Phase C approval timestamp must be RFC3339 UTC")
    if approval.implementation_commit != implementation_commit:
        raise PhaseCControlError("approval is bound to a different implementation commit")
    if approval.implementation_tree != implementation_tree:
        raise PhaseCControlError("approval is bound to a different implementation tree")
    if approval.locked_pilot_config_sha256 != locked_config_sha:
        raise PhaseCControlError("approval is bound to a different locked pilot config")
    if approval.workflow_sha256 != expected_workflow_sha256:
        raise PhaseCControlError("approval is bound to a different workflow")
    if not approval.approval_statement:
        raise PhaseCControlError("Phase C approval statement is missing")
    required_statement_terms = (
        implementation_commit,
        implementation_tree,
        locked_config_sha,
        expected_workflow_sha256,
        approval.confirmation_token_sha256,
        str(STANDARD_GAMES),
        str(EXPLORATORY_GAMES),
        str(PILOT_PRODUCTION_DECISION_LAYER_DEPTH),
        f"standard_shards={STANDARD_SHARDS}",
        f"exploratory_shards={EXPLORATORY_SHARDS}",
    )
    if not all(term in approval.approval_statement for term in required_statement_terms):
        raise PhaseCControlError(
            "Phase C approval statement must name implementation, tree, counts, depth, and digests"
        )
    blockers = current_engine_blockers()
    if blockers:
        raise PhaseCControlError(f"Phase C engine remains incomplete: {', '.join(blockers)}")
    return config, approval, seeds, context


def _require_durable_certification_gates(root: Path = ROOT) -> None:
    for script in (
        "scripts/check_phase_a_certification.py",
        "scripts/check_phase_b_certification.py",
    ):
        try:
            subprocess.check_output(
                [sys.executable, script], cwd=root, text=True, stderr=subprocess.STDOUT
            )
        except subprocess.CalledProcessError as exc:
            raise PhaseCControlError(
                f"durable certification gate failed before Phase C execution: {script}: "
                f"{exc.output.strip()}"
            ) from exc


def execute_phase_c_shard(
    *,
    confirmation: str,
    implementation_commit: str,
    activation_commit: str,
    expected_locked_config_sha256: str,
    expected_workflow_sha256: str,
    mode: str,
    shard_index: int,
    output_root: Path,
    config_path: Path = DEFAULT_CONFIG,
    approval_path: Path = DEFAULT_APPROVAL,
    workflow_path: Path = DEFAULT_WORKFLOW,
    root: Path = ROOT,
) -> Mapping[str, Any]:
    """Execute exactly one frozen, owner-authorized Phase C pilot shard."""
    config, approval, seeds, context = validate_execution_authorization(
        confirmation=confirmation,
        implementation_commit=implementation_commit,
        activation_commit=activation_commit,
        expected_locked_config_sha256=expected_locked_config_sha256,
        expected_workflow_sha256=expected_workflow_sha256,
        config_path=config_path,
        approval_path=approval_path,
        workflow_path=workflow_path,
        root=root,
    )
    _require_durable_certification_gates(root)
    assignment = build_pilot_shard_assignment(config, seeds, mode=mode, shard_index=shard_index)
    if output_root.exists() and not output_root.is_dir():
        raise PhaseCControlError("Phase C output root exists but is not a directory")

    from dataclasses import asdict, replace

    from mtg_measure import aggregate_measurements
    from mtg_runs.phase_c_artifacts import (
        build_shard_manifest,
        make_game_artifact,
        write_phase_c_shard,
    )
    from mtg_runs.phase_c_runner import run_phase_c_game_execution

    technical_records = []
    game_records = []
    replay_records = []
    measurements = []
    for offset, seed in enumerate(assignment.seeds):
        global_index = assignment.first_game_index + offset
        execution = run_phase_c_game_execution(
            seed=seed,
            mode=mode,
            search_seed=assignment.search_seeds[offset],
            pair_id=assignment.pair_ids[offset],
            paired_standard_game_index=assignment.paired_standard_game_indexes[offset],
            policy_config_id=config.policy_config_id,
            through_turn=10,
            validate_fresh_replay=True,
            policy_actions=True,
        )
        measurement = replace(execution.measurement, game_index=global_index)
        technical = execution.technical_game.to_dict()
        replay = dict(execution.replay_transcript)
        technical_records.append(technical)
        game_records.append(
            make_game_artifact(
                mode=mode,
                game_index=global_index,
                seed=seed,
                technical_game=technical,
                replay=replay,
                measurement=measurement,
            )
        )
        replay_records.append(replay)
        measurements.append(measurement)
    summary = asdict(aggregate_measurements(measurements))
    manifest = build_shard_manifest(
        mode=mode,
        shard_index=assignment.shard_index,
        shard_count=assignment.shard_count,
        first_game_index=assignment.first_game_index,
        seeds=assignment.seeds,
        pair_ids=assignment.pair_ids,
        paired_standard_game_indexes=assignment.paired_standard_game_indexes,
        search_seeds=assignment.search_seeds,
        implementation_commit=context.implementation_commit,
        implementation_tree=context.implementation_tree,
        activation_commit=context.activation_commit,
        locked_config_sha256=context.locked_config_sha256,
        workflow_sha256=context.workflow_sha256,
        approval_record_sha256=approval.sha256,
        policy_config_id=config.policy_config_id,
        policy_config_sha256=config.policy_config_hash,
        evaluator_snapshot_id=config.evaluator_snapshot_id,
        evaluator_snapshot_sha256=config.evaluator_snapshot_sha256,
        learning_plan_sha256=config.learning_plan_sha256,
        technical_games=technical_records,
        game_records=game_records,
        replays=replay_records,
        measurements=measurements,
        summary=summary,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    shard_dir = write_phase_c_shard(
        output_root,
        manifest,
        technical_records,
        game_records,
        replay_records,
        measurements,
        summary,
    )
    return {
        "status": "PASS",
        "mode": mode,
        "shard_index": shard_index,
        "game_count": len(assignment.seeds),
        "first_game_index": assignment.first_game_index,
        "last_game_index": assignment.last_game_index,
        "shard_sha256": manifest.shard_sha256,
        "output": str(shard_dir),
    }


def aggregate_phase_c_pilot_artifacts(
    *,
    confirmation: str,
    implementation_commit: str,
    activation_commit: str,
    expected_locked_config_sha256: str,
    expected_workflow_sha256: str,
    shard_root: Path,
    output_root: Path,
    config_path: Path = DEFAULT_CONFIG,
    approval_path: Path = DEFAULT_APPROVAL,
    workflow_path: Path = DEFAULT_WORKFLOW,
    root: Path = ROOT,
) -> Mapping[str, Any]:
    """Validate all 500/200 shard artifacts and write one immutable aggregate."""
    config, _approval, seeds, _context = validate_execution_authorization(
        confirmation=confirmation,
        implementation_commit=implementation_commit,
        activation_commit=activation_commit,
        expected_locked_config_sha256=expected_locked_config_sha256,
        expected_workflow_sha256=expected_workflow_sha256,
        config_path=config_path,
        approval_path=approval_path,
        workflow_path=workflow_path,
        root=root,
    )
    _require_durable_certification_gates(root)
    from mtg_runs.phase_c_artifacts import validate_phase_c_aggregate, write_phase_c_aggregate

    shard_dirs = sorted(
        path
        for path in shard_root.rglob("*")
        if path.is_dir() and (path / "manifest.json").is_file()
    )
    manifest, standard_summary, exploratory_summary, paired_analysis = validate_phase_c_aggregate(
        shard_dirs,
        expected_standard_seeds=seeds.standard,
        expected_exploratory_seeds=seeds.exploratory,
        expected_exploratory_search_seeds=seeds.exploratory_search,
        expected_pair_ids=seeds.pair_ids,
        expected_paired_standard_game_indexes=seeds.paired_standard_game_indexes,
        expected_standard_shards=config.standard_shards,
        expected_exploratory_shards=config.exploratory_shards,
        analysis_config=config.paired_analysis,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    aggregate_dir = write_phase_c_aggregate(
        output_root, manifest, standard_summary, exploratory_summary, paired_analysis
    )
    return {
        "status": "PASS",
        "standard_game_count": manifest.standard_game_count,
        "exploratory_game_count": manifest.exploratory_game_count,
        "aggregation_sha256": manifest.aggregation_sha256,
        "paired_turn8_analysis": dict(paired_analysis),
        "output": str(aggregate_dir),
    }


def execute_phase_c_pilot(**arguments: Any) -> Mapping[str, Any]:
    """Compatibility alias: Phase C execution is always one exact frozen shard."""
    return execute_phase_c_shard(**arguments)


__all__ = [
    "CONFIRMATION_TOKEN",
    "DEFAULT_APPROVAL",
    "DEFAULT_CONFIG",
    "DEFAULT_WORKFLOW",
    "EXPLORATORY_GAMES",
    "EXPLORATORY_SHARDS",
    "PILOT_PRODUCTION_DECISION_LAYER_DEPTH",
    "STANDARD_SHARDS",
    "PhaseCApproval",
    "PhaseCAuthorizationContext",
    "PhaseCConfiguration",
    "PhaseCControlError",
    "PhaseCDryRunReport",
    "PilotSeedPlan",
    "PilotShardAssignment",
    "STANDARD_GAMES",
    "aggregate_phase_c_pilot_artifacts",
    "build_pilot_seed_plan",
    "build_pilot_shard_assignment",
    "current_engine_blockers",
    "dry_run_phase_c",
    "evaluate_phase_c_readiness",
    "execute_phase_c_pilot",
    "execute_phase_c_shard",
    "file_sha256",
    "load_phase_c_approval",
    "load_phase_c_config",
    "validate_execution_authorization",
]
