from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict
from typing import Any

import pytest

from mtg_kernel.engine import GameExecutor
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import Zone
from mtg_measure.combo_access import ComboAccessTracker, bind_combo_access_tracker
from mtg_policy.broker import ActionBroker
from mtg_policy.public_actions import policy_action_view
from mtg_policy.standard import StandardPolicy
from mtg_runs.phase_c_runner import _bound_policy, run_phase_c_game_execution
from tests.phase_c import test_malcolm_glint_horn_witness_contract as contract


class _Captured(RuntimeError):
    pass


def _capture(label: str, seed: int, *, legacy: bool) -> tuple[Any, str, dict[str, Any]]:
    captured: dict[str, Any] = {}
    patch = pytest.MonkeyPatch()
    original_observe = ComboAccessTracker.observe
    original_select = StandardPolicy.select_action

    def observe(self: ComboAccessTracker, executor: Any) -> tuple[Any, ...]:
        result = original_observe(self, executor)
        snapshot = next(
            (
                item
                for item in result
                if item.package == "malcolm_glint_horn" and item.legally_executable
            ),
            None,
        )
        if snapshot is not None:
            captured["state"] = deepcopy(executor.state)
            captured["seed"] = str(executor.seed)
            captured["snapshot"] = asdict(snapshot)
            raise _Captured(label)
        return result

    def select(
        self: StandardPolicy,
        observation: dict[str, Any],
        actions: tuple[Any, ...],
    ) -> str:
        if legacy:
            return contract._historical_select(self, observation, actions)
        return original_select(self, observation, actions)

    patch.setattr(ComboAccessTracker, "observe", observe)
    patch.setattr(StandardPolicy, "select_action", select)
    try:
        with pytest.raises(_Captured):
            run_phase_c_game_execution(
                seed=seed,
                mode="STANDARD",
                through_turn=10,
                validate_fresh_replay=False,
                policy_actions=True,
            )
    finally:
        patch.undo()
    return captured["state"], captured["seed"], captured["snapshot"]


def _facts(state: Any, snapshot: dict[str, Any]) -> dict[str, Any]:
    battlefield = []
    untapped_mana_sources = []
    for obj in state.objects.values():
        if obj.retired or obj.ceased_to_exist or obj.zone is not Zone.BATTLEFIELD:
            continue
        name = str(obj.current_characteristics.get("name", ""))
        status = obj.permanent_status or {}
        battlefield.append(
            {
                "identity": name,
                "controller": obj.controller,
                "tap_status": status.get("tap"),
                "attacking": obj.current_characteristics.get("attacking") is True,
                "controller_since_turn": status.get("controller_since_turn"),
                "keywords": sorted(
                    str(value) for value in obj.current_characteristics.get("keywords", ())
                ),
            }
        )
        if obj.controller == "P0" and status.get("tap") == "UNTAPPED":
            card_types = set(str(value) for value in obj.current_characteristics.get("card_types", ()))
            mana_ability = any(
                isinstance(ability, dict) and bool(ability.get("mana_ability"))
                for ability in obj.current_characteristics.get("abilities", ())
            )
            if "Land" in card_types or mana_ability or name == "Treasure":
                untapped_mana_sources.append(name)
    hand_key = f"{Zone.HAND.value}:P0"
    library_key = f"{Zone.LIBRARY.value}:P0"
    hand = [
        str(state.objects[object_id].current_characteristics.get("name", ""))
        for object_id in state.zones.get(hand_key, ())
    ]
    stack = []
    for object_id in state.stack:
        obj = state.objects[object_id]
        source = state.objects.get(obj.source_object_id) if obj.source_object_id else None
        raw_ability = obj.current_characteristics.get("ability", {})
        stack.append(
            {
                "kind": str(obj.object_kind.value),
                "source_identity": (
                    str(source.current_characteristics.get("name", "")) if source else None
                ),
                "ability_id": raw_ability.get("ability_id") if isinstance(raw_ability, dict) else None,
            }
        )
    glint = next(
        (
            item
            for item in battlefield
            if item["controller"] == "P0" and item["identity"] == contract.GLINT
        ),
        None,
    )
    return {
        "private_state_hash": state_hash(state),
        "turn": int(state.turn.number),
        "phase": str(state.turn.phase),
        "step": str(state.turn.step),
        "priority_holder": state.turn.priority_holder_id,
        "stack": stack,
        "battlefield": sorted(
            battlefield,
            key=lambda item: (str(item["controller"]), str(item["identity"])),
        ),
        "p0_hand": hand,
        "p0_mana_pool": {key: int(value) for key, value in state.players["P0"].mana_pool.items()},
        "p0_untapped_mana_sources": sorted(untapped_mana_sources),
        "p0_treasure_count": sum(
            item["controller"] == "P0" and item["identity"] == "Treasure"
            for item in battlefield
        ),
        "p0_library_size": len(state.zones.get(library_key, ())),
        "opponent_life_totals": {
            player_id: int(player.life)
            for player_id, player in sorted(state.players.items())
            if player_id != "P0" and player.in_game
        },
        "glint_horn_status": glint,
        "discardable_card_count": len(hand),
        "tracker_snapshot": snapshot,
    }


