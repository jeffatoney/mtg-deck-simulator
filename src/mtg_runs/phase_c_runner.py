"""Bounded clean-engine Phase C technical runner.

This module executes no authorized pilot by itself.  It supplies the production
path used by dry-run readiness checks and, after separate owner activation, by the
500/200 adapter.  Every game action remains inside the clean GameExecutor and the
shared opaque ActionBroker.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from mtg_deck import build_exact_game
from mtg_kernel.engine import GameExecutor
from mtg_kernel.errors import IllegalAction, UnsupportedCapability
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import Zone
from mtg_kernel.replay import transcript, validate_replay
from mtg_kernel.strategic_choices import CardSelectionRequest, PublicCard
from mtg_measure import (
    CardMeasurement,
    ComboAccessSnapshot,
    ComboAccessTracker,
    ComboMeasurement,
    GameMeasurement,
    OpeningHandMeasurement,
    bind_combo_access_tracker,
)
from mtg_policy import (
    ActionBroker,
    ContextualEvaluator,
    StandardPolicy,
    bind_policy_strategic_choices,
    load_evaluator_config,
    load_policy_matrix,
)
from mtg_search import BoundedExplorer, SearchEvaluation, SearchPosition

ROOT = Path(__file__).resolve().parents[2]
CONTROLLED_PLAYER = "P0"
PLAYER_IDS = ("P0", "P1", "P2", "P3")
TURN_STEPS = (
    "UNTAP",
    "UPKEEP",
    "DRAW",
    "PRECOMBAT_MAIN",
    "BEGIN_COMBAT",
    "DECLARE_ATTACKERS",
    "DECLARE_BLOCKERS",
    "COMBAT_DAMAGE",
    "END_COMBAT",
    "POSTCOMBAT_MAIN",
    "END",
    "CLEANUP",
)
MAX_ACTIONS_PER_PRIORITY_WINDOW = 256
PILOT_PRODUCTION_DECISION_LAYER_DEPTH = 1


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


@dataclass(frozen=True)
class OpeningHandRecord:
    candidate_index: int
    nominal_size: int
    card_names: tuple[str, ...]
    kept: bool
    refill_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExploratoryDecisionRecord:
    turn: int
    phase: str
    step: str
    standard_action: str
    exploratory_action: str
    branches_searched: int
    nodes_evaluated: int
    decision_layer_depth: int
    first_divergence: bool


@dataclass(frozen=True)
class PhaseCTechnicalGame:
    schema_version: str
    mode: str
    seed: int
    environment_initial_state_hash: str
    search_seed: int | None
    pair_id: str | None
    paired_standard_game_index: int | None
    policy_config_id: str
    opening_hands: tuple[OpeningHandRecord, ...]
    controlled_turns_completed: int
    terminal_status: str
    command_count: int
    replay_digest: str
    final_state_hash: str
    fresh_replay_state_hash: str
    combo_earliest_legal_turn: Mapping[str, int | None]
    combo_checkpoint_access: Mapping[str, Mapping[int, bool]]
    exploratory_decisions: tuple[ExploratoryDecisionRecord, ...]
    exploratory_nodes_evaluated: int
    exploratory_decision_layer_depth: int
    pilot_result: bool = False
    authorized_pilot_result: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != "phase-c-technical-game-v2":
            raise ValueError("unsupported Phase C technical game schema")
        if self.mode not in {"STANDARD", "EXPLORATORY"}:
            raise ValueError("technical game mode must be STANDARD or EXPLORATORY")
        if self.pilot_result or self.authorized_pilot_result:
            raise ValueError("technical games cannot be authorized pilot results")
        if self.fresh_replay_state_hash != self.final_state_hash:
            raise ValueError("technical game fresh replay diverged")
        if self.mode == "STANDARD" and self.exploratory_decision_layer_depth != 0:
            raise ValueError("standard technical games cannot report exploratory depth")
        if self.mode == "STANDARD" and self.search_seed is not None:
            raise ValueError("standard technical games cannot consume exploratory search seeds")
        if self.mode == "EXPLORATORY" and self.search_seed is None:
            raise ValueError("exploratory technical games require a separate search seed")
        if self.mode == "EXPLORATORY" and self.exploratory_decision_layer_depth != 1:
            raise ValueError(
                "exploratory technical games must report one production decision layer"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PhaseCGameExecution:
    schema_version: str
    technical_game: PhaseCTechnicalGame
    measurement: GameMeasurement
    replay_transcript: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.schema_version != "phase-c-game-execution-v1":
            raise ValueError("unsupported Phase C game execution schema")
        if self.measurement.seed != self.technical_game.seed:
            raise ValueError("Phase C execution measurement seed differs from the game")
        if self.measurement.mode != self.technical_game.mode:
            raise ValueError("Phase C execution measurement mode differs from the game")
        if str(self.replay_transcript.get("digest", "")) != self.technical_game.replay_digest:
            raise ValueError("Phase C execution replay digest differs from the game")


class _GameMeasurementCapture:
    def __init__(self) -> None:
        self.actual_first_attempt_turn: int | None = None
        self.attempt_package: str | None = None
        self.attempt_timing: str | None = None
        self.hand_turn_counts: Counter[str] = Counter()
        self.checkpoint_snapshots: dict[int, tuple[ComboAccessSnapshot, ...]] = {}
        self.selected_actions: list[dict[str, Any]] = []

    @staticmethod
    def _current_combo_snapshots(tracker: ComboAccessTracker) -> tuple[ComboAccessSnapshot, ...]:
        package_count = len(tracker.package_definitions)
        if package_count == 0 or len(tracker.records) < package_count:
            return ()
        return tuple(tracker.records[-package_count:])

    @staticmethod
    def _action_commits_to_package(action: Any, package: str, pieces: tuple[str, ...]) -> bool:
        if action.kind == "DECLARE_ATTACKERS":
            attackers = {str(value) for value in action.metadata.get("attacker_identities", ())}
            return package == "malcolm_glint_horn" and "Glint-Horn Buccaneer" in attackers
        identity = None if action.identity is None else str(action.identity)
        return bool(identity and identity in set(pieces) and action.kind != "PASS_PRIORITY")

    def observe_selected_action(
        self, executor: GameExecutor, tracker: ComboAccessTracker, action: Any
    ) -> None:
        snapshots = self._current_combo_snapshots(tracker)
        self.selected_actions.append(
            {
                "turn": int(executor.state.turn.number),
                "phase": str(executor.state.turn.phase),
                "step": str(executor.state.turn.step),
                "kind": str(action.kind),
                "identity": action.identity,
                "handle": str(action.handle),
            }
        )
        if self.actual_first_attempt_turn is not None:
            return
        for snapshot in snapshots:
            pieces = tuple(tracker.package_definitions.get(snapshot.package, ()))
            if not snapshot.legally_executable:
                continue
            if not self._action_commits_to_package(action, snapshot.package, pieces):
                continue
            self.actual_first_attempt_turn = int(executor.state.turn.number)
            self.attempt_package = snapshot.package
            earliest = tracker.earliest_legal_turn(snapshot.package)
            self.attempt_timing = (
                "IMMEDIATE" if earliest == self.actual_first_attempt_turn else "DELAYED"
            )
            return

    def record_turn_end(self, executor: GameExecutor, tracker: ComboAccessTracker) -> None:
        hand_key = executor.zones.zone_key(Zone.HAND, CONTROLLED_PLAYER)
        for object_id in executor.state.zones.get(hand_key, ()):
            name = str(executor.state.objects[object_id].current_characteristics.get("name", ""))
            if name:
                self.hand_turn_counts[name] += 1
        turn = int(executor.state.turn.number)
        if turn in {5, 6, 8, 10}:
            self.checkpoint_snapshots[turn] = tracker.observe(executor)


def _policy_bundle(policy_config_id: str) -> Any:
    return next(
        bundle for bundle in load_policy_matrix() if bundle.policy_config_id == policy_config_id
    )


def _bound_policy(executor: GameExecutor, policy_config_id: str) -> tuple[StandardPolicy, Any, Any]:
    bundle = _policy_bundle(policy_config_id)
    evaluator_config = load_evaluator_config()
    if (
        bundle.evaluator_snapshot_id != evaluator_config.evaluator_id
        or bundle.evaluator_snapshot_sha256 != evaluator_config.config_sha256
    ):
        raise ValueError("Phase C technical runner requires the exact frozen evaluator snapshot")
    evaluator = ContextualEvaluator(evaluator_config)
    provider = bind_policy_strategic_choices(executor, bundle, evaluator)
    return StandardPolicy(bundle, opponent_interaction_modeled=False), provider, evaluator_config


def _candidate_hand_from_probe(
    initial_state: Any,
    seed_text: str,
    candidate_index: int,
) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    probe_state = deepcopy(initial_state)
    probe = GameExecutor(probe_state, seed_text)
    probe.league_mulligan(CONTROLLED_PLAYER, candidate_index)
    candidate_event = next(
        event
        for event in probe.state.events
        if event.kind == "MULLIGAN_CANDIDATE_DRAWN"
        and int(event.payload["candidate_index"]) == candidate_index
    )
    object_ids = tuple(str(value) for value in candidate_event.payload["candidate_object_ids"])
    objects = tuple(probe.state.objects[object_id] for object_id in object_ids)
    names = tuple(str(obj.current_characteristics.get("name", "")) for obj in objects)
    types = tuple(
        tuple(str(value) for value in obj.current_characteristics.get("card_types", ()))
        for obj in objects
    )
    return names, types


def _choose_mulligan(
    initial_state: Any,
    seed_text: str,
    policy: StandardPolicy,
) -> tuple[int, tuple[OpeningHandRecord, ...]]:
    sizes = (7, 7, 6, 5, 4)
    records: list[OpeningHandRecord] = []
    selected = 4
    for index, size in enumerate(sizes):
        names, types = _candidate_hand_from_probe(initial_state, seed_text, index)
        decision = policy.decide_keep(size, names, types)
        keep = decision.keep or index == len(sizes) - 1
        records.append(OpeningHandRecord(index, size, names, keep))
        if keep:
            selected = index
            break
    return selected, tuple(records)


def _finalize_refill_names(
    executor: GameExecutor,
    records: tuple[OpeningHandRecord, ...],
) -> tuple[OpeningHandRecord, ...]:
    if not records:
        return records
    kept = records[-1]
    hand_key = executor.zones.zone_key(Zone.HAND, CONTROLLED_PLAYER)
    final_names = tuple(
        str(executor.state.objects[object_id].current_characteristics.get("name", ""))
        for object_id in executor.state.zones.get(hand_key, ())
    )
    refill_count = 7 - kept.nominal_size
    updated = OpeningHandRecord(
        kept.candidate_index,
        kept.nominal_size,
        kept.card_names,
        True,
        final_names[-refill_count:] if refill_count else (),
    )
    return (*records[:-1], updated)


def _living_players(executor: GameExecutor) -> tuple[str, ...]:
    return tuple(player.player_id for player in executor.state.players.values() if player.in_game)


def _auto_pass_opponents_until_control(executor: GameExecutor) -> None:
    while (
        executor.state.terminal.status == "ACTIVE"
        and executor.state.turn.priority_holder_id not in {None, CONTROLLED_PLAYER}
    ):
        holder = executor.state.turn.priority_holder_id
        if holder is None:
            break
        executor.pass_priority(holder)


def _direct_priority_window(executor: GameExecutor) -> None:
    """Pass all modeled priority without consulting strategy, resolving the stack exactly."""
    cycles = 0
    while executor.state.terminal.status == "ACTIVE":
        if executor.state.turn.priority_holder_id is None:
            return
        stack_before = bool(executor.state.stack)
        holders = _living_players(executor)
        for _ in holders:
            if executor.state.terminal.status != "ACTIVE":
                return
            holder = executor.state.turn.priority_holder_id
            if holder is None:
                return
            executor.pass_priority(holder)
        cycles += 1
        if cycles > MAX_ACTIONS_PER_PRIORITY_WINDOW:
            raise UnsupportedCapability("direct priority window exceeded bounded pass cycles")
        if not stack_before:
            return


def _resolve_required_stack(executor: GameExecutor) -> None:
    """Resolve only actual stack work in the frozen no-interaction technical path."""
    while executor.state.terminal.status == "ACTIVE" and executor.state.stack:
        _direct_priority_window(executor)


def _priority_window(
    executor: GameExecutor,
    policy: StandardPolicy,
    *,
    exploratory: "_OneLayerExplorer | None" = None,
    measurement: _GameMeasurementCapture | None = None,
) -> None:
    """Run one priority window until the controlled player passes on an empty stack."""
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
            raise UnsupportedCapability("controlled priority window exposes no legal broker action")
        standard_handle = policy.select_action(observation, actions)
        selected_handle = (
            exploratory.choose(executor, observation, actions, standard_handle)
            if exploratory is not None
            else standard_handle
        )
        selected = next(action for action in actions if action.handle == selected_handle)
        if measurement is not None:
            tracker = getattr(executor, "combo_access_tracker", None)
            if isinstance(tracker, ComboAccessTracker):
                measurement.observe_selected_action(executor, tracker, selected)
        broker.execute(int(observation["generation"]), selected_handle)
        actions_used += 1
        if actions_used > MAX_ACTIONS_PER_PRIORITY_WINDOW:
            raise UnsupportedCapability("controlled priority window exceeded bounded action count")
        if selected.kind != "PASS_PRIORITY":
            continue
        # The controlled player passed. Opponents have no modeled interaction and
        # therefore pass in turn. If a stack object resolves, P0 receives priority
        # again and the window continues. If the stack was already empty, the window ends.
        stack_before = bool(executor.state.stack)
        _auto_pass_opponents_until_control(executor)
        if executor.state.terminal.status != "ACTIVE":
            return
        if stack_before:
            continue
        return


def _cleanup_discard_ids(executor: GameExecutor, provider: Any) -> tuple[str, ...]:
    player = executor.state.players[CONTROLLED_PLAYER]
    hand_key = executor.zones.zone_key(Zone.HAND, CONTROLLED_PLAYER)
    hand_ids = tuple(executor.state.zones.get(hand_key, ()))
    excess = max(0, len(hand_ids) - player.maximum_hand_size)
    if excess == 0:
        return ()
    # Issue #62: policy-only cleanup bookkeeping must not consume engine identity
    # or RNG. The request namespace is a pure function of visible current state.
    state_digest = state_hash(executor.state)
    request_id = hashlib.sha256(
        f"phase-c-cleanup:{state_digest}:{executor.state.turn.number}".encode()
    ).hexdigest()[:24]
    handles: dict[str, str] = {
        object_id: hashlib.sha256(f"{request_id}:{object_id}".encode()).hexdigest()[:24]
        for object_id in hand_ids
    }
    candidates = tuple(
        PublicCard(
            handle=handles[object_id],
            identity=str(executor.state.objects[object_id].current_characteristics.get("name", "")),
            mana_value=int(
                executor.state.objects[object_id].current_characteristics.get("mana_value", 0)
            ),
            card_types=tuple(
                str(value)
                for value in executor.state.objects[object_id].current_characteristics.get(
                    "card_types", ()
                )
            ),
            effect_kinds=executor._strategic_effect_kinds(executor.state.objects[object_id]),
        )
        for object_id in hand_ids
    )
    selection = provider.choose_cards(
        CardSelectionRequest(
            request_id=request_id,
            actor_id=CONTROLLED_PLAYER,
            ability_id="phase-c-cleanup",
            purpose="DISCARD",
            turn_number=executor.state.turn.number,
            observation=executor._strategic_observation(CONTROLLED_PLAYER),
            candidates=candidates,
            minimum=excess,
            maximum=excess,
        )
    )
    by_handle = {handle: object_id for object_id, handle in handles.items()}
    if len(selection.selected_handles) != excess or any(
        handle not in by_handle for handle in selection.selected_handles
    ):
        raise IllegalAction("cleanup policy returned an illegal discard selection")
    return tuple(by_handle[handle] for handle in selection.selected_handles)


def _combo_evaluation(executor: GameExecutor, tracker: ComboAccessTracker) -> SearchEvaluation:
    current = tracker.observe(executor)
    immediate = any(record.legally_executable and record.full_table_kill for record in current)
    protected = any(
        record.legally_executable and record.full_table_kill and record.usable_protection
        for record in current
    )
    earliest = tracker.earliest_legal_turn()
    hand_key = executor.zones.zone_key(Zone.HAND, CONTROLLED_PLAYER)
    board = sum(
        1
        for obj in executor.state.objects.values()
        if not obj.retired and obj.zone is Zone.BATTLEFIELD and obj.controller == CONTROLLED_PLAYER
    )
    mana = sum(executor.state.players[CONTROLLED_PLAYER].mana_pool.values())
    return SearchEvaluation(
        immediate_legal_table_win=immediate,
        protected_table_win=protected,
        expected_win_turn=earliest if earliest is not None else 99,
        independent_second_lines=sum(record.legally_executable for record in current),
        cards_accessed=len(executor.state.zones.get(hand_key, ())),
        net_usable_mana=max(0, int(mana)),
        resilient_board=board,
    )


class _OneLayerExplorer:
    """One audited production decision layer under the frozen Phase B hard caps."""

    def __init__(self, policy_config_id: str, search_seed: int) -> None:
        self.policy_config_id = policy_config_id
        self.search_seed = search_seed
        self.search = BoundedExplorer()
        self.search.begin_game()
        self.records: list[ExploratoryDecisionRecord] = []
        self._divergence_seen = False

    def choose(
        self,
        executor: GameExecutor,
        observation: Mapping[str, Any],
        actions: tuple[Any, ...],
        standard_handle: str,
    ) -> str:
        root = SearchPosition(
            observation=observation,
            actions=actions,
            evaluation=SearchEvaluation(),
            player_turns_elapsed=0,
        )

        def expand(parent: SearchPosition, selected: Any, belief_seed: int) -> SearchPosition:
            del parent, belief_seed  # future random outcomes are intentionally unavailable
            clone_state = deepcopy(executor.state)
            clone = GameExecutor(clone_state, executor.seed)
            _policy, _provider, evaluator_config = _bound_policy(clone, self.policy_config_id)
            tracker = bind_combo_access_tracker(
                clone, CONTROLLED_PLAYER, evaluator_config.combo_packages
            )
            clone_broker = ActionBroker(clone, CONTROLLED_PLAYER)
            clone_observation, clone_actions = clone_broker.refresh()
            matching = next(
                (action for action in clone_actions if action.handle == selected.handle), None
            )
            if matching is None:
                raise UnsupportedCapability(
                    "exploratory successor could not reproduce a root action through the shared broker"
                )
            clone_broker.execute(int(clone_observation["generation"]), matching.handle)
            successor_broker = ActionBroker(clone, CONTROLLED_PLAYER)
            successor_observation, _ = successor_broker.refresh()
            return SearchPosition(
                observation=successor_observation,
                actions=(),  # freeze the pilot adapter to one production decision layer
                evaluation=_combo_evaluation(clone, tracker),
                player_turns_elapsed=1,
            )

        belief_seed = int.from_bytes(
            hashlib.sha256(
                f"phase-c-belief:{self.search_seed}:{executor.state.turn.number}:"
                f"{executor.state.turn.step}:{len(self.records)}".encode()
            ).digest()[:8],
            "big",
        )
        result = self.search.choose(root, belief_sample_seeds=(belief_seed,), expand=expand)
        first_divergence = result.selected_action != standard_handle and not self._divergence_seen
        self._divergence_seen = self._divergence_seen or first_divergence
        self.records.append(
            ExploratoryDecisionRecord(
                turn=executor.state.turn.number,
                phase=executor.state.turn.phase,
                step=executor.state.turn.step,
                standard_action=standard_handle,
                exploratory_action=result.selected_action,
                branches_searched=result.log.branches_searched,
                nodes_evaluated=result.log.nodes_evaluated,
                decision_layer_depth=result.log.depth_reached,
                first_divergence=first_divergence,
            )
        )
        if result.log.depth_reached != PILOT_PRODUCTION_DECISION_LAYER_DEPTH:
            raise UnsupportedCapability(
                "exploratory search did not execute exactly one production layer"
            )
        return result.selected_action


def _combat_optional_trigger_choices(
    executor: GameExecutor, policy: StandardPolicy
) -> dict[str, dict[str, Any]]:
    choices: dict[str, dict[str, Any]] = {}
    attackers = [
        obj
        for obj in executor.state.objects.values()
        if not obj.retired
        and obj.zone is Zone.BATTLEFIELD
        and obj.controller == CONTROLLED_PLAYER
        and obj.current_characteristics.get("attacking") is True
        and obj.current_characteristics.get("unblocked") is True
    ]
    for attacker in attackers:
        optional: dict[str, bool] = {}
        for permanent in executor.state.objects.values():
            if permanent.retired or permanent.zone is not Zone.BATTLEFIELD:
                continue
            if (
                permanent.attached_to_ref is None
                or permanent.attached_to_ref.object_id != attacker.object_id
            ):
                continue
            for raw_ability in permanent.current_characteristics.get("abilities", ()):
                ability = dict(raw_ability)
                if not ability.get("optional"):
                    continue
                if ability.get("trigger") != "ENCHANTED_CREATURE_DAMAGE_TO_OPPONENT":
                    continue
                effect_kind = str(dict(ability.get("effect", {})).get("kind", ""))
                optional[str(ability["ability_id"])] = policy.choose_optional_trigger(effect_kind)
        if optional:
            choices[attacker.object_id] = {"optional": optional}
    return choices


def _delayed_trigger_step_choices(executor: GameExecutor, step: str) -> dict[str, Any]:
    """Supply explicit rules-required choices for frozen delayed triggers.

    Arcane Denial's delayed trigger lets the controller of the countered spell draw
    up to two cards. In the frozen Phase C model P0 maximizes deterministic card
    access, so P0 chooses two. Opponent hidden resources and actions are outside the
    model, so an opponent chooses zero rather than injecting unmodeled hidden cards.
    The choice is recorded in the begin-step replay command.
    """
    if step != "UPKEEP":
        return {}
    per_trigger: dict[str, dict[str, Any]] = {}
    for object_id in tuple(executor.state.delayed_triggers):
        trigger = executor.state.objects.get(object_id)
        if trigger is None or trigger.retired or trigger.ceased_to_exist:
            continue
        raw_ability = trigger.current_characteristics.get("ability", {})
        if not isinstance(raw_ability, dict):
            continue
        ability = dict(raw_ability)
        if ability.get("trigger") != "NEXT_UPKEEP":
            continue
        raw_context = trigger.current_characteristics.get("trigger_context", {})
        context = dict(raw_context) if isinstance(raw_context, dict) else {}
        not_before_turn = int(context.get("not_before_turn", executor.state.turn.number))
        if executor.state.turn.number < not_before_turn:
            continue
        raw_effect = ability.get("effect", {})
        if not isinstance(raw_effect, dict):
            continue
        effect = dict(raw_effect)
        if effect.get("kind") != "ARCANE_DENIAL_DELAYED_DRAWS":
            continue
        optional_player = str(effect.get("optional_player", ""))
        if optional_player not in executor.state.players:
            raise IllegalAction("Arcane Denial delayed draw player is unavailable")
        count = 2 if optional_player == CONTROLLED_PLAYER else 0
        per_trigger[object_id] = {
            "arcane_denial_draw_count": {
                "player_id": optional_player,
                "count": count,
            }
        }
    return {"delayed_trigger_choices": per_trigger} if per_trigger else {}


def _policy_window_required(step: str, executor: GameExecutor) -> bool:
    if step in {"PRECOMBAT_MAIN", "DECLARE_ATTACKERS", "POSTCOMBAT_MAIN"}:
        return True
    if step in {"DECLARE_BLOCKERS", "COMBAT_DAMAGE", "END_COMBAT"}:
        return any(
            not obj.retired
            and obj.zone is Zone.BATTLEFIELD
            and obj.controller == CONTROLLED_PLAYER
            and obj.current_characteristics.get("attacking") is True
            for obj in executor.state.objects.values()
        ) or bool(executor.state.stack)
    return bool(executor.state.stack)


_FAILURE_BLOCKER_MAP: tuple[tuple[str, str], ...] = (
    ("INSUFFICIENT_MANA", "mana_shortage"),
    ("MANA", "mana_shortage"),
    ("PROTECTION", "protection_mana_shortage"),
    ("TIMING", "sequencing_failure"),
    ("ATTACK", "sequencing_failure"),
    ("SUMMONING", "sequencing_failure"),
    ("TARGET", "sequencing_failure"),
    ("NOT_IN_HAND", "action_density_shortage"),
    ("UNAVAILABLE", "action_density_shortage"),
    ("MISSING", "action_density_shortage"),
)


def _failure_labels_for_checkpoint(tracker: ComboAccessTracker, checkpoint: int) -> tuple[str, ...]:
    if any(
        record.turn <= checkpoint and record.legally_executable and record.full_table_kill
        for record in tracker.records
    ):
        return ()
    candidates = [record for record in tracker.records if record.turn <= checkpoint]
    if not candidates:
        return ("other_documented_cause",)
    latest_turn = max(record.turn for record in candidates)
    blockers = {
        str(blocker)
        for record in candidates
        if record.turn == latest_turn
        for blocker in record.blockers
    }
    labels: set[str] = set()
    for blocker in blockers:
        upper = blocker.upper()
        for token, label in _FAILURE_BLOCKER_MAP:
            if token in upper:
                labels.add(label)
    if not labels:
        labels.add("other_documented_cause")
    priority = (
        "mana_shortage",
        "color_shortage",
        "protection_mana_shortage",
        "action_density_shortage",
        "sequencing_failure",
        "other_documented_cause",
    )
    return tuple(label for label in priority if label in labels)


def _best_combo_snapshot(
    tracker: ComboAccessTracker, package: str, checkpoint: int
) -> ComboAccessSnapshot | None:
    values = [
        record
        for record in tracker.records
        if record.package == package and record.turn <= checkpoint
    ]
    if not values:
        return None
    return max(
        values,
        key=lambda record: (
            int(record.legally_executable and record.full_table_kill),
            int(record.legally_executable),
            int(record.sufficient_mana),
            int(record.pieces_assembled),
            record.turn,
            record.observation_index,
        ),
    )


def _drawn_card_counts(executor: GameExecutor) -> Counter[str]:
    events = executor.state.events
    kept_indexes = [
        index for index, event in enumerate(events) if event.kind == "MULLIGAN_HAND_KEPT"
    ]
    boundary = kept_indexes[-1] if kept_indexes else -1
    order = {event.event_id: index for index, event in enumerate(events)}
    counts: Counter[str] = Counter()
    for change in executor.state.zone_changes:
        if change.cause != "DRAW" or change.to_object_id is None:
            continue
        if order.get(change.event_id, -1) <= boundary:
            continue
        obj = executor.state.objects.get(change.to_object_id)
        if obj is None or obj.owner != CONTROLLED_PLAYER:
            continue
        name = str(obj.current_characteristics.get("name", ""))
        if name:
            counts[name] += 1
    return counts


def _cast_card_counts(executor: GameExecutor) -> Counter[str]:
    counts: Counter[str] = Counter()
    for action in executor.state.actions:
        if (
            action.kind != "CAST"
            or action.actor_id != CONTROLLED_PLAYER
            or not action.source_object_id
        ):
            continue
        obj = executor.state.objects.get(action.source_object_id)
        if obj is None:
            continue
        name = str(obj.current_characteristics.get("name", ""))
        if name:
            counts[name] += 1
    return counts


def _protection_names_in_final_hand(executor: GameExecutor) -> set[str]:
    protected_effects = {
        "COUNTER",
        "COUNTER_IF",
        "COUNTER_TARGETING_CONTROLLER",
        "COUNTER_UNLESS_PAY",
        "COUNTER_UNLESS_PAY_EXILE",
        "AMASS_AND_HEXPROOF",
        "PHASE_OUT",
    }
    result: set[str] = set()
    hand_key = executor.zones.zone_key(Zone.HAND, CONTROLLED_PLAYER)
    for object_id in executor.state.zones.get(hand_key, ()):
        obj = executor.state.objects[object_id]
        kinds = set(executor._strategic_effect_kinds(obj))
        if kinds.intersection(protected_effects):
            result.add(str(obj.current_characteristics.get("name", "")))
    return result


def _build_game_measurement(
    *,
    executor: GameExecutor,
    tracker: ComboAccessTracker,
    evaluator_config: Any,
    opening: tuple[OpeningHandRecord, ...],
    mode: str,
    seed: int,
    policy_config_id: str,
    capture: _GameMeasurementCapture,
    exploratory_records: tuple[ExploratoryDecisionRecord, ...],
    environment_initial_state_hash: str,
    search_seed: int | None,
    pair_id: str | None,
    paired_standard_game_index: int | None,
) -> GameMeasurement:
    checkpoints = (5, 6, 8, 10)
    checkpoint_access = {
        turn: any(
            record.turn <= turn and record.legally_executable and record.full_table_kill
            for record in tracker.records
        )
        for turn in checkpoints
    }
    failures = {
        turn: (() if checkpoint_access[turn] else _failure_labels_for_checkpoint(tracker, turn))
        for turn in checkpoints
    }
    primary = {turn: (labels[0] if labels else None) for turn, labels in failures.items()}
    earliest_table_win_turns = [
        record.turn
        for record in tracker.records
        if record.legally_executable and record.full_table_kill
    ]
    earliest = min(earliest_table_win_turns) if earliest_table_win_turns else None
    terminal = executor.state.terminal.status != "ACTIVE"
    combo_records: list[ComboMeasurement] = []
    for package in sorted(evaluator_config.combo_packages):
        for checkpoint in checkpoints:
            snapshot = _best_combo_snapshot(tracker, package, checkpoint)
            if snapshot is None:
                combo_records.append(
                    ComboMeasurement(
                        package, checkpoint, False, False, False, False, False, False, False, False
                    )
                )
                continue
            attempted = bool(
                capture.attempt_package == package
                and capture.actual_first_attempt_turn is not None
                and capture.actual_first_attempt_turn <= checkpoint
            )
            resolved = bool(attempted and terminal and executor.state.turn.number <= checkpoint)
            combo_records.append(
                ComboMeasurement(
                    package=package,
                    turn=checkpoint,
                    pieces_assembled=snapshot.pieces_assembled,
                    legally_executable=snapshot.legally_executable,
                    sufficient_mana=snapshot.sufficient_mana,
                    usable_protection=snapshot.usable_protection,
                    attempted=attempted,
                    resolved=resolved,
                    full_table_kill=resolved and snapshot.full_table_kill,
                    conditional_kill_or_takeover=snapshot.conditional_kill_or_takeover,
                )
            )

    package_cards = {
        package: set(str(card) for card in cards)
        for package, cards in evaluator_config.combo_packages.items()
    }
    combo_piece_names = set().union(*package_cards.values()) if package_cards else set()
    mana_names: set[str] = set()
    from mtg_cards.full_deck import load_full_deck_specs

    for spec in load_full_deck_specs().values():
        name = str(spec.name)
        if "Land" in tuple(spec.card_types):
            mana_names.add(name)
        if any(
            str(dict(dict(ability).get("effect", {})).get("kind", ""))
            in {"ADD_MANA", "ADD_CHOSEN_MANA"}
            for ability in spec.abilities
        ):
            mana_names.add(name)

    opening_measurements = tuple(
        OpeningHandMeasurement(
            hand_number=record.candidate_index + 1,
            nominal_size=record.nominal_size,
            card_names=record.card_names,
            kept=record.kept,
            refill_cards=record.refill_names,
            refill_changed_combo_access=any(
                name in combo_piece_names and name not in record.card_names
                for name in record.refill_names
            ),
            refill_changed_mana_access=any(
                name in mana_names and name not in record.card_names for name in record.refill_names
            ),
        )
        for record in opening
    )
    drawn = _drawn_card_counts(executor)
    cast = _cast_card_counts(executor)
    hand_key = executor.zones.zone_key(Zone.HAND, CONTROLLED_PLAYER)
    stranded_counts: Counter[str] = Counter(
        str(executor.state.objects[object_id].current_characteristics.get("name", ""))
        for object_id in executor.state.zones.get(hand_key, ())
    )
    all_names = sorted(
        set(drawn) | set(cast) | set(capture.hand_turn_counts) | set(stranded_counts)
    )
    card_records: list[CardMeasurement] = []
    for name in all_names:
        contributions = tuple(
            f"combo_access:{package}"
            for package, cards in sorted(package_cards.items())
            if name in cards
            and any(
                record.package == package and record.legally_executable
                for record in tracker.records
            )
        )
        stranded = stranded_counts[name]
        stranded_reasons = failures[10] if stranded else ()
        card_records.append(
            CardMeasurement(
                card_name=name,
                drawn=drawn[name],
                cast=cast[name],
                turns_held=capture.hand_turn_counts[name],
                stranded=stranded,
                stranded_reasons=stranded_reasons,
                cast_without_outcome_improvement=0,
                contributions=contributions,
            )
        )

    # Single exploratory executions record choice divergence diagnostics only.
    # Paired outcome comparison is constructed later from two executions sharing
    # the same environment seed; never write the same game's result into both arms.
    first_divergence = next(
        (record for record in exploratory_records if record.first_divergence), None
    )
    divergence = None

    usable_protection = int(
        any(record.legally_executable and record.usable_protection for record in tracker.records)
    )
    protection_names = _protection_names_in_final_hand(executor)
    second_line = any(
        sum(
            1
            for record in tracker.records
            if record.observation_index == observation_index
            and record.legally_executable
            and record.full_table_kill
        )
        >= 2
        for observation_index in {record.observation_index for record in tracker.records}
    )
    return GameMeasurement(
        schema_version="phase-b-game-measurement-v1",
        game_index=1,  # rewritten to the exact shard-global index by the output adapter
        seed=seed,
        mode=mode,
        policy_config_id=policy_config_id,
        opening_hands=opening_measurements,
        kept_at=opening[-1].nominal_size,
        checkpoint_table_win_access=checkpoint_access,
        failure_labels=failures,
        primary_failure=primary,
        combo_records=tuple(combo_records),
        earliest_legal_attempt_turn=earliest,
        actual_first_attempt_turn=capture.actual_first_attempt_turn,
        attempt_package=capture.attempt_package,
        attempt_timing=capture.attempt_timing,
        usable_protection_count=usable_protection,
        protection_in_hand_not_payable=bool(protection_names and not usable_protection),
        protection_category_mismatch=False,
        independent_second_line_available=second_line,
        card_records=tuple(card_records),
        divergence=divergence,
        search_decisions=tuple(asdict(record) for record in exploratory_records),
        future_information_rejections=0,
        post_result_optimization_rejections=0,
        terminal_status=executor.state.terminal.status,
        terminal_turn=(int(executor.state.turn.number) if terminal else None),
        extra={
            "environment_seed": seed,
            "environment_initial_state_hash": environment_initial_state_hash,
            "search_seed": search_seed,
            "pair_id": pair_id,
            "paired_standard_game_index": paired_standard_game_index,
            "first_decision_divergence": (
                None if first_divergence is None else asdict(first_divergence)
            ),
            "selected_actions": tuple(capture.selected_actions),
            "combo_checkpoint_blockers": {
                str(turn): {
                    package: (
                        list(snapshot.blockers)
                        if (snapshot := _best_combo_snapshot(tracker, package, turn)) is not None
                        else ["NO_OBSERVATION"]
                    )
                    for package in sorted(evaluator_config.combo_packages)
                }
                for turn in checkpoints
            },
        },
    )


def run_phase_c_game_execution(
    *,
    seed: int,
    mode: str,
    search_seed: int | None = None,
    pair_id: str | None = None,
    paired_standard_game_index: int | None = None,
    policy_config_id: str = "anchor_balanced",
    through_turn: int = 10,
    validate_fresh_replay: bool = True,
    policy_actions: bool = False,
) -> PhaseCGameExecution:
    """Execute one bounded non-pilot game through the real clean-engine path."""
    if mode not in {"STANDARD", "EXPLORATORY"}:
        raise ValueError("Phase C technical mode must be STANDARD or EXPLORATORY")
    if through_turn < 1 or through_turn > 10:
        raise ValueError("Phase C technical turn horizon must be within 1..10")
    if mode == "STANDARD" and search_seed is not None:
        raise ValueError("STANDARD execution cannot receive an exploratory search seed")
    effective_search_seed = search_seed
    if mode == "EXPLORATORY" and effective_search_seed is None:
        effective_search_seed = int.from_bytes(
            hashlib.sha256(f"phase-c-technical-search-v1:{seed}".encode()).digest()[:8],
            "big",
        )
    seed_text = f"phase-c:standard:{seed}"
    state, executor, _ = build_exact_game(seed_text, PLAYER_IDS)
    environment_initial_state_hash = state_hash(state)
    policy, provider, evaluator_config = _bound_policy(executor, policy_config_id)
    tracker = bind_combo_access_tracker(
        executor, CONTROLLED_PLAYER, evaluator_config.combo_packages
    )
    capture = _GameMeasurementCapture()

    initial_state = deepcopy(state)
    keep_index, opening = _choose_mulligan(initial_state, seed_text, policy)
    executor.league_mulligan(CONTROLLED_PLAYER, keep_index)
    opening = _finalize_refill_names(executor, opening)

    explorer = None
    if mode == "EXPLORATORY" and policy_actions:
        if effective_search_seed is None:
            raise ValueError("EXPLORATORY execution requires a search seed")
        explorer = _OneLayerExplorer(policy_config_id, effective_search_seed)
    completed_turns = 0
    for turn_number in range(1, through_turn + 1):
        if state.terminal.status != "ACTIVE":
            break
        if turn_number > 1:
            executor.start_next_controlled_turn(CONTROLLED_PLAYER)
        if state.turn.number != turn_number:
            raise UnsupportedCapability("controlled turn number diverged from Phase C horizon")
        for step in TURN_STEPS:
            if state.terminal.status != "ACTIVE":
                break
            if step == "CLEANUP":
                while True:
                    discard_ids = _cleanup_discard_ids(executor, provider)
                    executor.begin_step("CLEANUP", {"discard_ids": list(discard_ids)})
                    if not state.turn.cleanup_repeat_pending:
                        break
                    # Resolve cleanup triggers, but do not pass on an empty stack: the
                    # next cleanup iteration may require a new deterministic discard.
                    while state.stack and state.terminal.status == "ACTIVE":
                        (
                            _priority_window(
                                executor, policy, exploratory=explorer, measurement=capture
                            )
                            if policy_actions and _policy_window_required("CLEANUP", executor)
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
                    _priority_window(executor, policy, exploratory=explorer, measurement=capture)
                    if policy_actions and _policy_window_required(step, executor)
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
                    _priority_window(executor, policy, exploratory=explorer, measurement=capture)
                    if policy_actions and _policy_window_required(step, executor)
                    else _resolve_required_stack(executor)
                )
                continue
            step_choices = _delayed_trigger_step_choices(executor, step)
            executor.begin_step(step, step_choices)
            if step == "DECLARE_ATTACKERS" and not policy_actions:
                executor.declare_attackers(CONTROLLED_PLAYER, {})
            if step != "UNTAP":
                (
                    _priority_window(executor, policy, exploratory=explorer, measurement=capture)
                    if policy_actions and _policy_window_required(step, executor)
                    else _resolve_required_stack(executor)
                )
        if state.terminal.status == "ACTIVE" and state.turn.step != "CLEANUP":
            raise UnsupportedCapability("controlled turn ended before cleanup completed")
        capture.record_turn_end(executor, tracker)
        completed_turns = turn_number

    body = transcript(state, seed=seed_text)
    # Same-process replay catches state/command errors before the more expensive
    # fresh-process check and never invokes policy decision code.
    replayed = validate_replay(body)
    replay_hash = state_hash(replayed)
    fresh_hash = replay_hash
    if validate_fresh_replay:
        from mtg_runs.replay_audit import replay_in_fresh_process

        fresh_hash = replay_in_fresh_process(body, cwd=ROOT).state_hash
    earliest = {
        package: tracker.earliest_legal_turn(package)
        for package in sorted(evaluator_config.combo_packages)
    }
    checkpoints = {
        package: tracker.cumulative_checkpoint_access(package)
        for package in sorted(evaluator_config.combo_packages)
    }
    exploratory_records = tuple(explorer.records) if explorer is not None else ()
    technical = PhaseCTechnicalGame(
        schema_version="phase-c-technical-game-v2",
        mode=mode,
        seed=seed,
        environment_initial_state_hash=environment_initial_state_hash,
        search_seed=effective_search_seed,
        pair_id=pair_id,
        paired_standard_game_index=paired_standard_game_index,
        policy_config_id=policy_config_id,
        opening_hands=opening,
        controlled_turns_completed=completed_turns,
        terminal_status=state.terminal.status,
        command_count=len(state.replay_commands),
        replay_digest=str(body["digest"]),
        final_state_hash=state_hash(state),
        fresh_replay_state_hash=fresh_hash,
        combo_earliest_legal_turn=earliest,
        combo_checkpoint_access=checkpoints,
        exploratory_decisions=exploratory_records,
        exploratory_nodes_evaluated=sum(record.nodes_evaluated for record in exploratory_records),
        exploratory_decision_layer_depth=(1 if mode == "EXPLORATORY" else 0),
    )
    measurement = _build_game_measurement(
        executor=executor,
        tracker=tracker,
        evaluator_config=evaluator_config,
        opening=opening,
        mode=mode,
        seed=seed,
        policy_config_id=policy_config_id,
        capture=capture,
        exploratory_records=exploratory_records,
        environment_initial_state_hash=environment_initial_state_hash,
        search_seed=effective_search_seed,
        pair_id=pair_id,
        paired_standard_game_index=paired_standard_game_index,
    )
    return PhaseCGameExecution(
        schema_version="phase-c-game-execution-v1",
        technical_game=technical,
        measurement=measurement,
        replay_transcript=body,
    )


def run_phase_c_technical_game(
    *,
    seed: int,
    mode: str,
    policy_config_id: str = "anchor_balanced",
    through_turn: int = 10,
    validate_fresh_replay: bool = True,
    policy_actions: bool = False,
) -> PhaseCTechnicalGame:
    """Return the technical-game view of one clean-engine Phase C execution."""
    return run_phase_c_game_execution(
        seed=seed,
        mode=mode,
        policy_config_id=policy_config_id,
        through_turn=through_turn,
        validate_fresh_replay=validate_fresh_replay,
        policy_actions=policy_actions,
    ).technical_game


def run_phase_c_paired_environment_smoke(
    *, environment_seed: int = 505, search_seed: int = 606
) -> dict[str, Any]:
    """Prove paired modes start from the same environment and separate search RNG."""
    pair_id = hashlib.sha256(f"technical-pair:{environment_seed}".encode()).hexdigest()[:24]
    standard = run_phase_c_game_execution(
        seed=environment_seed,
        mode="STANDARD",
        pair_id=pair_id,
        paired_standard_game_index=1,
        through_turn=1,
        validate_fresh_replay=False,
        policy_actions=True,
    )
    exploratory = run_phase_c_game_execution(
        seed=environment_seed,
        mode="EXPLORATORY",
        search_seed=search_seed,
        pair_id=pair_id,
        paired_standard_game_index=1,
        through_turn=1,
        validate_fresh_replay=False,
        policy_actions=True,
    )
    if (
        standard.technical_game.environment_initial_state_hash
        != exploratory.technical_game.environment_initial_state_hash
    ):
        raise UnsupportedCapability("paired modes did not share the same environment state")
    if standard.technical_game.opening_hands != exploratory.technical_game.opening_hands:
        raise UnsupportedCapability("paired modes did not share the same opening environment")
    if standard.technical_game.search_seed is not None:
        raise UnsupportedCapability("standard mode consumed a search seed")
    if exploratory.technical_game.search_seed != search_seed:
        raise UnsupportedCapability("exploratory mode did not bind its separate search seed")
    return {
        "status": "PASS",
        "pair_id": pair_id,
        "environment_seed": environment_seed,
        "search_seed": search_seed,
        "environment_initial_state_hash": standard.technical_game.environment_initial_state_hash,
        "opening_environment_equal": True,
        "standard_search_seed": None,
        "exploratory_search_seed": search_seed,
    }


def run_phase_c_combat_smoke(*, seed: int = 303) -> dict[str, Any]:
    """Prove legal multiplayer no-blocker combat through broker and executor."""
    from mtg_cards.full_deck import load_full_deck_specs
    from mtg_kernel.factory import add_card, new_game

    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    seed_text = f"phase-c-combat:{seed}"
    state, executor = new_game(PLAYER_IDS, seed_text)
    state.turn.number = 2
    state.turn.phase = "COMBAT"
    state.turn.step = "BEGIN_COMBAT"
    state.turn.active_player_id = CONTROLLED_PLAYER
    state.turn.priority_holder_id = CONTROLLED_PLAYER
    malcolm = add_card(
        executor,
        specs["Malcolm, Keen-Eyed Navigator"],
        Zone.BATTLEFIELD,
        owner=CONTROLLED_PLAYER,
        commander=True,
    )
    if malcolm.permanent_status is not None:
        malcolm.permanent_status["controller_since_turn"] = "1"
    executor.begin_step("DECLARE_ATTACKERS")
    broker = ActionBroker(executor, CONTROLLED_PLAYER)
    observation, actions = broker.refresh()
    attack = next(
        action
        for action in actions
        if action.kind == "DECLARE_ATTACKERS"
        and action.identity is None
        and action.metadata.get("attacker_count") == 1
        and any(item.get("opponent") == "P1" for item in action.metadata.get("assignments", ()))
    )
    broker.execute(int(observation["generation"]), attack.handle)
    executor.begin_step("DECLARE_BLOCKERS")
    executor.declare_no_blockers()
    executor.begin_step("COMBAT_DAMAGE")
    executor.resolve_no_blocker_combat_damage()
    _direct_priority_window(executor)
    body = transcript(state, seed=seed_text)
    replayed = validate_replay(body)
    if state_hash(replayed) != state_hash(state):
        raise UnsupportedCapability("combat smoke replay diverged")
    commander_instance = malcolm.component_card_instance_ids[0]
    damage = state.commander_damage.get(commander_instance, {}).get("P1", 0)
    if state.players["P1"].life != 38 or damage != 2:
        raise UnsupportedCapability("combat smoke did not apply Malcolm combat damage exactly")
    if not any(
        obj.zone is Zone.STACK
        and obj.current_characteristics.get("ability", {}).get("ability_id")
        == "malcolm:pirate-damage"
        for obj in state.objects.values()
        if not obj.retired
    ) and not any(event.kind == "TREASURE_CREATED" for event in state.events):
        # The trigger may already have resolved during the direct priority cycle.
        raise UnsupportedCapability(
            "combat smoke did not preserve Malcolm damage trigger causality"
        )
    return {
        "status": "PASS",
        "attacker": "Malcolm, Keen-Eyed Navigator",
        "defender": "P1",
        "life_after": state.players["P1"].life,
        "commander_damage": damage,
        "replay_digest": body["digest"],
        "final_state_hash": state_hash(state),
        "broker_action_kind": attack.kind,
    }


def run_phase_c_exploratory_smoke(*, seed: int = 404) -> dict[str, Any]:
    """Execute one real successor layer through the shared broker/executor."""
    seed_text = f"phase-c-exploratory-smoke:{seed}"
    state, executor, _ = build_exact_game(seed_text, PLAYER_IDS)
    policy, _provider, evaluator_config = _bound_policy(executor, "anchor_balanced")
    bind_combo_access_tracker(executor, CONTROLLED_PLAYER, evaluator_config.combo_packages)
    executor.league_mulligan(CONTROLLED_PLAYER, 0)
    executor.begin_step("PRECOMBAT_MAIN")
    broker = ActionBroker(executor, CONTROLLED_PLAYER)
    observation, actions = broker.refresh()
    standard = policy.select_action(observation, actions)
    explorer = _OneLayerExplorer("anchor_balanced", seed)
    selected = explorer.choose(executor, observation, actions, standard)
    broker.execute(int(observation["generation"]), selected)
    if not explorer.records:
        raise UnsupportedCapability("exploratory smoke produced no decision record")
    record = explorer.records[-1]
    if record.decision_layer_depth != 1 or record.nodes_evaluated < 1:
        raise UnsupportedCapability(
            "exploratory smoke did not execute exactly one production layer"
        )
    body = transcript(state, seed=seed_text)
    replayed = validate_replay(body)
    if state_hash(replayed) != state_hash(state):
        raise UnsupportedCapability("exploratory selected action did not replay exactly")
    return {
        "status": "PASS",
        "standard_action": standard,
        "selected_action": selected,
        "branches_searched": record.branches_searched,
        "nodes_evaluated": record.nodes_evaluated,
        "production_decision_layer_depth": record.decision_layer_depth,
        "game_nodes_used": explorer.search.game_nodes_used,
        "first_divergence": record.first_divergence,
        "replay_digest": body["digest"],
    }


def technical_game_digest(game: PhaseCTechnicalGame) -> str:
    return hashlib.sha256(_canonical(game.to_dict())).hexdigest()


__all__ = [
    "CONTROLLED_PLAYER",
    "OpeningHandRecord",
    "ExploratoryDecisionRecord",
    "PhaseCGameExecution",
    "PhaseCTechnicalGame",
    "PILOT_PRODUCTION_DECISION_LAYER_DEPTH",
    "run_phase_c_game_execution",
    "run_phase_c_technical_game",
    "run_phase_c_combat_smoke",
    "run_phase_c_exploratory_smoke",
    "technical_game_digest",
]
