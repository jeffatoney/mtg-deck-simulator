"""Probe and clone isolation for replay metadata and strategic bindings."""

from __future__ import annotations

import json
from copy import deepcopy

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.engine import GameExecutor
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import TargetRef, Zone
from mtg_kernel.replay import transcript, validate_replay
from mtg_kernel.serialization import state_to_data
from mtg_kernel.strategic_choices import CounterPaymentRequest, CounterPaymentSelection
from mtg_policy import ActionBroker
from mtg_policy.broker import ActionBroker as BaseActionBroker
from mtg_policy.broker_core import disposable_probe_state
from mtg_runs import phase_c_runner

PLAYERS = ("P0", "P1", "P2", "P3")


class _PayProvider:
    def choose_counter_payment(self, request: CounterPaymentRequest) -> CounterPaymentSelection:
        selected = "PAY" if "PAY" in request.legal_outcomes else "DECLINE"
        return CounterPaymentSelection(selected, "probe-isolation", "1" * 64, {})


def _live_executor(seed: str, profile: str = "no_known_colors") -> GameExecutor:
    state, executor = new_game(PLAYERS, seed)
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    state.turn.phase = "PRECOMBAT_MAIN"
    state.players["P0"].mana_pool.update({symbol: 0 for symbol in ("W", "U", "B", "R", "G", "C")})
    state.players["P0"].mana_pool["U"] = 2
    add_card(executor, specs["Island"], Zone.BATTLEFIELD, owner="P0")
    add_card(executor, specs["Island"], Zone.BATTLEFIELD, owner="P0")
    opt = add_card(executor, specs["Opt"], Zone.HAND, owner="P0")
    pierce = add_card(executor, specs["Spell Pierce"], Zone.HAND, owner="P0")
    state.replay_initial_state = state_to_data(state)
    executor.opponent_mana_profile = profile
    executor.bind_strategic_choice_provider(_PayProvider(), controlled_player_id="P0")
    target = executor.cast("P0", opt.object_id, choices={"scry_to_bottom": False})
    executor.cast("P0", pierce.object_id, targets=(TargetRef(target.object_id),))
    return executor


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def test_disposable_probe_state_does_not_alias_replay_initial_state() -> None:
    executor = _live_executor("stage3-probe-alias")
    original = executor.state.replay_initial_state
    assert original is not None
    before = _json_bytes(original)
    probe_state = disposable_probe_state(executor.state)
    assert probe_state.replay_initial_state is not original
    assert probe_state.replay_initial_state is not None
    probe_state.replay_initial_state["mutated_by_probe"] = True
    context = probe_state.replay_initial_state.setdefault("execution_context", {})
    context["opponent_mana_profile"] = "tampered"
    assert _json_bytes(original) == before
    assert "mutated_by_probe" not in original


def test_probe_constructor_cannot_mutate_live_replay_or_transcript_bytes() -> None:
    executor = _live_executor("stage3-probe-constructor", profile="no_known_colors")
    original = executor.state.replay_initial_state
    assert original is not None
    before_initial = _json_bytes(original)
    before_commands = _json_bytes(executor.state.replay_commands)
    body = transcript(executor.state, seed=executor.seed)
    before_transcript = _json_bytes(body)

    for broker_type in (ActionBroker, BaseActionBroker):
        broker_type(executor, "P0")._probe("pass_priority", {"player_id": "P0"})

    assert executor.state.replay_initial_state is original
    assert _json_bytes(original) == before_initial
    assert _json_bytes(executor.state.replay_commands) == before_commands
    assert _json_bytes(transcript(executor.state, seed=executor.seed)) == before_transcript


def test_probe_preserves_binding_and_nondefault_opponent_profile() -> None:
    executor = _live_executor("stage3-probe-binding", profile="no_known_colors")
    probe_state = disposable_probe_state(executor.state)
    probe = GameExecutor(
        probe_state,
        executor.seed,
        replaying=True,
        probing=True,
        opponent_mana_profile=executor.opponent_mana_profile,
        strategic_choice_binding=executor.strategic_choice_binding,
    )
    assert probe.opponent_mana_profile == "no_known_colors"
    assert probe.controlled_player_id == "P0"
    assert probe.strategic_choice_binding is executor.strategic_choice_binding
    assert executor.controlled_player_id == "P0"


def test_replay_reconstructs_recorded_nondefault_profile() -> None:
    executor = _live_executor("stage3-probe-replay-profile", profile="no_known_colors")
    for _ in PLAYERS:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)
    body = transcript(executor.state, seed=executor.seed)
    assert body["initial_state"]["execution_context"] == {
        "opponent_mana_profile": "no_known_colors"
    }
    replayed = validate_replay(body)
    assert state_hash(replayed) == state_hash(executor.state)


def test_runner_clone_threads_profile_and_rebounds_controlled_player() -> None:
    executor = _live_executor("stage3-probe-runner-clone", profile="no_known_colors")
    before_initial = _json_bytes(executor.state.replay_initial_state)
    clone_state = deepcopy(executor.state)
    clone = GameExecutor(
        clone_state,
        executor.seed,
        opponent_mana_profile=executor.opponent_mana_profile,
    )
    phase_c_runner._bound_policy(clone, "anchor_balanced")
    assert clone.opponent_mana_profile == "no_known_colors"
    assert clone.controlled_player_id == "P0"
    assert executor.controlled_player_id == "P0"
    assert _json_bytes(executor.state.replay_initial_state) == before_initial
