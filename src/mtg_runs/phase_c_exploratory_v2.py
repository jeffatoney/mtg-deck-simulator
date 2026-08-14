"""Non-authorized Phase C exploratory V2 clean-engine runner.

The historical V1 pilot path is intentionally not imported as an artifact writer.
This module reuses the frozen engine, broker, STANDARD policy, measurements, and
replay machinery while keeping V2 decisions in a separate diagnostic schema.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from mtg_deck import build_exact_game
from mtg_kernel.engine import GameExecutor
from mtg_kernel.errors import UnsupportedCapability
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import Zone
from mtg_kernel.observation import ObservationService
from mtg_kernel.replay import transcript, validate_replay
from mtg_measure import ComboAccessTracker, GameMeasurement, bind_combo_access_tracker
from mtg_policy import ActionBroker, StandardPolicy
from mtg_policy.broker_core import ObservedAction
from mtg_policy.exploratory_v2 import (
    ExploratoryStrategicChoiceProvider,
    NoveltyLedger,
    PublicProjection,
    assert_no_glint_tutor_selection,
    canonical_interaction_signature,
    score_priority_candidate,
    semantic_action_key,
)
from mtg_runs.phase_c_runner import (
    CONTROLLED_PLAYER,
    MAX_ACTIONS_PER_PRIORITY_WINDOW,
    PLAYER_IDS,
    TURN_STEPS,
    ExploratoryDecisionRecord,
    OpeningHandRecord,
    _GameMeasurementCapture,
    _auto_pass_opponents_until_control,
    _bound_policy,
    _build_game_measurement,
    _choose_mulligan,
    _cleanup_discard_ids,
    _combat_optional_trigger_choices,
    _combo_evaluation,
    _delayed_trigger_step_choices,
    _finalize_refill_names,
    _policy_window_required,
    _resolve_required_stack,
)
from mtg_search.directed_v2 import (
    ARM_IDS,
    CandidateScoreVector,
    DirectedArmConfig,
    DirectedCandidate,
    canonical_sha256,
    load_directed_arm_config,
    select_directed_candidate,
)

ROOT = Path(__file__).resolve().parents[2]
DECISION_SCHEMA = "phase-c-exploratory-v2-decision-v1"
TECHNICAL_SCHEMA = "phase-c-exploratory-v2-technical-game-v1"
EXECUTION_SCHEMA = "phase-c-exploratory-v2-game-execution-v1"

_HIDDEN_BOUNDARY_MARKERS = (
    "DRAW",
    "SCRY",
    "LOOK",
    "RANDOM",
    "SHUFFLE",
    "SEARCH",
    "TUTOR",
    "TRANSMUTE",
    "TYPECYCLE",
    "LANDCYCLE",
    "IMPULSE",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _public_observation(executor: GameExecutor) -> Mapping[str, Any]:
    return ObservationService(executor.state).observe_for_policy(CONTROLLED_PLAYER)


def _public_digest(executor: GameExecutor) -> str:
    return canonical_sha256(_public_observation(executor))


def _crosses_hidden_boundary(action: ObservedAction) -> bool:
    material = " ".join((action.kind, action.identity or "", *action.tags)).upper()
    return any(marker in material for marker in _HIDDEN_BOUNDARY_MARKERS)


@dataclass(frozen=True)
class ExploratoryV2DecisionRecord:
    schema_version: str
    arm_id: str
    game_index: int
    environment_seed: int
    exploration_seed: int
    decision_id: str
    turn: int
    phase: str
    public_observation_digest: str
    strategic_choice_purpose: str
    legal_candidate_handles: tuple[str, ...]
    standard_baseline_handle: str
    standard_baseline_score_vector: Mapping[str, Any]
    candidate_evaluations: tuple[Mapping[str, Any], ...]
    pruned_candidates: tuple[Mapping[str, Any], ...]
    arm_specific_exclusions: tuple[Mapping[str, Any], ...]
    novelty_state_before: Mapping[str, int]
    equivalence_window: Mapping[str, int]
    eligible_top_k: tuple[str, ...]
    selected_action: str
    selection_reason: str
    randomness_affected_selection: bool
    selected_plan_or_package_id: str | None
    continuation_method: str
    continuation_horizon: Mapping[str, Any]
    plan_termination_or_fallback_reason: str | None
    resulting_public_state_digest: str | None
    replay_binding: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.schema_version != DECISION_SCHEMA:
            raise ValueError("unsupported exploratory V2 decision schema")
        handles = set(self.legal_candidate_handles)
        if self.standard_baseline_handle not in handles:
            raise ValueError("V2 decision lost the STANDARD baseline candidate")
        if self.selected_action not in handles:
            raise ValueError("V2 decision selected a non-legal candidate")
        if self.selected_action not in self.eligible_top_k:
            raise ValueError("V2 selected candidate is outside eligible top-k")
        if len(self.public_observation_digest) != 64:
            raise ValueError("V2 public observation digest is malformed")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExploratoryV2TechnicalGame:
    schema_version: str
    artifact_classification: str
    arm_id: str
    reporting_label: str
    arm_config_sha256: str
    seed: int
    exploration_seed: int
    policy_config_id: str
    environment_initial_state_hash: str
    opening_hands: tuple[OpeningHandRecord, ...]
    controlled_turns_completed: int
    terminal_status: str
    command_count: int
    replay_digest: str
    final_state_hash: str
    fresh_replay_state_hash: str
    combo_earliest_legal_turn: Mapping[str, int | None]
    combo_checkpoint_access: Mapping[str, Mapping[int, bool]]
    decisions: tuple[ExploratoryV2DecisionRecord, ...]
    strategic_choice_records: tuple[Mapping[str, Any], ...]
    decision_evidence_sha256: str
    baseline_candidate_retained: int
    baseline_candidate_required: int
    candidate_score_vectors_persisted: int
    candidate_score_vectors_required: int
    land_guardrail_applicable: int
    land_guardrail_compliant: int
    pilot_result: bool = False
    authorized_pilot_result: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != TECHNICAL_SCHEMA:
            raise ValueError("unsupported exploratory V2 technical schema")
        if self.artifact_classification != "NON_AUTHORIZED_DIAGNOSTIC":
            raise ValueError("exploratory V2 technical game must be diagnostic-only")
        if self.arm_id not in ARM_IDS:
            raise ValueError("exploratory V2 technical game has unknown arm")
        if self.pilot_result or self.authorized_pilot_result:
            raise ValueError("exploratory V2 technical games cannot be pilot results")
        if self.final_state_hash != self.fresh_replay_state_hash:
            raise ValueError("exploratory V2 fresh transcript replay diverged")
        if self.baseline_candidate_retained != self.baseline_candidate_required:
            raise ValueError("exploratory V2 baseline candidate retention is incomplete")
        if self.candidate_score_vectors_persisted != self.candidate_score_vectors_required:
            raise ValueError("exploratory V2 candidate score evidence is incomplete")
        if self.land_guardrail_compliant != self.land_guardrail_applicable:
            raise ValueError("exploratory V2 land-development compliance is incomplete")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExploratoryV2GameExecution:
    schema_version: str
    technical_game: ExploratoryV2TechnicalGame
    measurement: GameMeasurement
    replay_transcript: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.schema_version != EXECUTION_SCHEMA:
            raise ValueError("unsupported exploratory V2 execution schema")
        if self.measurement.seed != self.technical_game.seed:
            raise ValueError("V2 measurement seed differs from technical game")
        if self.measurement.mode != "EXPLORATORY":
            raise ValueError("V2 measurement must retain the historical EXPLORATORY mode label")
        if str(self.replay_transcript.get("digest", "")) != self.technical_game.replay_digest:
            raise ValueError("V2 transcript digest differs from technical game")


@dataclass(frozen=True)
class _ProjectedCandidate:
    projection: PublicProjection
    package_id: str | None


class DirectedExplorerV2:
    """One strategic deviation plus bounded visible STANDARD continuation."""

    def __init__(
        self,
        *,
        policy_config_id: str,
        config: DirectedArmConfig,
        exploration_seed: int,
        environment_seed: int,
        game_index: int,
        novelty: NoveltyLedger,
    ) -> None:
        self.policy_config_id = policy_config_id
        self.config = config
        self.exploration_seed = exploration_seed
        self.environment_seed = environment_seed
        self.game_index = game_index
        self.novelty = novelty
        self.records: list[ExploratoryV2DecisionRecord] = []
        self._pending_signature: str | None = None
        self._divergence_seen = False

    @staticmethod
    def _clone_executor(executor: GameExecutor) -> GameExecutor:
        live = executor.state
        replay_initial = live.replay_initial_state
        replay_commands = live.replay_commands
        live.replay_initial_state = None
        live.replay_commands = []
        try:
            cloned_state = deepcopy(live)
        finally:
            live.replay_initial_state = replay_initial
            live.replay_commands = replay_commands
        cloned_state.replay_initial_state = replay_initial
        cloned_state.replay_commands = list(replay_commands)
        return GameExecutor(cloned_state, executor.seed)

    def _project_candidate(
        self,
        executor: GameExecutor,
        action: ObservedAction,
    ) -> PublicProjection:
        clone = self._clone_executor(executor)
        standard, _provider, evaluator_config = _bound_policy(clone, self.policy_config_id)
        tracker = bind_combo_access_tracker(
            clone, CONTROLLED_PLAYER, evaluator_config.combo_packages
        )
        before = _combo_evaluation(clone, tracker)
        before_turn = None if before.expected_win_turn >= 99 else before.expected_win_turn
        if _crosses_hidden_boundary(action):
            return PublicProjection(
                immediate_deterministic_access=before.immediate_legal_table_win,
                projected_deterministic_access=before.immediate_legal_table_win,
                earliest_projected_access_turn=before_turn,
                continuation_actions=(),
                stop_reason="HIDDEN_INFORMATION_BOUNDARY",
                action_count=0,
            )

        broker = ActionBroker(clone, CONTROLLED_PLAYER)
        observation, actions = broker.refresh()
        match = next((candidate for candidate in actions if candidate.handle == action.handle), None)
        if match is None:
            key = semantic_action_key(action)
            matches = [candidate for candidate in actions if semantic_action_key(candidate) == key]
            if len(matches) != 1:
                raise UnsupportedCapability("V2 projection could not identify candidate in clone")
            match = matches[0]
        broker.execute(int(observation["generation"]), match.handle)
        after = _combo_evaluation(clone, tracker)
        continuation: list[str] = []
        stop_reason = "STANDARD_PASS"
        for _ in range(self.config.continuation_action_limit):
            if clone.state.terminal.status != "ACTIVE":
                stop_reason = "TERMINAL"
                break
            if clone.state.turn.priority_holder_id != CONTROLLED_PLAYER:
                stop_reason = "PRIORITY_LEFT_CONTROLLED_PLAYER"
                break
            next_broker = ActionBroker(clone, CONTROLLED_PLAYER)
            next_observation, next_actions = next_broker.refresh()
            if not next_actions:
                stop_reason = "NO_LEGAL_ACTION"
                break
            handle = standard.select_action(dict(next_observation), next_actions)
            selected = next(candidate for candidate in next_actions if candidate.handle == handle)
            if selected.kind == "PASS_PRIORITY":
                stop_reason = "STANDARD_PASS"
                break
            continuation.append(semantic_action_key(selected))
            if _crosses_hidden_boundary(selected):
                stop_reason = "HIDDEN_INFORMATION_BOUNDARY"
                break
            next_broker.execute(int(next_observation["generation"]), selected.handle)
            after = _combo_evaluation(clone, tracker)
        else:
            stop_reason = "CONTINUATION_ACTION_LIMIT"

        projected_turn = None if after.expected_win_turn >= 99 else after.expected_win_turn
        return PublicProjection(
            immediate_deterministic_access=after.immediate_legal_table_win,
            projected_deterministic_access=after.immediate_legal_table_win,
            earliest_projected_access_turn=projected_turn,
            continuation_actions=tuple(continuation),
            stop_reason=stop_reason,
            action_count=len(continuation),
        )

    def choose(
        self,
        executor: GameExecutor,
        observation: Mapping[str, Any],
        actions: tuple[ObservedAction, ...],
        standard_handle: str,
    ) -> str:
        if len(actions) == 1:
            return standard_handle
        observation_digest = canonical_sha256(observation)
        decision_id = hashlib.sha256(
            (
                f"priority-v2:{self.config.arm_id}:{self.game_index}:"
                f"{executor.state.turn.number}:{executor.state.turn.phase}:"
                f"{executor.state.turn.step}:{len(self.records)}:{observation_digest}"
            ).encode("utf-8")
        ).hexdigest()[:24]
        novelty_before = self.novelty.snapshot()
        tracker = getattr(executor, "combo_access_tracker", None)
        if not isinstance(tracker, ComboAccessTracker):
            raise UnsupportedCapability("V2 priority decision requires combo tracker")
        package_definitions = tracker.package_definitions

        directed: list[DirectedCandidate] = []
        projections: dict[str, _ProjectedCandidate] = {}
        signatures: dict[str, str] = {}
        for action in actions:
            signature = canonical_interaction_signature(
                purpose=f"PRIORITY:{executor.state.turn.step}",
                action_kind=action.kind,
                identity=action.identity,
                metadata=action.metadata,
            )
            signatures[action.handle] = signature
            projection = self._project_candidate(executor, action)
            score, prune, package_id = score_priority_candidate(
                action=action,
                observation=observation,
                all_actions=actions,
                config=self.config,
                projection=projection,
                novelty_value=self.novelty.novelty_value(signature),
                combo_packages=package_definitions,
            )
            directed.append(
                DirectedCandidate(
                    handle=action.handle,
                    semantic_key=semantic_action_key(action),
                    score=score,
                    pruned_reason=prune,
                )
            )
            projections[action.handle] = _ProjectedCandidate(projection, package_id)

        selection = select_directed_candidate(
            self.config,
            directed,
            baseline_handle=standard_handle,
            exploration_seed=self.exploration_seed,
            decision_id=decision_id,
        )
        by_handle = {candidate.handle: candidate for candidate in selection.candidates}
        baseline = by_handle[standard_handle]
        selected_projection = projections[selection.selected_handle]
        pruned = tuple(
            {"handle": candidate.handle, "reason": candidate.pruned_reason}
            for candidate in selection.candidates
            if candidate.pruned_reason is not None
        )
        exclusions = tuple(
            {
                "handle": candidate.handle,
                "constraint_status": candidate.score.arm_constraint_status,
                "reason": candidate.pruned_reason,
            }
            for candidate in selection.candidates
            if candidate.score.arm_constraint_status.startswith("PROHIBITED_")
        )
        first_divergence = selection.selected_handle != standard_handle and not self._divergence_seen
        self._divergence_seen = self._divergence_seen or first_divergence
        record = ExploratoryV2DecisionRecord(
            schema_version=DECISION_SCHEMA,
            arm_id=self.config.arm_id,
            game_index=self.game_index,
            environment_seed=self.environment_seed,
            exploration_seed=self.exploration_seed,
            decision_id=decision_id,
            turn=int(executor.state.turn.number),
            phase=str(executor.state.turn.phase),
            public_observation_digest=observation_digest,
            strategic_choice_purpose=f"PRIORITY:{executor.state.turn.step}",
            legal_candidate_handles=tuple(action.handle for action in actions),
            standard_baseline_handle=standard_handle,
            standard_baseline_score_vector=baseline.score.to_dict(),
            candidate_evaluations=tuple(
                {
                    "handle": candidate.handle,
                    "semantic_key": candidate.semantic_key,
                    "score": candidate.score.to_dict(),
                    "pruned_reason": candidate.pruned_reason,
                }
                for candidate in selection.candidates
            ),
            pruned_candidates=pruned,
            arm_specific_exclusions=exclusions,
            novelty_state_before=novelty_before,
            equivalence_window=dict(self.config.equivalence_window),
            eligible_top_k=selection.eligible_top_k,
            selected_action=selection.selected_handle,
            selection_reason=selection.selection_reason,
            randomness_affected_selection=selection.randomness_affected_selection,
            selected_plan_or_package_id=selected_projection.package_id,
            continuation_method=self.config.continuation_method,
            continuation_horizon={
                "maximum_standard_actions": self.config.continuation_action_limit,
                "projected_standard_actions": list(
                    selected_projection.projection.continuation_actions
                ),
                "projected_action_count": selected_projection.projection.action_count,
                "hidden_future_consumed": False,
            },
            plan_termination_or_fallback_reason=selected_projection.projection.stop_reason,
            resulting_public_state_digest=None,
            replay_binding={
                "command_count_before": len(executor.state.replay_commands),
                "first_divergence": first_divergence,
            },
        )
        self.records.append(record)
        self._pending_signature = signatures[selection.selected_handle]
        return selection.selected_handle

    def record_result(self, executor: GameExecutor) -> None:
        if not self.records or self._pending_signature is None:
            return
        self.novelty.visit(self._pending_signature)
        self._pending_signature = None
        current = self.records[-1]
        self.records[-1] = replace(
            current,
            resulting_public_state_digest=_public_digest(executor),
            replay_binding={
                **dict(current.replay_binding),
                "command_count_after": len(executor.state.replay_commands),
            },
        )


def _priority_window_v2(
    executor: GameExecutor,
    policy: StandardPolicy,
    explorer: DirectedExplorerV2,
    measurement: _GameMeasurementCapture,
) -> None:
    actions_used = 0
    while executor.state.terminal.status == "ACTIVE":
        _auto_pass_opponents_until_control(executor)
        if executor.state.terminal.status != "ACTIVE":
            return
        if executor.state.turn.priority_holder_id != CONTROLLED_PLAYER:
            return
        broker = ActionBroker(executor, CONTROLLED_PLAYER)
        observation, actions = broker.refresh()
        if not actions:
            raise UnsupportedCapability("V2 controlled priority exposes no legal broker action")
        standard_handle = policy.select_action(dict(observation), actions)
        selected_handle = explorer.choose(executor, observation, actions, standard_handle)
        selected = next(action for action in actions if action.handle == selected_handle)
        tracker = getattr(executor, "combo_access_tracker", None)
        if isinstance(tracker, ComboAccessTracker):
            measurement.observe_selected_action(executor, tracker, selected)
        broker.execute(int(observation["generation"]), selected_handle)
        explorer.record_result(executor)
        actions_used += 1
        if actions_used > MAX_ACTIONS_PER_PRIORITY_WINDOW:
            raise UnsupportedCapability("V2 priority window exceeded bounded action count")
        if selected.kind != "PASS_PRIORITY":
            continue
        stack_before = bool(executor.state.stack)
        _auto_pass_opponents_until_control(executor)
        if executor.state.terminal.status != "ACTIVE":
            return
        if stack_before:
            continue
        return


def _decision_summary_records(
    records: Sequence[ExploratoryV2DecisionRecord],
) -> tuple[ExploratoryDecisionRecord, ...]:
    result: list[ExploratoryDecisionRecord] = []
    divergence_seen = False
    for record in records:
        diverged = record.selected_action != record.standard_baseline_handle
        first = diverged and not divergence_seen
        divergence_seen = divergence_seen or diverged
        result.append(
            ExploratoryDecisionRecord(
                turn=record.turn,
                phase=record.phase,
                step=record.strategic_choice_purpose.removeprefix("PRIORITY:"),
                standard_action=record.standard_baseline_handle,
                exploratory_action=record.selected_action,
                branches_searched=len(record.candidate_evaluations),
                nodes_evaluated=sum(
                    int(item.get("score") is not None) for item in record.candidate_evaluations
                ),
                decision_layer_depth=2,
                first_divergence=first,
            )
        )
    return tuple(result)


def _evidence_counts(
    records: Sequence[ExploratoryV2DecisionRecord],
) -> tuple[int, int, int, int, int, int]:
    baseline_required = len(records)
    baseline_retained = sum(
        record.standard_baseline_handle in record.legal_candidate_handles for record in records
    )
    required_vectors = sum(len(record.legal_candidate_handles) for record in records)
    persisted_vectors = sum(len(record.candidate_evaluations) for record in records)
    land_applicable = 0
    land_compliant = 0
    for record in records:
        land_prunes = [
            item
            for item in record.pruned_candidates
            if item.get("reason") == "MAIN_PHASE_LAND_AVAILABLE_WITHOUT_VALID_HOLD_REASON"
        ]
        if land_prunes:
            land_applicable += 1
            if record.selected_action not in {str(item.get("handle")) for item in land_prunes}:
                land_compliant += 1
    return (
        baseline_retained,
        baseline_required,
        persisted_vectors,
        required_vectors,
        land_compliant,
        land_applicable,
    )


def run_exploratory_v2_game_execution(
    *,
    seed: int,
    arm_id: str,
    exploration_seed: int,
    game_index: int = 1,
    policy_config_id: str = "anchor_balanced",
    through_turn: int = 10,
    validate_fresh_replay: bool = True,
) -> ExploratoryV2GameExecution:
    """Run one diagnostic-only V2 game through the clean production engine path."""

    config = load_directed_arm_config(arm_id)
    if config.pilot_activation:
        raise ValueError("V2 runner refuses pilot-active config")
    if through_turn < 1 or through_turn > 10:
        raise ValueError("V2 turn horizon must be within 1..10")
    if game_index < 1:
        raise ValueError("V2 game_index must be positive")
    seed_text = f"phase-c-v2:{arm_id}:{seed}"
    state, executor, _ = build_exact_game(seed_text, PLAYER_IDS)
    environment_initial_state_hash = state_hash(state)
    policy, baseline_provider, evaluator_config = _bound_policy(executor, policy_config_id)
    novelty = NoveltyLedger()
    provider = ExploratoryStrategicChoiceProvider(
        baseline_provider,
        config,
        exploration_seed=exploration_seed,
        environment_seed=seed,
        game_index=game_index,
        novelty=novelty,
    )
    executor.bind_strategic_choice_provider(provider)
    tracker = bind_combo_access_tracker(
        executor, CONTROLLED_PLAYER, evaluator_config.combo_packages
    )
    capture = _GameMeasurementCapture()
    initial_state = deepcopy(state)
    keep_index, opening = _choose_mulligan(initial_state, seed_text, policy)
    executor.league_mulligan(CONTROLLED_PLAYER, keep_index)
    opening = _finalize_refill_names(executor, opening)
    explorer = DirectedExplorerV2(
        policy_config_id=policy_config_id,
        config=config,
        exploration_seed=exploration_seed,
        environment_seed=seed,
        game_index=game_index,
        novelty=novelty,
    )

    completed_turns = 0
    for turn_number in range(1, through_turn + 1):
        if state.terminal.status != "ACTIVE":
            break
        if turn_number > 1:
            executor.start_next_controlled_turn(CONTROLLED_PLAYER)
        if state.turn.number != turn_number:
            raise UnsupportedCapability("V2 controlled turn number diverged from horizon")
        for step in TURN_STEPS:
            if state.terminal.status != "ACTIVE":
                break
            if step == "CLEANUP":
                while True:
                    discard_ids = _cleanup_discard_ids(executor, provider)
                    executor.begin_step("CLEANUP", {"discard_ids": list(discard_ids)})
                    if not state.turn.cleanup_repeat_pending:
                        break
                    while state.stack and state.terminal.status == "ACTIVE":
                        (
                            _priority_window_v2(executor, policy, explorer, capture)
                            if _policy_window_required("CLEANUP", executor)
                            else _resolve_required_stack(executor)
                        )
                    if state.terminal.status != "ACTIVE":
                        break
                continue
            if step == "DECLARE_BLOCKERS":
                attackers = any(
                    not obj.retired
                    and obj.zone is Zone.BATTLEFIELD
                    and obj.current_characteristics.get("attacking") is True
                    for obj in state.objects.values()
                )
                if not attackers:
                    continue
                executor.begin_step(step)
                executor.declare_no_blockers()
                (
                    _priority_window_v2(executor, policy, explorer, capture)
                    if _policy_window_required(step, executor)
                    else _resolve_required_stack(executor)
                )
                continue
            if step == "COMBAT_DAMAGE":
                attackers = any(
                    not obj.retired
                    and obj.zone is Zone.BATTLEFIELD
                    and obj.controller == CONTROLLED_PLAYER
                    and obj.current_characteristics.get("attacking") is True
                    for obj in state.objects.values()
                )
                if not attackers:
                    continue
                executor.begin_step(step)
                executor.resolve_no_blocker_combat_damage(
                    _combat_optional_trigger_choices(executor, policy)
                )
                (
                    _priority_window_v2(executor, policy, explorer, capture)
                    if _policy_window_required(step, executor)
                    else _resolve_required_stack(executor)
                )
                continue
            executor.begin_step(step, _delayed_trigger_step_choices(executor, step))
            if step != "UNTAP":
                (
                    _priority_window_v2(executor, policy, explorer, capture)
                    if _policy_window_required(step, executor)
                    else _resolve_required_stack(executor)
                )
        if state.terminal.status == "ACTIVE" and state.turn.step != "CLEANUP":
            raise UnsupportedCapability("V2 controlled turn ended before cleanup completed")
        capture.record_turn_end(executor, tracker)
        completed_turns = turn_number

    body = transcript(state, seed=seed_text)
    replayed = validate_replay(body)
    replay_hash = state_hash(replayed)
    fresh_hash = replay_hash
    if validate_fresh_replay:
        from mtg_runs.replay_audit import replay_in_fresh_process

        fresh_hash = replay_in_fresh_process(body, cwd=ROOT).state_hash

    decisions = tuple(explorer.records)
    if any(record.resulting_public_state_digest is None for record in decisions):
        raise UnsupportedCapability("V2 decision record is missing resulting public-state digest")
    assert_no_glint_tutor_selection(provider.records)
    summary_records = _decision_summary_records(decisions)
    measurement = _build_game_measurement(
        executor=executor,
        tracker=tracker,
        evaluator_config=evaluator_config,
        opening=opening,
        mode="EXPLORATORY",
        seed=seed,
        policy_config_id=policy_config_id,
        capture=capture,
        exploratory_records=summary_records,
        environment_initial_state_hash=environment_initial_state_hash,
        search_seed=exploration_seed,
        pair_id=None,
        paired_standard_game_index=None,
    )
    measurement = replace(
        measurement,
        extra={
            **dict(measurement.extra),
            "exploratory_v2_arm_id": arm_id,
            "exploratory_v2_arm_config_sha256": config.config_sha256,
            "artifact_classification": "NON_AUTHORIZED_DIAGNOSTIC",
            "strategic_choice_records": tuple(provider.records),
        },
    )
    earliest = {
        package: tracker.earliest_legal_turn(package)
        for package in sorted(evaluator_config.combo_packages)
    }
    checkpoints = {
        package: tracker.cumulative_checkpoint_access(package)
        for package in sorted(evaluator_config.combo_packages)
    }
    (
        baseline_retained,
        baseline_required,
        vectors_persisted,
        vectors_required,
        land_compliant,
        land_applicable,
    ) = _evidence_counts(decisions)
    evidence_payload = {
        "decisions": [record.to_dict() for record in decisions],
        "strategic_choices": provider.records,
    }
    technical = ExploratoryV2TechnicalGame(
        schema_version=TECHNICAL_SCHEMA,
        artifact_classification="NON_AUTHORIZED_DIAGNOSTIC",
        arm_id=arm_id,
        reporting_label=config.reporting_label,
        arm_config_sha256=config.config_sha256,
        seed=seed,
        exploration_seed=exploration_seed,
        policy_config_id=policy_config_id,
        environment_initial_state_hash=environment_initial_state_hash,
        opening_hands=opening,
        controlled_turns_completed=completed_turns,
        terminal_status=state.terminal.status,
        command_count=len(state.replay_commands),
        replay_digest=str(body["digest"]),
        final_state_hash=state_hash(state),
        fresh_replay_state_hash=fresh_hash,
        combo_earliest_legal_turn=earliest,
        combo_checkpoint_access=checkpoints,
        decisions=decisions,
        strategic_choice_records=tuple(provider.records),
        decision_evidence_sha256=canonical_sha256(evidence_payload),
        baseline_candidate_retained=baseline_retained,
        baseline_candidate_required=baseline_required,
        candidate_score_vectors_persisted=vectors_persisted,
        candidate_score_vectors_required=vectors_required,
        land_guardrail_applicable=land_applicable,
        land_guardrail_compliant=land_compliant,
    )
    return ExploratoryV2GameExecution(EXECUTION_SCHEMA, technical, measurement, body)


def recompute_decision_evidence_in_fresh_process(
    *,
    seed: int,
    arm_id: str,
    exploration_seed: int,
    game_index: int = 1,
    policy_config_id: str = "anchor_balanced",
    through_turn: int = 10,
) -> Mapping[str, Any]:
    """Re-run V2 policy selection in a fresh Python process and return its digest."""

    command = [
        sys.executable,
        "-m",
        "mtg_runs.phase_c_exploratory_v2",
        "--recompute",
        "--seed",
        str(seed),
        "--arm-id",
        arm_id,
        "--exploration-seed",
        str(exploration_seed),
        "--game-index",
        str(game_index),
        "--policy-config-id",
        policy_config_id,
        "--through-turn",
        str(through_turn),
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, Mapping):
        raise ValueError("fresh V2 recomputation did not return an object")
    return payload


def _recompute_payload(args: argparse.Namespace) -> Mapping[str, Any]:
    execution = run_exploratory_v2_game_execution(
        seed=args.seed,
        arm_id=args.arm_id,
        exploration_seed=args.exploration_seed,
        game_index=args.game_index,
        policy_config_id=args.policy_config_id,
        through_turn=args.through_turn,
        validate_fresh_replay=False,
    )
    game = execution.technical_game
    return {
        "arm_id": game.arm_id,
        "seed": game.seed,
        "exploration_seed": game.exploration_seed,
        "final_state_hash": game.final_state_hash,
        "replay_digest": game.replay_digest,
        "decision_evidence_sha256": game.decision_evidence_sha256,
    }


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--arm-id", choices=sorted(ARM_IDS), required=True)
    parser.add_argument("--exploration-seed", type=int, required=True)
    parser.add_argument("--game-index", type=int, default=1)
    parser.add_argument("--policy-config-id", default="anchor_balanced")
    parser.add_argument("--through-turn", type=int, default=10)
    args = parser.parse_args()
    if not args.recompute:
        parser.error("this module CLI is reserved for deterministic --recompute")
    print(json.dumps(_recompute_payload(args), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "DECISION_SCHEMA",
    "EXECUTION_SCHEMA",
    "TECHNICAL_SCHEMA",
    "DirectedExplorerV2",
    "ExploratoryV2DecisionRecord",
    "ExploratoryV2GameExecution",
    "ExploratoryV2TechnicalGame",
    "recompute_decision_evidence_in_fresh_process",
    "run_exploratory_v2_game_execution",
]