def _menu(state: Any, seed_text: str, *, legacy: bool) -> dict[str, Any]:
    executor = GameExecutor(deepcopy(state), seed_text)
    policy, _provider, evaluator = _bound_policy(executor, "anchor_balanced")
    bind_combo_access_tracker(executor, "P0", evaluator.combo_packages)
    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()
    handle = (
        contract._historical_select(policy, observation, actions)
        if legacy
        else policy.select_action(observation, actions)
    )
    selected = next(action for action in actions if action.handle == handle)
    selected_view = policy_action_view(selected)
    classes: dict[str, dict[str, Any]] = {}
    for action in actions:
        view = policy_action_view(action)
        classes.setdefault(
            view.key.canonical_json,
            {
                "kind": view.kind,
                "identity": view.identity,
                "metadata": json.loads(view.key.canonical_json)["metadata"],
                "tags": list(view.tags),
                "score_prefix": list(contract._substantive_prefix(policy, observation, action)),
            },
        )
    return {
        "class_count": len(classes),
        "classes": [classes[key] for key in sorted(classes)],
        "selected": {
            "kind": selected_view.kind,
            "identity": selected_view.identity,
            "metadata": json.loads(selected_view.key.canonical_json)["metadata"],
            "score_prefix": list(contract._substantive_prefix(policy, observation, selected)),
        },
    }


def test_stage3_final_state_extract() -> None:
    positives: dict[str, Any] = {}
    for label, seed, legacy in (
        ("repaired-391", 391730338978874520, False),
        ("legacy-391", 391730338978874520, True),
        ("legacy-101", 101, True),
    ):
        state, seed_text, snapshot = _capture(label, seed, legacy=legacy)
        witness, steps = contract._produce_witness(state, seed_text)
        positives[label] = {
            "state": _facts(state, snapshot),
            "menu": _menu(state, seed_text, legacy=legacy),
            "witness": {
                "terminal_status": witness.state.terminal.status,
                "winners": list(witness.state.terminal.winners),
                "losers": list(witness.state.terminal.losers),
                "final_private_state_hash": state_hash(witness.state),
                "steps": steps,
            },
        }
    negative = run_phase_c_game_execution(
        seed=101,
        mode="STANDARD",
        through_turn=10,
        validate_fresh_replay=True,
        policy_actions=True,
    )
    payload = {
        "schema_version": "pr100-stage3-final-state-extract-v1",
        "positive": positives,
        "negative_repaired_101": {
            "terminal_status": negative.technical_game.terminal_status,
            "controlled_turns_completed": negative.technical_game.controlled_turns_completed,
            "earliest_legal_turn": negative.technical_game.combo_earliest_legal_turn[
                "malcolm_glint_horn"
            ],
            "checkpoint_legal_access": negative.technical_game.combo_checkpoint_access[
                "malcolm_glint_horn"
            ],
            "checkpoint_table_win_access": dict(
                negative.measurement.checkpoint_table_win_access
            ),
            "actual_first_attempt_turn": negative.measurement.actual_first_attempt_turn,
            "fresh_replay_equal": (
                negative.technical_game.final_state_hash
                == negative.technical_game.fresh_replay_state_hash
            ),
        },
    }
    pytest.exit(
        "STAGE3_FINAL_STATE_EXTRACT="
        + json.dumps(payload, sort_keys=True, separators=(",", ":")),
        returncode=1,
    )
