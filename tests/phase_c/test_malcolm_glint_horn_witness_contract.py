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
from mtg_kernel.models import Zone
from mtg_kernel.replay import transcript, validate_replay
from mtg_kernel.resource_payment import PaymentStep, PaymentWindow
from mtg_kernel.resource_sources import solve_state_payment
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
    "legacy-101.json": (
        "5dc7311cab76a3bcd58c19542173965042046b8903177949d256a5a5de199108",
        154,
        48,
        32,
        13,
        7,
        2,
        [10],
        10,
    ),
    "legacy-391730338978874520.json": (
        "2835e668e60b94f9e4d9cd8ab1bf5d201838ab44c54ab3d3cec85e116cd01167",
        274,
        98,
        61,
        55,
        53,
        9,
        [6, 7, 8, 9, 10],
        6,
    ),
    "repaired-101.json": (
        "721d86249de6918a58161e4fcb65d1407f5e6c22dbd88fbb25664b90bd93930f",
        154,
        32,
        20,
        0,
        0,
        0,
        [],
        None,
    ),
    "repaired-391730338978874520.json": (
        "0276d308ed13f6f43783f0058cd841773cb18f639420b0de272b8d5842d0a9ea",
        220,
        63,
        46,
        1,
        0,
        0,
        [5, 6, 7, 8, 9, 10],
        None,
    ),
}
EXPECTED_FIRST_ACCESS = {
    "repaired-391": (
        "4c8cdf227e7f2ad924eccc6ef1ec903e447887915546a0512cd11e04af4d7845",
        5,
        "COMBAT",
        "COMBAT_DAMAGE",
        True,
        (),
    ),
    "legacy-391": (
        "648d4c4f54b92261fb33e73ee51e6ea632a304845726c68dfd3a8917470afd18",
        6,
        "COMBAT",
        "COMBAT_DAMAGE",
        True,
        (),
    ),
    "legacy-101": (
        "8d81dc59d5b6b5588e7e8fa16c76a22bfbf9e7899601c92ddbf7611def4ab7a7",
        10,
        "PRECOMBAT_MAIN",
        "PRECOMBAT_MAIN",
        True,
        (),
    ),
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _selected(decision: dict[str, Any]) -> dict[str, Any]:
    return decision["actual_selected_public_action"]


def _metrics(payload: dict[str, Any]) -> tuple[Any, ...]:
    decisions = payload["decisions"]
    candidates = [
        c for d in decisions for c in d["candidates"] if c.get("public_identity") == GLINT
    ]
    activates = [c for c in candidates if c.get("action_kind") == "ACTIVATE"]
    selected_loot = [
        d
        for d in decisions
        if _selected(d).get("action_kind") == "ACTIVATE"
        and _selected(d).get("public_identity") == GLINT
        and _selected(d).get("canonical_public_metadata", {}).get("ability_id") == "glint-horn:loot"
    ]
    attacks = sorted(
        {
            int(d["turn_number"])
            for d in decisions
            if _selected(d).get("action_kind") == "DECLARE_ATTACKERS"
            and GLINT
            in set(_selected(d).get("canonical_public_metadata", {}).get("attacker_identities", ()))
        }
    )
    outcome = payload["summary"]["outcome"]
    return (
        len(decisions),
        sum(d["tie_classification"] == "DISTINCT_PUBLIC_KEYS" for d in decisions),
        sum(bool(d["historical_and_repaired_selections_differ"]) for d in decisions),
        len(candidates),
        len(activates),
        len(selected_loot),
        attacks,
        outcome["actual_first_attempt_turn"],
    )


def _first_divergence(left: dict[str, Any], right: dict[str, Any], field: str) -> int | None:
    for index, (a, b) in enumerate(zip(left["decisions"], right["decisions"], strict=False)):
        if field == "public_key":
            av, bv = _selected(a)["public_action_key"], _selected(b)["public_action_key"]
        else:
            av, bv = a[field], b[field]
        if av != bv:
            return index
    return None


def test_repaired_archive_is_independently_revalidated() -> None:
    raw = ARCHIVE.read_bytes()
    assert _sha256(raw) == ARCHIVE_SHA256
    with zipfile.ZipFile(ARCHIVE) as bundle:
        assert set(bundle.namelist()) == set(EXPECTED_RUNS)
        data = {}
        for name, expected in EXPECTED_RUNS.items():
            member = bundle.read(name)
            assert _sha256(member) == expected[0]
            payload = json.loads(member)
            data[name] = payload
            assert _metrics(payload) == expected[1:]
            assert payload["summary"]["outcome"]["terminal_status"] == "ACTIVE"
            assert payload["summary"]["outcome"]["fresh_replay_equal"] is True
        for seed, expected in {"101": (9, 0, 0), "391730338978874520": (9, 9, 9)}.items():
            left, right = data[f"legacy-{seed}.json"], data[f"repaired-{seed}.json"]
            assert (
                _first_divergence(left, right, "public_key"),
                _first_divergence(left, right, "post_decision_full_state_hash"),
                _first_divergence(left, right, "resulting_public_state_digest"),
            ) == expected


def _score_prefix(
    policy: StandardPolicy, observation: dict[str, Any], action: Any
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
        count = int(view.metadata.get("attacker_count", 0))
        opponents = int(view.metadata.get("opponent_count", 0))
        pirates = int(view.metadata.get("pirate_count", 0))
        identities = {str(item) for item in view.metadata.get("attacker_identities", ())}
        value += 30 * count + 25 * opponents + 20 * pirates
        value += 25 if MALCOLM in identities else 0
        value += 20 if GLINT in identities else 0
        value -= 60 if count == 0 else 0
    if policy.opponent_interaction_modeled:
        value -= 100 if view.kind == "PASS_PRIORITY" else 0
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
    policy: StandardPolicy, observation: dict[str, Any], actions: tuple[Any, ...]
) -> str:
    return max(
        actions, key=lambda action: (*_score_prefix(policy, observation, action), action.handle)
    ).handle


class _Captured(RuntimeError):
    pass


def _first_access(
    monkeypatch: pytest.MonkeyPatch, label: str, seed: int, legacy: bool
) -> tuple[Any, str, dict[str, Any]]:
    captured: dict[str, Any] = {}
    observe, select = ComboAccessTracker.observe, StandardPolicy.select_action

    def wrapped_observe(self: ComboAccessTracker, executor: Any) -> tuple[Any, ...]:
        current = observe(self, executor)
        snap = next(
            (s for s in current if s.package == "malcolm_glint_horn" and s.legally_executable), None
        )
        if snap is not None:
            captured.update(
                state=deepcopy(executor.state), seed=str(executor.seed), snapshot=asdict(snap)
            )
            raise _Captured(label)
        return current

    def wrapped_select(
        self: StandardPolicy, observation: dict[str, Any], actions: tuple[Any, ...]
    ) -> str:
        return (
            _historical_select(self, observation, actions)
            if legacy
            else select(self, observation, actions)
        )

    monkeypatch.setattr(ComboAccessTracker, "observe", wrapped_observe)
    monkeypatch.setattr(StandardPolicy, "select_action", wrapped_select)
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
        monkeypatch.undo()
    return captured["state"], captured["seed"], captured["snapshot"]


def _public(
    executor: GameExecutor, predicate: Callable[[PolicyActionView], bool]
) -> dict[str, Any]:
    assert executor.state.turn.priority_holder_id == "P0"
    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()
    views = sorted(
        (policy_action_view(a) for a in actions if predicate(policy_action_view(a))),
        key=lambda v: v.key,
    )
    assert views
    selected = views[0]
    assert "discard_ids" not in selected.key.canonical_json
    broker.execute(
        int(observation["generation"]), resolve_selected_action_handle(actions, selected.key)
    )
    return {
        "kind": selected.kind,
        "identity": selected.identity,
        "metadata": json.loads(selected.key.canonical_json)["metadata"],
    }


def _treasure(color: str) -> Callable[[PolicyActionView], bool]:
    return lambda view: (
        view.kind == "ACTIVATE"
        and view.identity == "Treasure"
        and view.metadata.get("ability_id") == "token:treasure-mana"
        and view.metadata.get("mana_color") == color
    )


def _glint_loot(view: PolicyActionView) -> bool:
    return (
        view.kind == "ACTIVATE"
        and view.identity == GLINT
        and view.metadata.get("ability_id") == "glint-horn:loot"
    )


def _resolve_stack(executor: GameExecutor) -> None:
    while executor.state.terminal.status == "ACTIVE" and executor.state.stack:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def _close_empty_window(executor: GameExecutor) -> None:
    assert not executor.state.stack
    living = sum(player.in_game for player in executor.state.players.values())
    for _ in range(living):
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def _glint_on_field(executor: GameExecutor) -> bool:
    return any(
        not obj.retired
        and obj.zone is Zone.BATTLEFIELD
        and obj.controller == "P0"
        and str(obj.current_characteristics.get("name", "")) == GLINT
        for obj in executor.state.objects.values()
    )


def _glint_attacking(executor: GameExecutor) -> bool:
    return any(
        not obj.retired
        and obj.zone is Zone.BATTLEFIELD
        and obj.controller == "P0"
        and str(obj.current_characteristics.get("name", "")) == GLINT
        and obj.current_characteristics.get("attacking") is True
        for obj in executor.state.objects.values()
    )


def _prepare_combat(executor: GameExecutor, steps: list[dict[str, Any]]) -> None:
    if _glint_attacking(executor):
        return
    if not _glint_on_field(executor):
        steps.append(_public(executor, lambda view: view.kind == "CAST" and view.identity == GLINT))
        _resolve_stack(executor)
    assert executor.state.turn.phase == "PRECOMBAT_MAIN"
    _close_empty_window(executor)
    executor.begin_step("BEGIN_COMBAT")
    executor.begin_step("DECLARE_ATTACKERS")
    steps.append(
        _public(
            executor,
            lambda view: (
                view.kind == "DECLARE_ATTACKERS"
                and {GLINT, MALCOLM}.issubset(
                    {str(v) for v in view.metadata.get("attacker_identities", ())}
                )
            ),
        )
    )
    _close_empty_window(executor)
    executor.begin_step("DECLARE_BLOCKERS")
    executor.declare_no_blockers()
    _close_empty_window(executor)
    executor.begin_step("COMBAT_DAMAGE")
    executor.resolve_no_blocker_combat_damage({})
    _resolve_stack(executor)
    assert _glint_attacking(executor)


def _witness(state: Any, seed: str) -> tuple[GameExecutor, list[dict[str, Any]]]:
    executor = GameExecutor(deepcopy(state), seed)
    steps: list[dict[str, Any]] = []
    _prepare_combat(executor, steps)
    activations = 0
    while executor.state.terminal.status == "ACTIVE":
        assert executor.state.turn.priority_holder_id == "P0"
        pool = executor.state.players["P0"].mana_pool
        if int(pool.get("R", 0)) < 1:
            steps.append(_public(executor, _treasure("R")))
            continue
        if sum(int(value) for value in pool.values()) < 2:
            steps.append(_public(executor, _treasure("W")))
            continue
        steps.append(_public(executor, _glint_loot))
        activations += 1
        _resolve_stack(executor)
        assert activations <= 60
    assert activations > 0
    return executor, steps


def _assert_captured_combat_payment(state: Any) -> None:
    payment = solve_state_payment(
        state,
        "P0",
        (
            PaymentStep(
                "malcolm_glint_horn:activation:1",
                "{1}{R}",
                PaymentWindow(0, "captured-combat-damage"),
                context_tags=("ACTIVATED_ABILITY",),
            ),
        ),
    )
    assert payment.feasible is True
    assert sum(item.amount for item in payment.canonical_allocation) == 2
    untapped_treasures = sum(
        1
        for obj in state.objects.values()
        if not obj.retired
        and not obj.ceased_to_exist
        and obj.zone is Zone.BATTLEFIELD
        and obj.controller == "P0"
        and str(obj.current_characteristics.get("name", "")) == "Treasure"
        and (obj.permanent_status or {}).get("tap") == "UNTAPPED"
    )
    treasure_used = sum(
        item.amount
        for item in payment.canonical_allocation
        if item.source_semantic_id == "Treasure:treasure-mana"
    )
    assert treasure_used <= untapped_treasures


def test_first_access_states_have_finite_production_table_win_witnesses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for label, seed, legacy in (
        ("repaired-391", 391730338978874520, False),
        ("legacy-391", 391730338978874520, True),
        ("legacy-101", 101, True),
    ):
        state, seed_text, snapshot = _first_access(monkeypatch, label, seed, legacy)
        if label in {"repaired-391", "legacy-391"}:
            _assert_captured_combat_payment(state)
        expected = EXPECTED_FIRST_ACCESS[label]
        assert (
            state_hash(state),
            int(state.turn.number),
            state.turn.phase,
            state.turn.step,
            snapshot["sufficient_mana"],
            tuple(snapshot["blockers"]),
        ) == expected
        assert state.turn.priority_holder_id == "P0"
        assert snapshot["legally_executable"] is True
        assert snapshot["full_table_kill"] is True
        assert snapshot["conditional_kill_or_takeover"] is False
        witness, steps = _witness(state, seed_text)
        assert witness.state.terminal.status == "TERMINAL"
        assert all(
            not player.in_game for pid, player in witness.state.players.items() if pid != "P0"
        )
        assert steps[0]["identity"] == (GLINT if label == "legacy-101" else "Treasure")
        if label != "legacy-101":
            assert steps[0]["metadata"]["mana_color"] == "R"
        body = transcript(witness.state, seed=seed_text)
        assert state_hash(validate_replay(body)) == state_hash(witness.state)
        assert replay_in_fresh_process(body, cwd=ROOT).state_hash == state_hash(witness.state)

    control = run_phase_c_game_execution(
        seed=101, mode="STANDARD", through_turn=10, validate_fresh_replay=True, policy_actions=True
    )
    assert control.technical_game.combo_earliest_legal_turn["malcolm_glint_horn"] is None
    assert control.technical_game.terminal_status == "ACTIVE"
    assert control.measurement.actual_first_attempt_turn is None
    assert control.technical_game.final_state_hash == control.technical_game.fresh_replay_state_hash
