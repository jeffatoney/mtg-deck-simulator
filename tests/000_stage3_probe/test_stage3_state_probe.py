from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from mtg_kernel.engine import GameExecutor
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import Zone
from mtg_kernel.replay import transcript, validate_replay
from mtg_measure.combo_access import ComboAccessTracker
from mtg_policy.broker import ActionBroker
from mtg_policy.public_actions import policy_action_view
from mtg_policy.standard import StandardPolicy
from mtg_runs.phase_c_runner import run_phase_c_game_execution
from mtg_runs.replay_audit import replay_in_fresh_process

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = (
    ROOT
    / "docs/audit/phase-c-postpilot/evidence/"
    "pr100-glint-horn-repaired-behavior-4d15c185.zip"
)
CONTRACT_PATH = ROOT / "tests/phase_c/test_malcolm_glint_horn_witness_contract.py"
GLINT = "Glint-Horn Buccaneer"
PACKAGE = "malcolm_glint_horn"
MEMBERS = {
    "repaired-391": ("repaired-391730338978874520.json", 391730338978874520),
    "legacy-391": ("legacy-391730338978874520.json", 391730338978874520),
    "legacy-101": ("legacy-101.json", 101),
    "repaired-101-control": ("repaired-101.json", 101),
}


def _load_contract() -> ModuleType:
    spec = importlib.util.spec_from_file_location("stage3_witness_contract", CONTRACT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_payloads() -> dict[str, dict[str, Any]]:
    with zipfile.ZipFile(ARCHIVE) as bundle:
        return {
            label: json.loads(bundle.read(member))
            for label, (member, _seed) in MEMBERS.items()
        }


def _capture_exact_archive_states(
    monkeypatch: pytest.MonkeyPatch,
    payloads: dict[str, dict[str, Any]],
) -> tuple[dict[str, tuple[Any, str, dict[str, Any]]], dict[str, Any]]:
    captured: dict[str, tuple[Any, str, dict[str, Any]]] = {}
    executions: dict[str, Any] = {}
    cursors = {label: 0 for label in MEMBERS}
    current: dict[str, Any] = {"label": "", "pending": None}
    original_observe = ComboAccessTracker.observe
    original_select = StandardPolicy.select_action
    original_execute = ActionBroker.execute

    def wrapped_observe(self: ComboAccessTracker, executor: Any) -> tuple[Any, ...]:
        result = original_observe(self, executor)
        label = str(current["label"])
        if label and label not in captured:
            snapshot = next(
                (
                    item
                    for item in result
                    if item.package == PACKAGE and item.legally_executable
                ),
                None,
            )
            if snapshot is not None:
                captured[label] = (
                    deepcopy(executor.state),
                    str(executor.seed),
                    asdict(snapshot),
                )
        return result

    def wrapped_select(
        self: StandardPolicy,
        observation: dict[str, Any],
        actions: tuple[Any, ...],
    ) -> str:
        del self, observation
        label = str(current["label"])
        if not label:
            return original_select(self, observation, actions)
        decisions = payloads[label]["decisions"]
        index = cursors[label]
        assert index < len(decisions), (label, index, len(decisions))
        decision = decisions[index]
        selected = decision["actual_selected_public_action"]
        expected_key = str(selected["public_action_key"])
        matching = [
            action
            for action in actions
            if policy_action_view(action).key.canonical_json == expected_key
        ]
        assert matching, (label, index, expected_key)
        archived_handle = str(selected["internal_opaque_handle"])
        assert any(action.handle == archived_handle for action in matching), (
            label,
            index,
            archived_handle,
            tuple(action.handle for action in matching),
        )
        current["pending"] = (label, index, archived_handle)
        return archived_handle

    def wrapped_execute(self: ActionBroker, generation: int, handle: str) -> None:
        pending = current["pending"]
        assert pending is not None
        label, index, expected_handle = pending
        assert handle == expected_handle
        original_execute(self, generation, handle)
        expected_hash = payloads[label]["decisions"][index]["post_decision_full_state_hash"]
        assert state_hash(self.executor.state) == expected_hash, (label, index)
        cursors[label] += 1
        current["pending"] = None

    with monkeypatch.context() as patch:
        patch.setattr(ComboAccessTracker, "observe", wrapped_observe)
        patch.setattr(StandardPolicy, "select_action", wrapped_select)
        patch.setattr(ActionBroker, "execute", wrapped_execute)
        for label, (_member, seed) in MEMBERS.items():
            current["label"] = label
            current["pending"] = None
            executions[label] = run_phase_c_game_execution(
                seed=seed,
                mode="STANDARD",
                through_turn=10,
                validate_fresh_replay=True,
                policy_actions=True,
            )
            assert current["pending"] is None
            assert cursors[label] == len(payloads[label]["decisions"])
        current["label"] = ""
    return captured, executions


def _stack_facts(state: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for object_id in state.stack:
        obj = state.objects[object_id]
        source = state.objects.get(obj.source_object_id) if obj.source_object_id else None
        ability = obj.current_characteristics.get("ability", {})
        result.append(
            {
                "object_kind": str(obj.object_kind.value),
                "source_identity": (
                    str(source.current_characteristics.get("name", "")) if source else None
                ),
                "ability_id": ability.get("ability_id") if isinstance(ability, dict) else None,
                "effect_kind": (
                    dict(ability.get("effect", {})).get("kind")
                    if isinstance(ability, dict)
                    else None
                ),
            }
        )
    return result


def _state_facts(state: Any, seed: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    turn = int(state.turn.number)
    battlefield: list[dict[str, Any]] = []
    untapped_sources: list[str] = []
    for obj in state.objects.values():
        if obj.retired or obj.ceased_to_exist or obj.zone is not Zone.BATTLEFIELD:
            continue
        status = obj.permanent_status or {}
        name = str(obj.current_characteristics.get("name", ""))
        keywords = sorted(str(value) for value in obj.current_characteristics.get("keywords", ()))
        card_types = sorted(
            str(value) for value in obj.current_characteristics.get("card_types", ())
        )
        since = status.get("controller_since_turn")
        creature = "Creature" in card_types
        summoning_sick = bool(
            creature
            and "Haste" not in keywords
            and since is not None
            and int(since) >= turn
        )
        battlefield.append(
            {
                "identity": name,
                "controller": obj.controller,
                "card_types": card_types,
                "keywords": keywords,
                "tapped": status.get("tap") == "TAPPED",
                "attacking": obj.current_characteristics.get("attacking") is True,
                "unblocked": obj.current_characteristics.get("unblocked") is True,
                "controller_since_turn": since,
                "summoning_sick": summoning_sick,
            }
        )
        if obj.controller == "P0" and status.get("tap") == "UNTAPPED":
            if any(ability.get("mana_ability") for ability in obj.current_characteristics.get("abilities", ())):
                untapped_sources.append(name)

    hand_key = f"{Zone.HAND.value}:P0"
    library_key = f"{Zone.LIBRARY.value}:P0"
    hand = sorted(
        str(state.objects[object_id].current_characteristics.get("name", ""))
        for object_id in state.zones.get(hand_key, ())
    )
    executor = GameExecutor(deepcopy(state), seed)
    broker = ActionBroker(executor, "P0")
    _observation, actions = broker.refresh()
    views = [policy_action_view(action) for action in actions]
    glint_candidates = [
        {
            "kind": view.kind,
            "identity": view.identity,
            "ability_id": view.metadata.get("ability_id"),
            "discard_cards": view.metadata.get("discard_cards"),
            "public_action_key": view.key.canonical_json,
        }
        for view in views
        if view.identity == GLINT
    ]
    return {
        "private_state_hash": state_hash(state),
        "turn": turn,
        "phase": str(state.turn.phase),
        "step": str(state.turn.step),
        "priority_holder": state.turn.priority_holder_id,
        "stack": _stack_facts(state),
        "battlefield": sorted(
            battlefield,
            key=lambda item: (str(item["controller"]), str(item["identity"])),
        ),
        "p0_hand": hand,
        "p0_mana_pool": dict(sorted(state.players["P0"].mana_pool.items())),
        "untapped_mana_sources": sorted(untapped_sources),
        "treasure_count": sum(
            item["controller"] == "P0" and item["identity"] == "Treasure"
            for item in battlefield
        ),
        "untapped_treasure_count": sum(
            item["controller"] == "P0"
            and item["identity"] == "Treasure"
            and not item["tapped"]
            for item in battlefield
        ),
        "library_size": len(state.zones.get(library_key, ())),
        "opponents": {
            player_id: {"life": int(player.life), "in_game": bool(player.in_game)}
            for player_id, player in sorted(state.players.items())
            if player_id != "P0"
        },
        "discardable_card_count": len(hand),
        "tracker_snapshot": snapshot,
        "broker_action_count": len(views),
        "broker_public_equivalence_class_count": len({view.key for view in views}),
        "broker_kind_counts": dict(sorted(Counter(view.kind for view in views).items())),
        "broker_identity_counts": dict(
            sorted(Counter(str(view.identity) for view in views).items())
        ),
        "glint_candidates": glint_candidates,
    }


def _step_facts(step: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": step["kind"],
        "identity": step["identity"],
        "metadata": step["metadata"],
        "public_action_key": step["public_action_key"],
        "pre_state_hash_private": step["pre_state_hash_private"],
        "post_state_hash_private": step["post_state_hash_private"],
    }


def test_emit_stage3_state_and_witness_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = _load_contract()
    payloads = _load_payloads()
    captured, executions = _capture_exact_archive_states(monkeypatch, payloads)
    assert "repaired-101-control" not in captured

    result: dict[str, Any] = {
        "states": {},
        "witnesses": {},
        "trajectory_measurements": {},
        "archive_outcomes": {
            label: payload["summary"]["outcome"] for label, payload in payloads.items()
        },
    }
    for label, execution in executions.items():
        measurement = asdict(execution.measurement)
        result["trajectory_measurements"][label] = {
            "terminal_status": execution.technical_game.terminal_status,
            "controlled_turns_completed": execution.technical_game.controlled_turns_completed,
            "combo_earliest_legal_turn": execution.technical_game.combo_earliest_legal_turn,
            "combo_checkpoint_access": execution.technical_game.combo_checkpoint_access,
            "checkpoint_table_win_access": measurement.get("checkpoint_table_win_access"),
            "actual_first_attempt_turn": measurement.get("actual_first_attempt_turn"),
            "attempt_package": measurement.get("attempt_package"),
            "attempt_timing": measurement.get("attempt_timing"),
        }

    for label in ("repaired-391", "legacy-391", "legacy-101"):
        state, seed, snapshot = captured[label]
        result["states"][label] = _state_facts(state, seed, snapshot)
        witness, steps = contract._produce_witness(state, seed)
        body = transcript(witness.state, seed=seed)
        same_process = validate_replay(body)
        fresh = replay_in_fresh_process(body, cwd=ROOT)
        result["witnesses"][label] = {
            "terminal_status": witness.state.terminal.status,
            "final_state_hash": state_hash(witness.state),
            "same_process_state_hash": state_hash(same_process),
            "fresh_replay_state_hash": fresh.state_hash,
            "glint_activation_count": sum(
                step["kind"] == "ACTIVATE" and step["identity"] == GLINT
                for step in steps
            ),
            "treasure_activation_count": sum(step["identity"] == "Treasure" for step in steps),
            "steps": [_step_facts(step) for step in steps],
        }

    pytest.exit(
        "STAGE3_STATE_PROBE="
        + json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
        returncode=1,
    )
