"""Fail-closed Phase C pilot configuration and authorization controls."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json"
DEFAULT_APPROVAL = ROOT / "docs/spec/phase-c/PHASE_C_PILOT_APPROVAL.json"
DEFAULT_WORKFLOW = ROOT / ".github/workflows/phase-c-pilot.yml"
CONFIRMATION_TOKEN = "AUTHORIZE_PHASE_C_500_STANDARD_200_EXPLORATORY"
STANDARD_GAMES = 500
EXPLORATORY_GAMES = 200

CURRENT_ENGINE_BLOCKERS: tuple[str, ...] = ()


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


@dataclass(frozen=True)
class PhaseCGameRecord:
    schema_version: str
    mode: str
    game_index: int
    seed: int
    controlled_turns_completed: int
    mulligan_candidate_sizes: tuple[int, ...]
    kept_hand_refilled_to: int
    turn_one_draw_recorded: bool
    commands_recorded: tuple[str, ...]
    terminal_status: str
    combo_checkpoint_access: Mapping[str, Mapping[int, bool]]
    first_legal_attempt_turn: int | None
    actual_first_attempt_turn: int | None
    exploratory_production_decision_layers: int
    replay_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != "phase-c-technical-game-record-v1":
            raise PhaseCControlError("unsupported Phase C game-record schema")
        if self.mode not in {"STANDARD", "EXPLORATORY"}:
            raise PhaseCControlError("Phase C game record uses an invalid mode")
        if self.controlled_turns_completed != 10 or not self.turn_one_draw_recorded:
            raise PhaseCControlError("Phase C technical fixture must complete controlled Turn 10")
        if self.mulligan_candidate_sizes != (7, 7, 6, 5, 4):
            raise PhaseCControlError("Phase C technical fixture must use league mulligan sizes")
        if self.kept_hand_refilled_to != 7:
            raise PhaseCControlError("Phase C technical fixture must refill kept hands to seven")
        if self.mode == "STANDARD" and self.exploratory_production_decision_layers != 0:
            raise PhaseCControlError("standard records cannot report exploratory layers")
        if self.mode == "EXPLORATORY" and self.exploratory_production_decision_layers != 1:
            raise PhaseCControlError("exploratory records must report the frozen one-layer depth")
        if not self.commands_recorded or len(self.replay_sha256) != 64:
            raise PhaseCControlError("Phase C technical fixture replay evidence is incomplete")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PhaseCShardManifest:
    schema_version: str
    mode: str
    shard_index: int
    first_game_index: int
    last_game_index: int
    seed_sha256: str
    record_count: int
    records_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != "phase-c-technical-shard-manifest-v1":
            raise PhaseCControlError("unsupported Phase C shard schema")
        if self.mode not in {"STANDARD", "EXPLORATORY"}:
            raise PhaseCControlError("Phase C shard uses an invalid mode")
        if self.first_game_index < 1 or self.last_game_index < self.first_game_index:
            raise PhaseCControlError("Phase C shard assignment is invalid")
        expected = self.last_game_index - self.first_game_index + 1
        if self.record_count != expected:
            raise PhaseCControlError("Phase C shard record count does not match assignment")
        if not _is_sha256(self.seed_sha256) or not _is_sha256(self.records_sha256):
            raise PhaseCControlError("Phase C shard digests must be SHA-256 values")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PhaseCTechnicalFixture:
    schema_version: str
    standard_shard: PhaseCShardManifest
    exploratory_shard: PhaseCShardManifest
    aggregate_sha256: str
    game_results_created: int

    def __post_init__(self) -> None:
        if self.schema_version != "phase-c-technical-fixture-v1":
            raise PhaseCControlError("unsupported Phase C fixture schema")
        if self.standard_shard.mode != "STANDARD" or self.exploratory_shard.mode != "EXPLORATORY":
            raise PhaseCControlError("Phase C fixture must keep modes separate")
        if not _is_sha256(self.aggregate_sha256) or self.game_results_created != 0:
            raise PhaseCControlError(
                "Phase C fixture must be digest-bound and create no pilot results"
            )


def _fixture_record(mode: str, game_index: int, seed: int, depth: int) -> PhaseCGameRecord:
    commands = tuple(
        ["MULLIGAN_LEAGUE_7_7_6_5_4", "DRAW_TURN_1"]
        + [f"END_CONTROLLED_TURN_{turn}" for turn in range(1, 11)]
    )
    replay_sha = hashlib.sha256(
        _canonical({"mode": mode, "game_index": game_index, "seed": seed, "commands": commands})
    ).hexdigest()
    return PhaseCGameRecord(
        schema_version="phase-c-technical-game-record-v1",
        mode=mode,
        game_index=game_index,
        seed=seed,
        controlled_turns_completed=10,
        mulligan_candidate_sizes=(7, 7, 6, 5, 4),
        kept_hand_refilled_to=7,
        turn_one_draw_recorded=True,
        commands_recorded=commands,
        terminal_status="CONTROLLED_TURN_10_COMPLETE",
        combo_checkpoint_access={"dualcaster_twinflame": {5: False, 6: False, 8: False, 10: False}},
        first_legal_attempt_turn=None,
        actual_first_attempt_turn=None,
        exploratory_production_decision_layers=depth,
        replay_sha256=replay_sha,
    )


def _build_shard(
    mode: str, shard_index: int, seeds: Sequence[int], *, depth: int
) -> PhaseCShardManifest:
    records = tuple(
        _fixture_record(mode, index, seed, depth) for index, seed in enumerate(seeds, start=1)
    )
    return PhaseCShardManifest(
        schema_version="phase-c-technical-shard-manifest-v1",
        mode=mode,
        shard_index=shard_index,
        first_game_index=1,
        last_game_index=len(records),
        seed_sha256=hashlib.sha256(_canonical(tuple(seeds))).hexdigest(),
        record_count=len(records),
        records_sha256=hashlib.sha256(
            _canonical([record.to_dict() for record in records])
        ).hexdigest(),
    )


def build_phase_c_technical_fixture(
    config: PhaseCConfiguration, seeds: PilotSeedPlan
) -> PhaseCTechnicalFixture:
    standard = _build_shard("STANDARD", 0, seeds.standard[:2], depth=0)
    exploratory = _build_shard(
        "EXPLORATORY", 0, seeds.exploratory[:2], depth=config.exploratory_production_decision_layers
    )
    aggregate = hashlib.sha256(
        _canonical({"standard": standard.to_dict(), "exploratory": exploratory.to_dict()})
    ).hexdigest()
    return PhaseCTechnicalFixture(
        "phase-c-technical-fixture-v1", standard, exploratory, aggregate, 0
    )


def validate_phase_c_aggregate(shards: Iterable[PhaseCShardManifest]) -> dict[str, Any]:
    by_mode: dict[str, list[PhaseCShardManifest]] = {"STANDARD": [], "EXPLORATORY": []}
    for shard in shards:
        by_mode[shard.mode].append(shard)
    if not by_mode["STANDARD"] or not by_mode["EXPLORATORY"]:
        raise PhaseCControlError(
            "Phase C aggregation requires separate standard and exploratory shards"
        )
    summaries = {}
    for mode, mode_shards in by_mode.items():
        expected = 1
        seen: set[int] = set()
        for shard in sorted(mode_shards, key=lambda item: item.first_game_index):
            if shard.shard_index in seen or shard.first_game_index != expected:
                raise PhaseCControlError(
                    "Phase C aggregation rejects duplicate shards, gaps, or overlaps"
                )
            seen.add(shard.shard_index)
            expected = shard.last_game_index + 1
        summaries[mode.lower()] = {"shard_count": len(mode_shards), "game_count": expected - 1}
    body = {
        "schema_version": "phase-c-technical-aggregate-v1",
        "status": "PASS",
        "summaries": summaries,
    }
    return body | {"aggregation_sha256": hashlib.sha256(_canonical(body)).hexdigest()}


@dataclass(frozen=True)
class PilotSeedPlan:
    standard: tuple[int, ...]
    exploratory: tuple[int, ...]
    standard_sha256: str
    exploratory_sha256: str

    def __post_init__(self) -> None:
        if len(self.standard) != STANDARD_GAMES:
            raise PhaseCControlError("standard seed count is not exactly 500")
        if len(self.exploratory) != EXPLORATORY_GAMES:
            raise PhaseCControlError("exploratory seed count is not exactly 200")
        if len(set(self.standard)) != len(self.standard):
            raise PhaseCControlError("standard pilot seed plan contains duplicates")
        if len(set(self.exploratory)) != len(self.exploratory):
            raise PhaseCControlError("exploratory pilot seed plan contains duplicates")
        if set(self.standard).intersection(self.exploratory):
            raise PhaseCControlError("standard and exploratory pilot seed plans overlap")


@dataclass(frozen=True)
class PhaseCConfiguration:
    path: Path
    payload: Mapping[str, Any]
    sha256: str
    confirmation_token: str
    execution_allowed: bool
    authorization_status: str
    standard_games: int
    exploratory_games: int
    standard_seed_namespace: str
    exploratory_seed_namespace: str
    policy_config_id: str
    policy_config_hash: str
    evaluator_snapshot_id: str
    evaluator_snapshot_sha256: str
    learning_plan_sha256: str
    exploratory_production_decision_layers: int


@dataclass(frozen=True)
class PhaseCApproval:
    path: Path
    payload: Mapping[str, Any]
    sha256: str
    status: str
    approved_by: str | None
    approved_at: str | None
    authorized_commit: str | None
    pilot_config_sha256: str | None
    workflow_sha256: str | None
    confirmation_token_sha256: str
    approval_statement: str | None


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
    execution_allowed: bool
    authorization_status: str
    readiness_blockers: tuple[str, ...]
    game_results_created: int
    full_study_execution_allowed: bool
    exploratory_production_decision_layers: int
    technical_fixture_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _validate_scope(payload: Mapping[str, Any]) -> None:
    full_study = _mapping(payload.get("full_study"), "full_study")
    search = _mapping(payload.get("exploratory_search"), "exploratory_search")
    model = _mapping(payload.get("game_model"), "game_model")
    measurement = _mapping(payload.get("measurement"), "measurement")
    mulligan = _mapping(payload.get("mulligan"), "mulligan")
    prerequisites = _mapping(payload.get("prerequisites"), "prerequisites")

    _exact(full_study.get("execution_allowed"), False, "full-study flag")
    _exact(full_study.get("standard_games"), 20_000, "full-study count")
    _exact(full_study.get("exploratory_games"), 5_000, "full-study count")
    _exact(search.get("future_information_allowed"), False, "future information")
    _exact(
        search.get("post_result_optimization_allowed"),
        False,
        "post-result optimization",
    )
    _exact(search.get("bounded"), True, "bounded search")
    _exact(search.get("production_decision_layers"), 1, "exploratory production depth")
    _exact(search.get("rules_validation_required"), True, "search validation")
    _exact(search.get("reported_separately"), True, "separate reporting")

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
    _exact(
        mulligan.get("rejected_hands_returned_and_shuffled"),
        True,
        "mulligan shuffle",
    )

    _exact(prerequisites.get("clean_engine_only"), True, "clean engine")
    _exact(prerequisites.get("legacy_import_allowed"), False, "legacy import")
    _exact(prerequisites.get("phase_a_verifier_required"), "PASS", "Phase A")
    _exact(prerequisites.get("phase_b_verifier_required"), "PASS", "Phase B")
    _exact(
        prerequisites.get("phase_b_certification_required"),
        "PASS",
        "Phase B certification",
    )
    _exact(
        prerequisites.get("post_merge_main_ci_required"),
        "PASS",
        "post-merge main CI",
    )


def load_phase_c_config(path: Path = DEFAULT_CONFIG) -> PhaseCConfiguration:
    payload = _load_object(path, "Phase C pilot configuration")
    _exact(payload.get("schema_version"), "phase-c-pilot-config-v1", "schema")
    authorization = _mapping(payload.get("authorization"), "authorization")
    pilot = _mapping(payload.get("pilot"), "pilot")
    policy = _mapping(payload.get("policy"), "policy")
    search = _mapping(payload.get("exploratory_search"), "exploratory_search")
    _validate_scope(payload)

    _exact(
        authorization.get("confirmation_token"),
        CONFIRMATION_TOKEN,
        "confirmation token",
    )
    _exact(pilot.get("standard_games"), STANDARD_GAMES, "standard pilot count")
    _exact(
        pilot.get("exploratory_games"),
        EXPLORATORY_GAMES,
        "exploratory pilot count",
    )
    standard_namespace = str(pilot.get("standard_seed_namespace", ""))
    exploratory_namespace = str(pilot.get("exploratory_seed_namespace", ""))
    if not standard_namespace or not exploratory_namespace:
        raise PhaseCControlError("pilot seed namespaces must be nonempty")
    if standard_namespace == exploratory_namespace:
        raise PhaseCControlError("pilot seed namespaces must be distinct")

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
        confirmation_token=str(authorization["confirmation_token"]),
        execution_allowed=bool(authorization.get("execution_allowed")),
        authorization_status=str(authorization.get("status", "")),
        standard_games=int(pilot["standard_games"]),
        exploratory_games=int(pilot["exploratory_games"]),
        standard_seed_namespace=standard_namespace,
        exploratory_seed_namespace=exploratory_namespace,
        policy_config_id=policy_id,
        policy_config_hash=policy_hash,
        evaluator_snapshot_id=evaluator_id,
        evaluator_snapshot_sha256=evaluator_hash,
        learning_plan_sha256=learning_hash,
        exploratory_production_decision_layers=int(search.get("production_decision_layers", 0)),
    )


def load_phase_c_approval(path: Path = DEFAULT_APPROVAL) -> PhaseCApproval:
    payload = _load_object(path, "Phase C pilot approval")
    _exact(payload.get("schema_version"), "phase-c-pilot-approval-v1", "schema")
    token_digest = str(payload.get("confirmation_token_sha256", ""))
    expected = hashlib.sha256(CONFIRMATION_TOKEN.encode()).hexdigest()
    if token_digest != expected:
        raise PhaseCControlError("approval uses a different confirmation token")
    counts = _mapping(payload.get("authorized_counts"), "authorized_counts")
    _exact(counts.get("standard"), STANDARD_GAMES, "approved standard count")
    _exact(
        counts.get("exploratory"),
        EXPLORATORY_GAMES,
        "approved exploratory count",
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
        authorized_commit=optional_text("authorized_commit"),
        pilot_config_sha256=optional_text("pilot_config_sha256"),
        workflow_sha256=optional_text("workflow_sha256"),
        confirmation_token_sha256=token_digest,
        approval_statement=optional_text("approval_statement"),
    )


def _derive_seeds(namespace: str, count: int) -> tuple[int, ...]:
    return tuple(
        int.from_bytes(
            hashlib.sha256(f"{namespace}:{index}".encode()).digest()[:8],
            "big",
        )
        for index in range(1, count + 1)
    )


def build_pilot_seed_plan(config: PhaseCConfiguration) -> PilotSeedPlan:
    standard = _derive_seeds(
        config.standard_seed_namespace,
        config.standard_games,
    )
    exploratory = _derive_seeds(
        config.exploratory_seed_namespace,
        config.exploratory_games,
    )
    return PilotSeedPlan(
        standard=standard,
        exploratory=exploratory,
        standard_sha256=hashlib.sha256(_canonical(standard)).hexdigest(),
        exploratory_sha256=hashlib.sha256(_canonical(exploratory)).hexdigest(),
    )


def dry_run_phase_c(
    config_path: Path = DEFAULT_CONFIG,
    approval_path: Path = DEFAULT_APPROVAL,
    workflow_path: Path = DEFAULT_WORKFLOW,
) -> PhaseCDryRunReport:
    """Validate the locked control plane without creating a game result."""

    config = load_phase_c_config(config_path)
    approval = load_phase_c_approval(approval_path)
    seeds = build_pilot_seed_plan(config)
    full_study = _mapping(config.payload.get("full_study"), "full_study")
    fixture = build_phase_c_technical_fixture(config, seeds)
    status = "READY_FOR_OWNER_REVIEW" if not CURRENT_ENGINE_BLOCKERS else "LOCKED_ENGINE_INCOMPLETE"
    return PhaseCDryRunReport(
        schema_version="phase-c-dry-run-v1",
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
        execution_allowed=config.execution_allowed,
        authorization_status=config.authorization_status,
        readiness_blockers=CURRENT_ENGINE_BLOCKERS,
        game_results_created=0,
        full_study_execution_allowed=bool(full_study.get("execution_allowed")),
        exploratory_production_decision_layers=config.exploratory_production_decision_layers,
        technical_fixture_digest=fixture.aggregate_sha256,
    )


def _git_head(root: Path = ROOT) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
    ).strip()


def validate_execution_authorization(
    *,
    confirmation: str,
    authorized_commit: str,
    expected_config_sha256: str,
    expected_workflow_sha256: str,
    requested_standard_games: int = STANDARD_GAMES,
    requested_exploratory_games: int = EXPLORATORY_GAMES,
    config_path: Path = DEFAULT_CONFIG,
    approval_path: Path = DEFAULT_APPROVAL,
    workflow_path: Path = DEFAULT_WORKFLOW,
    root: Path = ROOT,
) -> tuple[PhaseCConfiguration, PhaseCApproval, PilotSeedPlan]:
    """Require exact approval before any output path is created."""

    config = load_phase_c_config(config_path)
    approval = load_phase_c_approval(approval_path)
    seeds = build_pilot_seed_plan(config)
    if confirmation != CONFIRMATION_TOKEN:
        raise PhaseCControlError("Phase C confirmation token does not match")
    if requested_standard_games != STANDARD_GAMES:
        raise PhaseCControlError("Phase C requires exactly 500 standard games")
    if requested_exploratory_games != EXPLORATORY_GAMES:
        raise PhaseCControlError("Phase C requires exactly 200 exploratory games")
    if not _is_git_object_id(authorized_commit):
        raise PhaseCControlError("authorized commit must be a full lowercase Git object ID")
    if not _is_sha256(expected_config_sha256) or not _is_sha256(expected_workflow_sha256):
        raise PhaseCControlError("configuration and workflow bindings must be SHA-256 digests")
    if config.sha256 != expected_config_sha256:
        raise PhaseCControlError("Phase C configuration digest differs")
    workflow_sha = file_sha256(workflow_path)
    if workflow_sha != expected_workflow_sha256:
        raise PhaseCControlError("Phase C workflow digest differs")
    if _git_head(root) != authorized_commit:
        raise PhaseCControlError("checked-out commit differs from authorization")
    if not config.execution_allowed:
        raise PhaseCControlError("Phase C configuration remains locked")
    if config.authorization_status != "AUTHORIZED":
        raise PhaseCControlError("Phase C configuration is not authorized")
    if approval.status != "APPROVED":
        raise PhaseCControlError("Phase C owner approval remains pending")
    if not approval.approved_by or not approval.approved_at:
        raise PhaseCControlError("Phase C owner approval metadata is incomplete")
    if not approval.approval_statement:
        raise PhaseCControlError("Phase C approval statement is missing")
    if approval.authorized_commit != authorized_commit:
        raise PhaseCControlError("approval is bound to a different commit")
    if approval.pilot_config_sha256 != config.sha256:
        raise PhaseCControlError("approval is bound to a different config")
    if approval.workflow_sha256 != workflow_sha:
        raise PhaseCControlError("approval is bound to a different workflow")
    if CURRENT_ENGINE_BLOCKERS:
        blockers = ", ".join(CURRENT_ENGINE_BLOCKERS)
        raise PhaseCControlError(f"Phase C engine remains incomplete: {blockers}")
    return config, approval, seeds


def execute_phase_c_pilot(**arguments: Any) -> None:
    """Fail before mutation until the production game driver is complete."""

    validate_execution_authorization(**arguments)
    raise PhaseCControlError("Phase C game execution adapter is not installed")


__all__ = [
    "CONFIRMATION_TOKEN",
    "CURRENT_ENGINE_BLOCKERS",
    "DEFAULT_APPROVAL",
    "DEFAULT_CONFIG",
    "DEFAULT_WORKFLOW",
    "EXPLORATORY_GAMES",
    "PhaseCApproval",
    "PhaseCConfiguration",
    "PhaseCControlError",
    "PhaseCDryRunReport",
    "PhaseCGameRecord",
    "PhaseCShardManifest",
    "PhaseCTechnicalFixture",
    "PilotSeedPlan",
    "STANDARD_GAMES",
    "build_phase_c_technical_fixture",
    "build_pilot_seed_plan",
    "dry_run_phase_c",
    "execute_phase_c_pilot",
    "file_sha256",
    "load_phase_c_approval",
    "load_phase_c_config",
    "validate_execution_authorization",
    "validate_phase_c_aggregate",
]
