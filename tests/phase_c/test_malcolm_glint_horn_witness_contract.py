from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from mtg_kernel.hashing import state_hash
from mtg_kernel.models import Zone
from mtg_measure.combo_access import ComboAccessTracker
from mtg_policy.broker import ActionBroker
from mtg_policy.public_actions import policy_action_view
from mtg_policy.standard import StandardPolicy
from mtg_runs.phase_c_runner import run_phase_c_game_execution


GLINT = "Glint-Horn Buccaneer"
MALCOLM = "Malcolm, Keen-Eyed Navigator"
_CURRENT_SELECTOR = ""
_CAPTURED: dict[str, dict[str, Any]] = {}


def _substantive_prefix(
    policy: StandardPolicy,
    observation: dict[str, Any],
    action: Any,
) -> tuple[int, int, int, int, int]:
    view = policy_action_view(action)
    tags = set(view.tags)
    value = 0
    if view.kind == "PLAY_LAND":
        value += 80
    if "ADD_MANA" in tags or "MANA_ABILITY" in tags:
        value += 65
    if "COMBO_COMPONENT" in tags:
        value += 50 if policy.bundle.value("glint_horn_use") == "cast_for_value" else 35
    if "PROTECTION" in tags and policy.opponent_interaction_modeled:
        value += 45 if policy.bundle.value("protection_plan") == "protected" else 10
    if "DRAW" in tags or "SCRY" in tags:
        value += 35 if policy.bundle.value("velocity_plan") == "cantrip_first" else 20
    if view.identity == MALCOLM:
        value += 70 if policy.bundle.value("development_plan") == "malcolm_first" else 30
    if view.identity == "Breeches, Brazen Plunderer":
        value += 25 if policy.bundle.value("breeches_timing") == "early" else 5
    if view.kind == "DECLARE_ATTACKERS":
        attacker_count = int(view.metadata.get("attacker_count", 0))
        opponent_count = int(view.metadata.get("opponent_count", 0))
        pirate_count = int(view.metadata.get("pirate_count", 0))
        identities = {str(item) for item in view.metadata.get("attacker_identities", ())}
        value += 30 * attacker_count + 25 * opponent_count + 20 * pirate_count
        if MALCOLM in identities:
            value += 25
        if GLINT in identities:
            value += 20
        if attacker_count == 0:
            value -= 60
    if policy.opponent_interaction_modeled:
        if view.kind == "PASS_PRIORITY":
            value -= 100
        return (0, value, 0, -view.mana_value, -view.target_count)
    classification = policy._no_opponent_self_class(observation, view)
    if classification == "DEFENSIVE_SELF_ONLY":
        utility, pass_preference = -1, 0
    elif classification == "NEUTRAL_SELF_TRADEOFF":
        utility, pass_preference = 0, 0
    elif view.kind == "PASS_PRIORITY":
        utility, value, pass_preference = 0, 0, 1
    else:
        utility, pass_preference = 1, 0
    return (utility, value, pass_preference, -view.mana_value, -view.target_count)


def _state_facts(executor: Any, snapshot: Any) -> dict[str, Any]:
    state = executor.state
    battlefield = []
    untapped_sources = []
    for obj in state.objects.values():
        if obj.retired or obj.ceased_to_exist or obj.zone is not Zone.BATTLEFIELD:
            continue
        name = str(obj.current_characteristics.get("name", ""))
        status = obj.permanent_status or {}
        entry = {
            "name": name,
            "controller": obj.controller,
            "tapped": status.get("tap") == "TAPPED",
            "attacking": obj.current_characteristics.get("attacking") is True,
            "keywords": sorted(str(value) for value in obj.current_characteristics.get("keywords", ())),
            "controller_since_turn": status.get("controller_since_turn"),
        }
        battlefield.append(entry)
        if obj.controller == "P0" and status.get("tap") == "UNTAPPED":
            for ability in obj.current_characteristics.get("abilities", ()):
                if ability.get("mana_ability"):
                    untapped_sources.append(name)
                    break
    hand_key = executor.zones.zone_key(Zone.HAND, "P0")
    library_key = executor.zones.zone_key(Zone.LIBRARY, "P0")
    hand_names = sorted(
        str(state.objects[object_id].current_characteristics.get("name", ""))
        for object_id in state.zones.get(hand_key, ())
    )
    stack = []
    for object_id in state.stack:
        obj = state.objects[object_id]
        ability = obj.current_characteristics.get("ability", {})
        source = state.objects.get(obj.source_object_id) if obj.source_object_id else None
        stack.append(
            {
                "kind": str(obj.object_kind.value),
                "source": str(source.current_characteristics.get("name", "")) if source else None,
                "ability_id": ability.get("ability_id") if isinstance(ability, dict) else None,
            }
        )
    glint = next((item for item in battlefield if item["name"] == GLINT), None)
    return {
        "full_state_hash_private": state_hash(state),
        "turn": int(state.turn.number),
        "phase": str(state.turn.phase),
        "step": str(state.turn.step),
        "priority_holder": state.turn.priority_holder_id,
        "stack": stack,
        "battlefield": sorted(battlefield, key=lambda item: (item["controller"] or "", item["name"])),
        "hand": hand_names,
        "mana_pool": dict(sorted(state.players["P0"].mana_pool.items())),
        "untapped_mana_sources": sorted(untapped_sources),
        "treasure_count": sum(item["name"] == "Treasure" and item["controller"] == "P0" for item in battlefield),
        "library_size": len(state.zones.get(library_key, ())),
        "opponent_life": {
            player_id: int(player.life)
            for player_id, player in state.players.items()
            if player_id != "P0" and player.in_game
        },
        "glint_attacking": bool(glint and glint["attacking"]),
        "glint_haste": bool(glint and "Haste" in glint["keywords"]),
        "glint_controller_since_turn": glint["controller_since_turn"] if glint else None,
        "discardable_card_count": len(hand_names),
        "tracker_snapshot": asdict(snapshot),
    }


