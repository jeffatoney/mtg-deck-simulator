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

from mtg_kernel.engine import GameExecutor
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import Zone
from mtg_measure.combo_access import ComboAccessTracker, bind_combo_access_tracker
from mtg_policy.broker import ActionBroker
from mtg_policy.public_actions import policy_action_view
from mtg_policy.standard import StandardPolicy
from mtg_runs.phase_c_runner import _bound_policy, run_phase_c_game_execution


ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = (
    ROOT
    / "docs/audit/phase-c-postpilot/evidence/"
    "pr100-glint-horn-repaired-behavior-4d15c185.zip"
)
CONTRACT = ROOT / "tests/phase_c/test_malcolm_glint_horn_witness_contract.py"
GLINT = "Glint-Horn Buccaneer"
MALCOLM = "Malcolm, Keen-Eyed Navigator"
PACKAGES = {GLINT, MALCOLM}


def _load_contract() -> ModuleType:
    spec = importlib.util.spec_from_file_location("stage3_contract", CONTRACT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


contract = _load_contract()


class _FirstAccessCaptured(RuntimeError):
    pass


def _capture_first_access(
    label: str,
    seed: int,
    *,
    legacy: bool,
) -> tuple[Any, str, dict[str, Any]]:
    captured: dict[str, Any] = {}
    monkeypatch = pytest.MonkeyPatch()
    original_observe = ComboAccessTracker.observe
    original_select = StandardPolicy.select_action

    def wrapped_observe(
        self: ComboAccessTracker,
        executor: Any,
    ) -> tuple[Any, ...]:
        result = original_observe(self, executor)
        snapshot = next(
            (
                item
                for item in result
                if item.package == "malcolm_glint_horn"
                and item.legally_executable
            ),
            None,
        )
        if snapshot is not None:
            captured["state"] = deepcopy(executor.state)
            captured["seed"] = str(executor.seed)
            captured["snapshot"] = asdict(snapshot)
            raise _FirstAccessCaptured(label)
        return result

    def wrapped_select(
        self: StandardPolicy,
        observation: dict[str, Any],
        actions: tuple[Any, ...],
    ) -> str:
        if legacy:
            return contract._historical_select(self, observation, actions)
        return original_select(self, observation, actions)

    monkeypatch.setattr(ComboAccessTracker, "observe", wrapped_observe)
    monkeypatch.setattr(StandardPolicy, "select_action", wrapped_select)
    try:
        with pytest.raises(_FirstAccessCaptured):
            run_phase_c_game_execution(
                seed=seed,
                mode="STANDARD",
                through_turn=10,
                validate_fresh_replay=False,
                policy_actions=True,
            )
    finally:
        monkeypatch.undo()

    return captured["state"], captured["seed"], captured["snapshot"]


def _object_name(state: Any, object_id: str) -> str:
    obj = state.objects[object_id]
    return str(obj.current_characteristics.get("name", ""))


def _zone_names(state: Any, zone: Zone, player_id: str) -> list[str]:
    if zone is Zone.BATTLEFIELD:
        return sorted(
            str(obj.current_characteristics.get("name", ""))
            for obj in state.objects.values()
            if not obj.retired
            and not obj.ceased_to_exist
            and obj.zone is zone
            and obj.controller == player_id
        )
    key = f"{zone.value}:{player_id}"
    return [_object_name(state, object_id) for object_id in state.zones.get(key, ())]


def _is_mana_source(obj: Any) -> bool:
    if "Land" in tuple(obj.current_characteristics.get("card_types", ())):
        return True
    for ability in obj.current_characteristics.get("abilities", ()):
        if not isinstance(ability, dict):
            continue
        effect = ability.get("effect", {})
        if isinstance(effect, dict) and str(effect.get("kind", "")) in {
            "ADD_MANA",
            "ADD_CHOSEN_MANA",
        }:
            return True
    return str(obj.current_characteristics.get("name", "")) == "Treasure"


def _state_facts(
    state: Any,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    battlefield: list[dict[str, Any]] = []
    untapped_mana_sources: list[str] = []
    glint_status: dict[str, Any] | None = None
    for obj in state.objects.values():
        if (
            obj.retired
            or obj.ceased_to_exist
            or obj.zone is not Zone.BATTLEFIELD
        ):
            continue
        name = str(obj.current_characteristics.get("name", ""))
        status = obj.permanent_status or {}
        item = {
            "identity": name,
            "controller": obj.controller,
            "tap_status": status.get("tap"),
            "attacking": bool(
                obj.current_characteristics.get("attacking") is True
            ),
            "controller_since_turn": status.get("controller_since_turn"),
            "keywords": sorted(
                str(value)
                for value in obj.current_characteristics.get("keywords", ())
            ),
        }
        battlefield.append(item)
        if (
            obj.controller == "P0"
            and status.get("tap") == "UNTAPPED"
            and _is_mana_source(obj)
        ):
            untapped_mana_sources.append(name)
        if obj.controller == "P0" and name == GLINT:
            try:
                controller_since = int(
                    status.get(
                        "controller_since_turn",
                        state.turn.number,
                    )
                )
            except (TypeError, ValueError):
                controller_since = int(state.turn.number)
            has_haste = "Haste" in set(item["keywords"])
            glint_status = {
                **item,
                "has_haste": has_haste,
                "summoning_sick_for_tap_or_attack": (
                    controller_since >= int(state.turn.number)
                    and not has_haste
                ),
            }

    stack: list[dict[str, Any]] = []
    for object_id in state.stack:
        obj = state.objects[object_id]
        stack.append(
            {
                "object_kind": str(obj.object_kind),
                "identity": str(
                    obj.current_characteristics.get("name", "")
                ),
                "ability_id": obj.current_characteristics.get("ability_id"),
                "controller": obj.controller,
            }
        )

    p0_hand = _zone_names(state, Zone.HAND, "P0")
    p0_library = _zone_names(state, Zone.LIBRARY, "P0")
    treasures = sum(
        item["controller"] == "P0" and item["identity"] == "Treasure"
        for item in battlefield
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
            key=lambda item: (
                str(item["controller"]),
                str(item["identity"]),
                str(item["tap_status"]),
            ),
        ),
        "p0_hand": p0_hand,
        "p0_mana_pool": {
            key: int(value)
            for key, value in state.players["P0"].mana_pool.items()
        },
        "p0_untapped_mana_sources": sorted(untapped_mana_sources),
        "p0_treasure_count": treasures,
        "p0_library_size": len(p0_library),
        "opponent_life_totals": {
            player_id: int(player.life)
            for player_id, player in sorted(state.players.items())
            if player_id != "P0" and player.in_game
        },
        "glint_horn_status": glint_status,
        "discardable_card_count": len(p0_hand),
        "tracker_snapshot": snapshot,
        "legally_executable": bool(snapshot["legally_executable"]),
        "full_table_kill": bool(snapshot["full_table_kill"]),
        "conditional_kill_or_takeover": bool(
            snapshot["conditional_kill_or_takeover"]
        ),
        "blockers": list(snapshot["blockers"]),
    }


def _public_menu_and_selection(
    state: Any,
    seed_text: str,
    *,
    legacy: bool,
) -> dict[str, Any]:
    executor = GameExecutor(deepcopy(state), seed_text)
    policy, _provider, evaluator_config = _bound_policy(
        executor,
        "anchor_balanced",
    )
    bind_combo_access_tracker(
        executor,
        "P0",
        evaluator_config.combo_packages,
    )
    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()
    selected_handle = (
        contract._historical_select(policy, observation, actions)
        if legacy
        else policy.select_action(observation, actions)
    )
    selected_action = next(
        action for action in actions if action.handle == selected_handle
    )
    selected_view = policy_action_view(selected_action)

    grouped: dict[str, dict[str, Any]] = {}
    for action in actions:
        view = policy_action_view(action)
        key = view.key.canonical_json
        entry = grouped.setdefault(
            key,
            {
                "public_action_key": key,
                "kind": view.kind,
                "identity": view.identity,
                "metadata": dict(view.metadata),
                "tags": sorted(str(value) for value in view.tags),
                "mana_value": int(view.mana_value),
                "target_count": int(view.target_count),
                "standard_score_prefix": list(
                    contract._substantive_prefix(
                        policy,
                        observation,
                        action,
                    )
                ),
                "private_representative_count": 0,
            },
        )
        entry["private_representative_count"] += 1

    before = state_hash(executor.state)
    broker.execute(int(observation["generation"]), selected_handle)
    post = {
        "private_state_hash": state_hash(executor.state),
        "terminal_status": executor.state.terminal.status,
        "turn": int(executor.state.turn.number),
        "phase": str(executor.state.turn.phase),
        "step": str(executor.state.turn.step),
        "priority_holder": executor.state.turn.priority_holder_id,
        "stack_size": len(executor.state.stack),
    }
    return {
        "public_action_classes": sorted(
            grouped.values(),
            key=lambda item: item["public_action_key"],
        ),
        "selected_public_action": {
            "public_action_key": selected_view.key.canonical_json,
            "kind": selected_view.kind,
            "identity": selected_view.identity,
            "metadata": dict(selected_view.metadata),
            "tags": sorted(str(value) for value in selected_view.tags),
            "standard_score_prefix": list(
                contract._substantive_prefix(
                    policy,
                    observation,
                    selected_action,
                )
            ),
        },
        "pre_action_private_state_hash": before,
        "post_action": post,
    }


def _selected(decision: dict[str, Any]) -> dict[str, Any]:
    return dict(decision["actual_selected_public_action"])


def _raw_timeline(payload: dict[str, Any]) -> dict[str, Any]:
    decisions = payload["decisions"]

    def first_matching(predicate: Any) -> dict[str, Any] | None:
        for index, decision in enumerate(decisions):
            selected = _selected(decision)
            if predicate(selected):
                return {
                    "decision_index": index,
                    "turn": int(decision["turn"]),
                    "phase": str(decision["phase"]),
                    "step": str(decision["step"]),
                    "public_action_key": str(
                        selected["public_action_key"]
                    ),
                    "kind": str(selected["action_kind"]),
                    "identity": selected["public_identity"],
                    "metadata": dict(
                        selected["canonical_public_metadata"]
                    ),
                }
        return None

    package_commitment = first_matching(
        lambda selected: (
            selected["action_kind"] == "DECLARE_ATTACKERS"
            and GLINT
            in set(
                selected["canonical_public_metadata"].get(
                    "attacker_identities",
                    (),
                )
            )
        )
        or (
            selected["action_kind"] != "PASS_PRIORITY"
            and selected["public_identity"] in PACKAGES
        )
    )
    glint_attack = first_matching(
        lambda selected: (
            selected["action_kind"] == "DECLARE_ATTACKERS"
            and GLINT
            in set(
                selected["canonical_public_metadata"].get(
                    "attacker_identities",
                    (),
                )
            )
        )
    )
    glint_loot = first_matching(
        lambda selected: (
            selected["action_kind"] == "ACTIVATE"
            and selected["public_identity"] == GLINT
            and selected["canonical_public_metadata"].get("ability_id")
            == "glint-horn:loot"
        )
    )
    glint_cast = first_matching(
        lambda selected: (
            selected["action_kind"] == "CAST"
            and selected["public_identity"] == GLINT
        )
    )
    return {
        "first_package_piece_commitment": package_commitment,
        "first_glint_horn_cast": glint_cast,
        "first_glint_horn_attack": glint_attack,
        "first_glint_horn_loot": glint_loot,
        "attacking_turns": sorted(
            {
                int(decision["turn"])
                for decision in decisions
                if (
                    _selected(decision)["action_kind"]
                    == "DECLARE_ATTACKERS"
                    and GLINT
                    in set(
                        _selected(decision)[
                            "canonical_public_metadata"
                        ].get("attacker_identities", ())
                    )
                )
            }
        ),
    }


def _witness(
    state: Any,
    seed_text: str,
) -> dict[str, Any]:
    try:
        executor, steps = contract._produce_witness(state, seed_text)
    except Exception as exc:
        return {
            "status": "FAILED_AT_EXISTING_DIAGNOSTIC_ASSUMPTION",
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "initial_turn": int(state.turn.number),
            "initial_phase": str(state.turn.phase),
            "initial_step": str(state.turn.step),
            "initial_priority_holder": state.turn.priority_holder_id,
        }
    return {
        "status": "TERMINAL_WITNESS_PRODUCED",
        "terminal_status": executor.state.terminal.status,
        "winner_ids": list(executor.state.terminal.winners),
        "loser_ids": list(executor.state.terminal.losers),
        "final_private_state_hash": state_hash(executor.state),
        "action_count": len(steps),
        "glint_horn_activation_count": sum(
            step["kind"] == "ACTIVATE" and step["identity"] == GLINT
            for step in steps
        ),
        "treasure_activation_count": sum(
            step["kind"] == "ACTIVATE"
            and step["identity"] == "Treasure"
            for step in steps
        ),
        "steps": steps,
    }


def test_stage3_bounded_first_access_probe() -> None:
    with zipfile.ZipFile(ARCHIVE) as bundle:
        raw_timelines = {
            name.removesuffix(".json"): _raw_timeline(
                json.loads(bundle.read(name))
            )
            for name in sorted(bundle.namelist())
        }

    captured = {
        "repaired-391": _capture_first_access(
            "repaired-391",
            391730338978874520,
            legacy=False,
        ),
        "legacy-391": _capture_first_access(
            "legacy-391",
            391730338978874520,
            legacy=True,
        ),
        "legacy-101": _capture_first_access(
            "legacy-101",
            101,
            legacy=True,
        ),
    }

    positive: dict[str, Any] = {}
    for label, (state, seed_text, snapshot) in captured.items():
        legacy = label.startswith("legacy-")
        positive[label] = {
            "state": _state_facts(state, snapshot),
            "menu_and_standard_selection": _public_menu_and_selection(
                state,
                seed_text,
                legacy=legacy,
            ),
            "production_witness": _witness(state, seed_text),
        }

    negative = run_phase_c_game_execution(
        seed=101,
        mode="STANDARD",
        through_turn=10,
        validate_fresh_replay=False,
        policy_actions=True,
    )
    result = {
        "schema_version": "pr100-stage3-bounded-probe-v1",
        "positive_first_access_states": positive,
        "negative_control": {
            "label": "repaired-101",
            "terminal_status": negative.technical_game.terminal_status,
            "controlled_turns_completed": (
                negative.technical_game.controlled_turns_completed
            ),
            "malcolm_glint_horn_earliest_legal_turn": (
                negative.technical_game.combo_earliest_legal_turn[
                    "malcolm_glint_horn"
                ]
            ),
            "malcolm_glint_horn_checkpoint_access": (
                negative.technical_game.combo_checkpoint_access[
                    "malcolm_glint_horn"
                ]
            ),
            "checkpoint_table_win_access": dict(
                negative.measurement.checkpoint_table_win_access
            ),
            "actual_first_attempt_turn": (
                negative.measurement.actual_first_attempt_turn
            ),
            "attempt_package": negative.measurement.attempt_package,
        },
        "raw_archive_timelines": raw_timelines,
    }
    pytest.exit(
        "STAGE3_BOUNDED_PROBE="
        + json.dumps(result, sort_keys=True, separators=(",", ":")),
        returncode=1,
    )
