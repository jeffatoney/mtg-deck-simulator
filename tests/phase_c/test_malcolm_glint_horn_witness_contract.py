from __future__ import annotations

import hashlib
import json
import zipfile
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

import pytest

from mtg_kernel.engine import GameExecutor
from mtg_kernel.hashing import state_hash
from mtg_kernel.replay import transcript, validate_replay
from mtg_measure.combo_access import ComboAccessTracker
from mtg_policy.broker import ActionBroker
from mtg_policy.public_actions import (
    PolicyActionView,
    policy_action_view,
    resolve_selected_action_handle,
)
from mtg_policy.standard import StandardPolicy
from mtg_runs.phase_c_runner import run_phase_c_game_execution
from mtg_runs.replay_audit import replay_in_fresh_process

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = (
    ROOT / "docs/audit/phase-c-postpilot/evidence/pr100-glint-horn-repaired-behavior-4d15c185.zip"
)
ARCHIVE_SHA256 = "5f1706e2a9f1ef906938f6eef972c0f7258226f5b2e5dcb0ed008febb62eb996"
GLINT = "Glint-Horn Buccaneer"
MALCOLM = "Malcolm, Keen-Eyed Navigator"

EXPECTED_RUNS = {
    "legacy-101.json": {
        "sha256": "5dc7311cab76a3bcd58c19542173965042046b8903177949d256a5a5de199108",
        "decisions": 154,
        "ties": 48,
        "selector_disagreements": 32,
        "glint_candidates": 13,
        "glint_activations": 7,
        "selected_loot": 2,
        "attacking_turns": [10],
        "attempt_turn": 10,
    },
    "legacy-391730338978874520.json": {
        "sha256": "2835e668e60b94f9e4d9cd8ab1bf5d201838ab44c54ab3d3cec85e116cd01167",
        "decisions": 274,
        "ties": 98,
        "selector_disagreements": 61,
        "glint_candidates": 55,
        "glint_activations": 53,
        "selected_loot": 9,
        "attacking_turns": [6, 7, 8, 9, 10],
        "attempt_turn": 6,
    },
    "repaired-101.json": {
        "sha256": "721d86249de6918a58161e4fcb65d1407f5e6c22dbd88fbb25664b90bd93930f",
        "decisions": 154,
        "ties": 32,
        "selector_disagreements": 20,
        "glint_candidates": 0,
        "glint_activations": 0,
        "selected_loot": 0,
        "attacking_turns": [],
        "attempt_turn": None,
    },
    "repaired-391730338978874520.json": {
        "sha256": "0276d308ed13f6f43783f0058cd841773cb18f639420b0de272b8d5842d0a9ea",
        "decisions": 220,
        "ties": 63,
        "selector_disagreements": 46,
        "glint_candidates": 1,
        "glint_activations": 0,
        "selected_loot": 0,
        "attacking_turns": [5, 6, 7, 8, 9, 10],
        "attempt_turn": None,
    },
}
EXPECTED_FIRST_ACCESS_HASHES = {
    "repaired-391": "4c8cdf227e7f2ad924eccc6ef1ec903e447887915546a0512cd11e04af4d7845",
    "legacy-391": "03a5f0dbc75f0b2715e640259e8610739b8cf9778c17a8b6b2bfbd8333d675c0",
    "legacy-101": "493d277b8476aa95e6bc7ba11b90695a66d35dee7678d2ea74d9ad89ded6e728",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _selected(decision: dict[str, Any]) -> dict[str, Any]:
    return decision["actual_selected_public_action"]


def _archive_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    decisions = payload["decisions"]
    glint_candidates = [
        candidate
        for decision in decisions
        for candidate in decision["candidates"]
        if candidate.get("public_identity") == GLINT
    ]
    glint_activations = [
        candidate
        for candidate in glint_candidates
        if candidate.get("action_kind") == "ACTIVATE"
        and candidate.get("canonical_public_metadata", {}).get("ability_id") == "glint-horn:loot"
    ]
    selected_loot = [
        decision
        for decision in decisions
        if _selected(decision).get("action_kind") == "ACTIVATE"
        and _selected(decision).get("public_identity") == GLINT
        and _selected(decision).get("canonical_public_metadata", {}).get("ability_id")
        == "glint-horn:loot"
    ]
    attacking_turns = sorted(
        {
            int(decision["turn_number"])
            for decision in decisions
            if _selected(decision).get("action_kind") == "DECLARE_ATTACKERS"
            and GLINT
            in set(
                _selected(decision).get("canonical_public_metadata", {}).get(
                    "attacker_identities", ()
                )
            )
        }
    )
    outcome = payload["summary"]["outcome"]
    return {
        "decisions": len(decisions),
        "ties": sum(
            decision["tie_classification"] == "DISTINCT_PUBLIC_KEYS" for decision in decisions
        ),
        "selector_disagreements": sum(
            bool(decision["historical_and_repaired_selections_differ"])
            for decision in decisions
        ),
        "glint_candidates": len(glint_candidates),
        "glint_activations": len(glint_activations),
        "selected_loot": len(selected_loot),
        "attacking_turns": attacking_turns,
        "attempt_turn": outcome["actual_first_attempt_turn"],
        "attempt_package": outcome["attempt_package"],
        "terminal_status": outcome["terminal_status"],
        "fresh_replay_equal": outcome["fresh_replay_equal"],
        "checkpoint_access": outcome.get("combo_checkpoint_access", {}).get(
            "malcolm_glint_horn", {}
        ),
    }


def _first_divergence(
    legacy: dict[str, Any], repaired: dict[str, Any], field: str
) -> int | None:
    for index, (left, right) in enumerate(
        zip(legacy["decisions"], repaired["decisions"], strict=False)
    ):
        if field == "public_key":
            left_value = _selected(left)["public_action_key"]
            right_value = _selected(right)["public_action_key"]
        else:
            left_value = left[field]
            right_value = right[field]
        if left_value != right_value:
            return index
    return None


def test_repaired_archive_is_independently_revalidated() -> None:
    raw_archive = ARCHIVE.read_bytes()
    assert _sha256(raw_archive) == ARCHIVE_SHA256
    with zipfile.ZipFile(ARCHIVE) as bundle:
        assert set(bundle.namelist()) == set(EXPECTED_RUNS)
        payloads: dict[str, dict[str, Any]] = {}
        for name, expected in EXPECTED_RUNS.items():
            raw = bundle.read(name)
            assert _sha256(raw) == expected["sha256"]
            payload = json.loads(raw)
            payloads[name] = payload
            metrics = _archive_metrics(payload)
            for key in (
                "decisions",
                "ties",
                "selector_disagreements",
                "glint_candidates",
                "glint_activations",
                "selected_loot",
                "attacking_turns",
                "attempt_turn",
            ):
                assert metrics[key] == expected[key]
            assert metrics["terminal_status"] == "ACTIVE"
            assert metrics["fresh_replay_equal"] is True

        expected_divergences = {
            "101": (9, 0, 0),
            "391730338978874520": (9, 9, 9),
        }
        for seed, expected in expected_divergences.items():
            legacy = payloads[f"legacy-{seed}.json"]
            repaired = payloads[f"repaired-{seed}.json"]
            actual = (
                _first_divergence(legacy, repaired, "public_key"),
                _first_divergence(legacy, repaired, "post_decision_full_state_hash"),
                _first_divergence(legacy, repaired, "resulting_public_state_digest"),
            )
            assert actual == expected


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


def _historical_select(
    policy: StandardPolicy,
    observation: dict[str, Any],
    actions: tuple[Any, ...],
) -> str:
    return max(
        actions,
        key=lambda action: (*_substantive_prefix(policy, observation, action), action.handle),
    ).handle


class _FirstAccessCaptured(RuntimeError):
    pass


def _capture_first_access(
    monkeypatch: pytest.MonkeyPatch,
    *,
    label: str,
    seed: int,
    legacy: bool,
) -> tuple[Any, str, dict[str, Any]]:
    captured: dict[str, Any] = {}
    original_observe = ComboAccessTracker.observe
    original_select = StandardPolicy.select_action

    def wrapped_observe(self: ComboAccessTracker, executor: Any) -> tuple[Any, ...]:
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
            raise _FirstAccessCaptured(label)
        return result

    def wrapped_select(
        self: StandardPolicy,
        observation: dict[str, Any],
        actions: tuple[Any, ...],
    ) -> str:
        if legacy:
            return _historical_select(self, observation, actions)
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


def _auto_pass_opponents_until_p0(executor: GameExecutor) -> None:
    while (
        executor.state.terminal.status == "ACTIVE"
        and executor.state.turn.priority_holder_id not in {None, "P0"}
    ):
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def _execute_public(
    executor: GameExecutor,
    predicate: Callable[[PolicyActionView], bool],
) -> dict[str, Any]:
    _auto_pass_opponents_until_p0(executor)
    assert executor.state.turn.priority_holder_id == "P0"
    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()
    matches = sorted(
        (policy_action_view(action) for action in actions if predicate(policy_action_view(action))),
        key=lambda view: view.key,
    )
    assert matches
    selected = matches[0]
    assert "discard_ids" not in selected.key.canonical_json
    handle = resolve_selected_action_handle(actions, selected.key)
    before = state_hash(executor.state)
    broker.execute(int(observation["generation"]), handle)
    return {
        "public_action_key": selected.key.canonical_json,
        "kind": selected.kind,
        "identity": selected.identity,
        "metadata": json.loads(selected.key.canonical_json)["metadata"],
        "pre_state_hash_private": before,
        "post_state_hash_private": state_hash(executor.state),
    }


def _treasure(color: str) -> Callable[[PolicyActionView], bool]:
    def predicate(view: PolicyActionView) -> bool:
        return (
            view.kind == "ACTIVATE"
            and view.identity == "Treasure"
            and view.metadata.get("ability_id") == "token:treasure-mana"
            and view.metadata.get("mana_color") == color
        )

    return predicate


def _glint_loot(view: PolicyActionView) -> bool:
    return (
        view.kind == "ACTIVATE"
        and view.identity == GLINT
        and view.metadata.get("ability_id") == "glint-horn:loot"
    )


def _glint_action_available(executor: GameExecutor) -> bool:
    _observation, actions = ActionBroker(executor, "P0").refresh()
    return any(_glint_loot(policy_action_view(action)) for action in actions)


def _resolve_stack_to_p0(executor: GameExecutor) -> None:
    while executor.state.terminal.status == "ACTIVE" and executor.state.stack:
        _auto_pass_opponents_until_p0(executor)
        assert executor.state.turn.priority_holder_id == "P0"
        executor.pass_priority("P0")
        _auto_pass_opponents_until_p0(executor)
    if executor.state.terminal.status == "ACTIVE":
        assert executor.state.turn.priority_holder_id == "P0"


def _produce_witness(state: Any, seed: str) -> tuple[GameExecutor, list[dict[str, Any]]]:
    executor = GameExecutor(deepcopy(state), seed)
    steps: list[dict[str, Any]] = []
    activations = 0
    while executor.state.terminal.status == "ACTIVE":
        _auto_pass_opponents_until_p0(executor)
        assert executor.state.turn.phase == "COMBAT"
        assert executor.state.turn.step == "COMBAT_DAMAGE"
        assert executor.state.turn.priority_holder_id == "P0"
        if not _glint_action_available(executor):
            pool = executor.state.players["P0"].mana_pool
            if int(pool.get("R", 0)) < 1:
                steps.append(_execute_public(executor, _treasure("R")))
            elif sum(int(value) for value in pool.values()) < 2:
                steps.append(_execute_public(executor, _treasure("W")))
            else:
                raise AssertionError("Glint-Horn activation absent despite payable public state")
            continue
        steps.append(_execute_public(executor, _glint_loot))
        activations += 1
        _resolve_stack_to_p0(executor)
        assert activations <= 60
    assert activations > 0
    return executor, steps


def test_first_access_states_have_finite_production_table_win_witnesses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = (
        ("repaired-391", 391730338978874520, False, 5),
        ("legacy-391", 391730338978874520, True, 6),
        ("legacy-101", 101, True, 10),
    )
    for label, seed, legacy, turn in cases:
        state, seed_text, snapshot = _capture_first_access(
            monkeypatch, label=label, seed=seed, legacy=legacy
        )
        assert state_hash(state) == EXPECTED_FIRST_ACCESS_HASHES[label]
        assert int(state.turn.number) == turn
        assert state.turn.phase == "COMBAT"
        assert state.turn.step == "COMBAT_DAMAGE"
        assert state.turn.priority_holder_id == "P0"
        assert snapshot["legally_executable"] is True
        assert snapshot["full_table_kill"] is True
        assert snapshot["conditional_kill_or_takeover"] is False
        if label == "repaired-391":
            assert snapshot["sufficient_mana"] is False
            assert tuple(snapshot["blockers"]) == ("INSUFFICIENT_MANA_OR_DISCARD",)
        else:
            assert snapshot["sufficient_mana"] is True
            assert not snapshot["blockers"]

        witness, steps = _produce_witness(state, seed_text)
        assert witness.state.terminal.status == "TERMINAL"
        assert all(
            not player.in_game
            for player_id, player in witness.state.players.items()
            if player_id != "P0"
        )
        if label == "repaired-391":
            assert steps[0]["identity"] == "Treasure"
            assert steps[0]["metadata"]["mana_color"] == "R"
        else:
            assert steps[0]["identity"] == GLINT
            assert steps[0]["kind"] == "ACTIVATE"

        body = transcript(witness.state, seed=seed_text)
        same_process = validate_replay(body)
        assert state_hash(same_process) == state_hash(witness.state)
        fresh = replay_in_fresh_process(body, cwd=ROOT)
        assert fresh.state_hash == state_hash(witness.state)

    control = run_phase_c_game_execution(
        seed=101,
        mode="STANDARD",
        through_turn=10,
        validate_fresh_replay=True,
        policy_actions=True,
    )
    assert control.technical_game.combo_earliest_legal_turn["malcolm_glint_horn"] is None
    assert control.technical_game.terminal_status == "ACTIVE"
    assert control.measurement.actual_first_attempt_turn is None
    assert control.technical_game.final_state_hash == control.technical_game.fresh_replay_state_hash
