from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from mtg_kernel.hashing import state_hash
from mtg_kernel.models import Zone
from mtg_measure.combo_access import ComboAccessTracker
from mtg_policy.broker import ActionBroker
from mtg_policy.public_actions import policy_action_view
from mtg_policy.standard import StandardPolicy
from mtg_runs.phase_c_runner import run_phase_c_game_execution

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / (
    "docs/audit/phase-c-postpilot/evidence/"
    "pr100-glint-horn-repaired-behavior-4d15c185.zip"
)
CONTRACT = ROOT / "tests/phase_c/test_malcolm_glint_horn_witness_contract.py"
PACKAGE = "malcolm_glint_horn"
MEMBERS = {
    "legacy-101": ("legacy-101.json", 101),
    "legacy-391": ("legacy-391730338978874520.json", 391730338978874520),
    "repaired-101": ("repaired-101.json", 101),
    "repaired-391": ("repaired-391730338978874520.json", 391730338978874520),
}


def _contract() -> ModuleType:
    spec = importlib.util.spec_from_file_location("stage3_contract", CONTRACT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _payloads() -> dict[str, dict[str, Any]]:
    with zipfile.ZipFile(ARCHIVE) as bundle:
        return {
            label: json.loads(bundle.read(member))
            for label, (member, _seed) in MEMBERS.items()
        }


def _facts(state: Any, snapshot: dict[str, Any]) -> dict[str, Any]:
    battlefield = []
    untapped_sources = []
    for obj in state.objects.values():
        if obj.retired or obj.ceased_to_exist or obj.zone is not Zone.BATTLEFIELD:
            continue
        status = obj.permanent_status or {}
        name = str(obj.current_characteristics.get("name", ""))
        abilities = obj.current_characteristics.get("abilities", ())
        battlefield.append(
            {
                "identity": name,
                "controller": obj.controller,
                "tapped": status.get("tap") == "TAPPED",
                "attacking": obj.current_characteristics.get("attacking") is True,
                "unblocked": obj.current_characteristics.get("unblocked") is True,
                "keywords": sorted(obj.current_characteristics.get("keywords", ())),
                "controller_since_turn": status.get("controller_since_turn"),
            }
        )
        if (
            obj.controller == "P0"
            and status.get("tap") == "UNTAPPED"
            and any(ability.get("mana_ability") for ability in abilities)
        ):
            untapped_sources.append(name)
    hand_key = f"{Zone.HAND.value}:P0"
    library_key = f"{Zone.LIBRARY.value}:P0"
    hand = sorted(
        str(state.objects[object_id].current_characteristics.get("name", ""))
        for object_id in state.zones.get(hand_key, ())
    )
    return {
        "state_hash_private": state_hash(state),
        "turn": state.turn.number,
        "phase": state.turn.phase,
        "step": state.turn.step,
        "priority_holder": state.turn.priority_holder_id,
        "stack_size": len(state.stack),
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
        "library_size": len(state.zones.get(library_key, ())),
        "opponent_life": {
            player_id: player.life
            for player_id, player in sorted(state.players.items())
            if player_id != "P0"
        },
        "discardable_card_count": len(hand),
        "tracker_snapshot": snapshot,
    }


def test_emit_exact_stage3_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    payloads = _payloads()
    contract = _contract()
    cursors = {label: 0 for label in MEMBERS}
    current: dict[str, Any] = {"label": "", "pending": None}
    captured: dict[str, tuple[Any, str, dict[str, Any]]] = {}
    executions: dict[str, Any] = {}
    original_observe = ComboAccessTracker.observe
    original_execute = ActionBroker.execute

    def observe(self: ComboAccessTracker, executor: Any) -> tuple[Any, ...]:
        result = original_observe(self, executor)
        label = str(current["label"])
        if label not in captured:
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

    def select(
        self: StandardPolicy,
        observation: dict[str, Any],
        actions: tuple[Any, ...],
    ) -> str:
        del self, observation
        label = str(current["label"])
        index = cursors[label]
        selected = payloads[label]["decisions"][index][
            "actual_selected_public_action"
        ]
        key = str(selected["public_action_key"])
        handle = str(selected["internal_opaque_handle"])
        matches = [
            action
            for action in actions
            if policy_action_view(action).key.canonical_json == key
        ]
        assert any(action.handle == handle for action in matches), (label, index)
        current["pending"] = (label, index, handle)
        return handle

    def execute(self: ActionBroker, generation: int, handle: str) -> None:
        pending = current["pending"]
        assert pending is not None
        label, index, expected_handle = pending
        assert handle == expected_handle
        original_execute(self, generation, handle)
        expected = payloads[label]["decisions"][index][
            "post_decision_full_state_hash"
        ]
        assert state_hash(self.executor.state) == expected, (label, index)
        cursors[label] += 1
        current["pending"] = None

    with monkeypatch.context() as patch:
        patch.setattr(ComboAccessTracker, "observe", observe)
        patch.setattr(StandardPolicy, "select_action", select)
        patch.setattr(ActionBroker, "execute", execute)
        for label, (_member, seed) in MEMBERS.items():
            current["label"] = label
            executions[label] = run_phase_c_game_execution(
                seed=seed,
                mode="STANDARD",
                through_turn=10,
                validate_fresh_replay=True,
                policy_actions=True,
            )
            assert cursors[label] == len(payloads[label]["decisions"])
    assert "repaired-101" not in captured

    output: dict[str, Any] = {"states": {}, "witnesses": {}, "measurements": {}}
    for label, execution in executions.items():
        output["measurements"][label] = {
            "terminal_status": execution.technical_game.terminal_status,
            "earliest_legal": execution.technical_game.combo_earliest_legal_turn,
            "technical_checkpoints": execution.technical_game.combo_checkpoint_access,
            "table_win_checkpoints": execution.measurement.checkpoint_table_win_access,
            "attempt_turn": execution.measurement.actual_first_attempt_turn,
            "attempt_package": execution.measurement.attempt_package,
            "attempt_timing": execution.measurement.attempt_timing,
        }
    for label in ("legacy-101", "legacy-391", "repaired-391"):
        state, seed, snapshot = captured[label]
        output["states"][label] = _facts(state, snapshot)
        witness, steps = contract._produce_witness(state, seed)
        output["witnesses"][label] = {
            "terminal_status": witness.state.terminal.status,
            "final_state_hash": state_hash(witness.state),
            "action_count": len(steps),
            "glint_activations": sum(
                step["identity"] == "Glint-Horn Buccaneer" for step in steps
            ),
            "treasure_activations": sum(
                step["identity"] == "Treasure" for step in steps
            ),
            "first_action": {
                "kind": steps[0]["kind"],
                "identity": steps[0]["identity"],
                "metadata": steps[0]["metadata"],
                "public_action_key": steps[0]["public_action_key"],
            },
        }
    pytest.exit(
        "STAGE3_PROBE="
        + json.dumps(output, sort_keys=True, separators=(",", ":")),
        returncode=1,
    )