def test_probe_exact_first_access_states(monkeypatch: Any) -> None:
    original_observe = ComboAccessTracker.observe
    original_refresh = ActionBroker.refresh
    original_select = StandardPolicy.select_action

    def wrapped_observe(self: ComboAccessTracker, executor: Any) -> tuple[Any, ...]:
        result = original_observe(self, executor)
        if _CURRENT_SELECTOR and _CURRENT_SELECTOR not in _CAPTURED:
            snapshot = next(
                (
                    item
                    for item in result
                    if item.package == "malcolm_glint_horn" and item.legally_executable
                ),
                None,
            )
            if snapshot is not None:
                _CAPTURED[_CURRENT_SELECTOR] = _state_facts(executor, snapshot)
        return result

    def wrapped_refresh(self: ActionBroker) -> tuple[dict[str, Any], tuple[Any, ...]]:
        observation, actions = original_refresh(self)
        capture = _CAPTURED.get(_CURRENT_SELECTOR)
        if capture is not None and "legal_action_surface" not in capture:
            if capture["full_state_hash_private"] == state_hash(self.executor.state):
                capture["legal_action_surface"] = sorted(
                    {
                        policy_action_view(action).key.canonical_json
                        for action in actions
                    }
                )
        return observation, actions

    def wrapped_select(
        self: StandardPolicy,
        observation: dict[str, Any],
        actions: tuple[Any, ...],
    ) -> str:
        if _CURRENT_SELECTOR != "legacy":
            return original_select(self, observation, actions)
        return max(
            actions,
            key=lambda action: (*_substantive_prefix(self, observation, action), action.handle),
        ).handle

    monkeypatch.setattr(ComboAccessTracker, "observe", wrapped_observe)
    monkeypatch.setattr(ActionBroker, "refresh", wrapped_refresh)
    monkeypatch.setattr(StandardPolicy, "select_action", wrapped_select)

    outcomes = {}
    cases = (
        ("repaired-391", "repaired", 391730338978874520),
        ("legacy-391", "legacy", 391730338978874520),
        ("legacy-101", "legacy", 101),
        ("repaired-101", "repaired-control", 101),
    )
    global _CURRENT_SELECTOR
    for label, selector, seed in cases:
        _CURRENT_SELECTOR = selector
        execution = run_phase_c_game_execution(
            seed=seed,
            mode="STANDARD",
            through_turn=10,
            validate_fresh_replay=True,
            policy_actions=True,
        )
        outcomes[label] = {
            "captured": _CAPTURED.get(selector),
            "terminal_status": execution.technical_game.terminal_status,
            "fresh_replay_equal": (
                execution.technical_game.final_state_hash
                == execution.technical_game.fresh_replay_state_hash
            ),
            "actual_first_attempt_turn": execution.measurement.actual_first_attempt_turn,
            "attempt_package": execution.measurement.attempt_package,
            "checkpoint_table_win_access": dict(execution.measurement.checkpoint_table_win_access),
            "combo_earliest_legal_turn": dict(execution.technical_game.combo_earliest_legal_turn),
        }
    _CURRENT_SELECTOR = ""
    raise AssertionError("STAGE3_FIRST_ACCESS_PROBE=" + json.dumps(outcomes, sort_keys=True))
