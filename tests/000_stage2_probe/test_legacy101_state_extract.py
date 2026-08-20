from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import pytest

from mtg_kernel.engine import GameExecutor
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import Zone
from mtg_policy.broker import ActionBroker
from mtg_policy.public_actions import policy_action_view
from mtg_runs.phase_c_runner import _bound_policy
from tests.phase_c import test_malcolm_glint_horn_witness_contract as witness


def _facts(state: Any, snapshot: dict[str, Any]) -> dict[str, Any]:
    battlefield = []
    untapped_mana_sources = []
    for obj in state.objects.values():
        if obj.retired or obj.ceased_to_exist or obj.zone is not Zone.BATTLEFIELD:
            continue
        name = str(obj.current_characteristics.get("name", ""))
        status = obj.permanent_status or {}
        item = {
            "identity": name,
            "controller": obj.controller,
            "tap_status": status.get("tap"),
            "attacking": obj.current_characteristics.get("attacking") is True,
            "controller_since_turn": status.get("controller_since_turn"),
            "keywords": sorted(
                str(value) for value in obj.current_characteristics.get("keywords", ())
            ),
        }
        battlefield.append(item)
        if obj.controller == "P0" and status.get("tap") == "UNTAPPED":
            card_types = set(
                str(value) for value in obj.current_characteristics.get("card_types", ())
            )
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
                "ability_id": (
                    raw_ability.get("ability_id") if isinstance(raw_ability, dict) else None
                ),
            }
        )

    glint = next(
        (
            item
            for item in battlefield
            if item["controller"] == "P0" and item["identity"] == witness.GLINT
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
            item["controller"] == "P0" and item["identity"] == "Treasure" for item in battlefield
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


def _menu_selected(state: Any, seed_text: str) -> dict[str, Any]:
    executor = GameExecutor(deepcopy(state), seed_text)
    policy, _provider, _evaluator = _bound_policy(executor, "anchor_balanced")
    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()
    handle = witness._historical_select(policy, observation, actions)
    selected = next(action for action in actions if action.handle == handle)
    view = policy_action_view(selected)
    return {
        "kind": view.kind,
        "identity": view.identity,
        "metadata": json.loads(view.key.canonical_json)["metadata"],
        "score_prefix": list(witness._score_prefix(policy, observation, selected)),
    }


def test_extract_current_legacy_101_first_access_state() -> None:
    patch = pytest.MonkeyPatch()
    state, seed_text, snapshot = witness._first_access(
        patch,
        "legacy-101",
        101,
        True,
    )
    payload = {
        "schema_version": "stage2-legacy101-state-diagnostic-v1",
        "state": _facts(state, snapshot),
        "menu_selected": _menu_selected(state, seed_text),
    }
    pytest.exit(
        "STAGE2_LEGACY101_STATE=" + json.dumps(payload, sort_keys=True, separators=(",", ":")),
        returncode=1,
    )
