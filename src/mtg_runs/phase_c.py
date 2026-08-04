"""Fail-closed Phase C pilot configuration, seed, approval, and execution controls."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
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

# These are engineering readiness blockers, not owner-decision placeholders.  The
# control plane exposes them so authorization can never hide an incomplete game path.
CURRENT_ENGINE_BLOCKERS = (
    "CONTROLLED_TURN_DRIVER_NOT_IMPLEMENTED",
    "COMBAT_ACTION_PATH_NOT_IMPLEMENTED",
    "EXPLORATORY_PRODUCTION_EXPANSION_NOT_IMPLEMENTED",
    "COMBO_ACCESS_DETECTORS_INCOMPLETE",
)


class PhaseCControlError(ValueError):
    """Raised whenever Phase C configuration or authorization fails closed."""


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


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PhaseCControlError(f"{label} must be an object")
    return value


def _require_exact(value: object, expected: object, label: str) -> None:
    if value != expected:
        raise PhaseCControlError(f"{label} must be {expected!r}, received {value!r}")


@dataclass(frozen=True)
class PilotSeedPlan:
    standard: tuple[int, ...]
    exploratory: tuple[int, ...]
    standard_sha256: str
    exploratory_sha256: str

    def __post_init__(self) -> None:
        if len(self.standard) != STANDARD_GAMES or len(self.exploratory) != EXPLORATORY_GAMES:
            raise PhaseCControlError("Phase C seed plan does not contain exactly 500/200 seeds")
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_phase_c_config(path: Path = DEFAULT_CONFIG) -> PhaseCConfiguration:
    payload = _load_object(path, "Phase C pilot configuration")
    _require_exact(payload.get("schema_version"), "phase-c-pilot-config-v1", "schema_version")

    authorization = _require_mapping(payload.get("authorization"), "authorization")
    pilot = _require_mapping(payload.get("pilot"), "pilot")
    full_study = _require_mapping(payload.get("full_study"), "full_study")
    search = _require_mapping(payload.get("exploratory_search"), "exploratory_search")
    model = _require_mapping(payload.get("game_model"), "game_model")
    measurement = _require_mapping(payload.get("measurement"), "measurement")
    mulligan = _require_mapping(payload.get("mulligan"), "mulligan")
    prerequisites = _require_mapping(payload.get("prerequisites"), "prerequisites")
    policy = _require_mapping(payload.get("policy"), "policy")

    _require_exact(
        authorization.get("confirmation_token"), CONFIRMATION_TOKEN, "confirmation token"
    )
    _require_exact(pilot.get("standard_games"), STANDARD_GAMES, "standard pilot count")
    _require_exact(
        pilot.get("exploratory_games"), EXPLORATORY_GAMES, "exploratory pilot count"
    )
    standard_namespace = str(pilot.get("standard_seed_namespace", ""))
    exploratory_namespace = str(pilot.get("exploratory_seed_namespace", ""))
    if not standard_namespace or not exploratory_namespace or standard_namespace == exploratory_namespace:
        raise PhaseCControlError("pilot seed namespaces must be nonempty and distinct")

    _require_exact(full_study.get("execution_allowed"), False, "full-study execution flag")
    _require_exact(full_study.get("standard_games"), 20_000, "full-study standard count")
    _require_exact(full_study.get("exploratory_games"), 5_000, "full-study exploratory count")
    _require_exact(search.get("future_information_allowed"), False, "future information flag")
    _require_exact(
        search.get("post_result_optimization_allowed"), False, "post-result optimization flag"
    )
    _require_exact(search.get("bounded"), True, "bounded exploratory-search flag")
    _require_exact(search.get("rules_validation_required"), True, "search rules-validation flag")
    _require_exact(search.get("reported_separately"), True, "separate exploratory reporting")

    _require_exact(model.get("players"), 4, "player count")
    _require_exact(model.get("opponents"), 3, "opponent count")
    _require_exact(model.get("end_after_controlled_turn"), 10, "controlled turn horizon")
    _require_exact(model.get("controlled_player_draws_on_turn_one"), True, "Turn 1 draw")
    _require_exact(model.get("opponent_interaction_modeled"), False, "opponent interaction")
    _require_exact(model.get("blocking_modeled"), False, "blocking model")
    _require_exact(model.get("opponent_wins_modeled"), False, "opponent win model")
    _require_exact(
        model.get("breeches_unknown_cards_added_as_deterministic_resources"),
        False,
        "Breeches deterministic-resource boundary",
    )

    _require_exact(measurement.get("primary_checkpoint"), 8, "primary checkpoint")
    _require_exact(measurement.get("additional_checkpoints"), [5, 6, 10], "checkpoints")
    _require_exact(
        measurement.get("objective"),
        "MAXIMIZE_LEGAL_DETERMINISTIC_TABLE_WIN_ACCESS",
        "measurement objective",
    )
    _require_exact(mulligan.get("candidate_hand_sizes"), [7, 7, 6, 5, 4], "mulligan sizes")
    _require_exact(mulligan.get("refill_kept_hand_to"), 7, "mulligan refill")
    _require_exact(mulligan.get("stop_below_four"), True, "mulligan floor")
    _require_exact(
        mulligan.get("rejected_hands_returned_and_shuffled"), True, "mulligan shuffle"
    )

    _require_exact(prerequisites.get("clean_engine_only"), True, "clean-engine prerequisite")
    _require_exact(prerequisites.get("legacy_import_allowed"), False, "legacy import prerequisite")
    _require_exact(prerequisites.get("phase_a_verifier_required"), "PASS", "Phase A gate")
    _require_exact(prerequisites.get("phase_b_verifier_required"), "PASS", "Phase B gate")
    _require_exact(
        prerequisites.get("phase_b_certification_required"), "PASS", "Phase B certification"
    )
    _require_exact(prerequisites.get("post_merge_main_ci_required"), "PASS", "main CI gate")

    policy_id = str(policy.get("standard_policy_config_id", ""))
    policy_hash = str(policy.get("standard_policy_config_hash", ""))
    evaluator_id = str(policy.get("evaluator_snapshot_id", ""))
    evaluator_hash = str(policy.get("evaluator_snapshot_sha256", ""))
    learning_hash = str(policy.get("learning_plan_sha256", ""))
    if not policy_id or any(len(value) != 64 for value in (policy_hash, evaluator_hash, learning_hash)):
        raise PhaseCControlError("Phase C policy and evaluator bindings are incomplete")
    _require_exact(policy.get("policy_mutation_allowed"), False, "policy-mutation flag")
    _require_exact(
        policy.get("exploratory_continuation_policy_config_id"),
        policy_id,
        "exploratory continuation policy",
    )

    return PhaseCConfiguration(
        path,
        payload,
        file_sha256(path),
        str(authorization["confirmation_token"]),
        bool(authorization.get("execution_allowed")),
        str(authorization.get("status", "")),
        int(pilot["standard_games"]),
        int(pilot["exploratory_games"]),
        standard_namespace,
        exploratory_namespace,
        policy_id,
        policy_hash,
        evaluator_id,
        evaluator_hash,
        learning_hash,
    )


def load_phase_c_approval(path: Path = DEFAULT_APPROVAL) -> PhaseCApproval:
    payload = _load_object(path, "Phase C pilot approval")
    _require_exact(payload.get("schema_version"), "phase-c-pilot-approval-v1", "approval schema")
    token_digest = str(payload.get("confirmation_token_sha256", ""))
    expected_token_digest = hashlib.sha256(CONFIRMATION_TOKEN.encode("utf-8")).hexdigest()
    if token_digest != expected_token_digest:
        raise PhaseCControlError("approval record is bound to a different confirmation token")
    counts = _require_mapping(payload.get("authorized_counts"), "authorized_counts")
    _require_exact(counts.get("standard"), STANDARD_GAMES, "approved standard count")
    _require_exact(counts.get("exploratory"), EXPLORATORY_GAMES, "approved exploratory count")
    return PhaseCApproval(
        path,
        payload,
        file_sha256(path),
        str(payload.get("status", "")),
        str(payload["approved_by"]) if payload.get("approved_by") is not None else None,
        str(payload["approved_at"]) if payload.get("approved_at") is not None else None,
        str(payload["authorized_commit"])
        if payload.get("authorized_commit") is not None
        else None,
        str(payload["pilot_config_sha256"])
        if payload.get("pilot_config_sha256") is not None
        else None,
        str(payload["workflow_sha256"]) if payload.get("workflow_sha256") is not None else None,
        token_digest,
        str(payload["approval_statement"])
        if payload.get("approval_statement") is not None
        else None,
    )


def _derive_seeds(namespace: str, count: int) -> tuple[int, ...]:
    values: list[int] = []
    for game_index in range(1, count + 1):
        material = f"{namespace}:{game_index}".encode("utf-8")
        values.append(int.from_bytes(hashlib.sha256(material).digest()[:8], "big"))
    return tuple(values)


def build_pilot_seed_plan(config: PhaseCConfiguration) -> PilotSeedPlan:
    standard = _derive_seeds(config.standard_seed_namespace, config.standard_games)
    exploratory = _derive_seeds(config.exploratory_seed_namespace, config.exploratory_games)
    return PilotSeedPlan(
        standard,
        exploratory,
        hashlib.sha256(_canonical(standard)).hexdigest(),
        hashlib.sha256(_canonical(exploratory)).hexdigest(),
    )


def dry_run_phase_c(
    config_path: Path = DEFAULT_CONFIG,
    approval_path: Path = DEFAULT_APPROVAL,
    workflow_path: Path = DEFAULT_WORKFLOW,
) -> PhaseCDryRunReport:
    """Validate the complete locked control plane without creating a game result."""

    config = load_phase_c_config(config_path)
    approval = load_phase_c_approval(approval_path)
    seeds = build_pilot_seed_plan(config)
    workflow_sha = file_sha256(workflow_path)
    full_study = _require_mapping(config.payload.get("full_study"), "full_study")
    status = "READY_FOR_OWNER_REVIEW" if not CURRENT_ENGINE_BLOCKERS else "LOCKED_ENGINE_INCOMPLETE"
    return PhaseCDryRunReport(
        "phase-c-dry-run-v1",
        status,
        config.sha256,
        approval.sha256,
        workflow_sha,
        config.policy_config_id,
        config.evaluator_snapshot_id,
        config.standard_games,
        config.exploratory_games,
        seeds.standard_sha256,
        seeds.exploratory_sha256,
        config.execution_allowed,
        config.authorization_status,
        CURRENT_ENGINE_BLOCKERS,
        0,
        bool(full_study.get("execution_allowed")),
    )


def _git_head(root: Path = ROOT) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


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
    """Require exact owner and digest authorization before any output path is created."""

    config = load_phase_c_config(config_path)
    approval = load_phase_c_approval(approval_path)
    seeds = build_pilot_seed_plan(config)
    if confirmation != CONFIRMATION_TOKEN:
        raise PhaseCControlError("Phase C confirmation token does not match")
    if requested_standard_games != STANDARD_GAMES or requested_exploratory_games != EXPLORATORY_GAMES:
        raise PhaseCControlError("Phase C execution requires exactly 500 standard and 200 exploratory games")
    if config.sha256 != expected_config_sha256:
        raise PhaseCControlError("Phase C configuration digest differs from the requested digest")
    workflow_sha = file_sha256(workflow_path)
    if workflow_sha != expected_workflow_sha256:
        raise PhaseCControlError("Phase C workflow digest differs from the requested digest")
    if _git_head(root) != authorized_commit:
        raise PhaseCControlError("checked-out commit differs from the authorized implementation commit")
    if not config.execution_allowed or config.authorization_status != "AUTHORIZED":
        raise PhaseCControlError("Phase C configuration remains locked")
    if approval.status != "APPROVED":
        raise PhaseCControlError("Phase C owner approval record remains pending")
    if not approval.approved_by or not approval.approved_at or not approval.approval_statement:
        raise PhaseCControlError("Phase C owner approval metadata is incomplete")
    if approval.authorized_commit != authorized_commit:
        raise PhaseCControlError("approval record is bound to a different implementation commit")
    if approval.pilot_config_sha256 != config.sha256:
        raise PhaseCControlError("approval record is bound to a different pilot configuration")
    if approval.workflow_sha256 != workflow_sha:
        raise PhaseCControlError("approval record is bound to a different workflow")
    if CURRENT_ENGINE_BLOCKERS:
        raise PhaseCControlError(
            "Phase C production engine remains incomplete: " + ", ".join(CURRENT_ENGINE_BLOCKERS)
        )
    return config, approval, seeds


def execute_phase_c_pilot(**arguments: Any) -> None:
    """Fail before filesystem mutation until the production game driver is complete."""

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
    "PilotSeedPlan",
    "STANDARD_GAMES",
    "build_pilot_seed_plan",
    "dry_run_phase_c",
    "execute_phase_c_pilot",
    "file_sha256",
    "load_phase_c_approval",
    "load_phase_c_config",
    "validate_execution_authorization",
]
