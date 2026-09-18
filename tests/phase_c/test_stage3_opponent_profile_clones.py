"""Regression coverage for opponent-mana execution context in executor clones."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.engine import GameExecutor
from mtg_kernel.errors import IllegalAction, UnsupportedCapability
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import TargetRef, Zone
from mtg_kernel.replay import transcript, validate_replay
from mtg_kernel.serialization import state_to_data
from mtg_kernel.strategic_choices import CounterPaymentRequest
from mtg_policy import (
    ActionBroker,
    ContextualEvaluator,
    PolicyStrategicChoiceProvider,
    load_evaluator_config,
    load_policy_matrix,
)
from mtg_policy.broker import ActionBroker as BaseActionBroker
from mtg_runs import phase_c_runner

PLAYERS = ("P0", "P1", "P2", "P3")
PROFILES = ("no_known_colors", "blue_red_available")


@dataclass
class _CapturingCounterProvider:
    delegate: PolicyStrategicChoiceProvider
    requests: list[CounterPaymentRequest]

    def choose_counter_payment(self, request: CounterPaymentRequest) -> Any:
        self.requests.append(request)
        return self.delegate.choose_counter_payment(request)


class _SuccessorCaptured(RuntimeError):
    def __init__(self, successor: Any) -> None:
        super().__init__("captured exploratory successor")
        self.successor = successor


def _production_provider() -> PolicyStrategicChoiceProvider:
    bundle = next(
        item for item in load_policy_matrix() if item.policy_config_id == "anchor_balanced"
    )
    return PolicyStrategicChoiceProvider(bundle, ContextualEvaluator(load_evaluator_config()))


def _counter_fixture(
    opponent_mana_profile: str,
    *,
    seed_suffix: str,
) -> tuple[Any, GameExecutor, Any, _CapturingCounterProvider]:
    state, executor = new_game(PLAYERS, f"stage3-profile-clone-{seed_suffix}")
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    state.turn.phase = "PRECOMBAT_MAIN"
    state.turn.step = "PRECOMBAT_MAIN"
    for symbol in ("W", "U", "B", "R", "G", "C"):
        state.players["P0"].mana_pool[symbol] = 0
    state.players["P0"].mana_pool["U"] = 2
    add_card(executor, specs["Exotic Orchard"], Zone.BATTLEFIELD, owner="P0")
    add_card(executor, specs["Fellwar Stone"], Zone.BATTLEFIELD, owner="P0")
    creature = add_card(executor, specs["Dualcaster Mage"], Zone.BATTLEFIELD, owner="P0")
    curiosity = add_card(executor, specs["Curiosity"], Zone.HAND, owner="P0")
    spell_pierce = add_card(executor, specs["Spell Pierce"], Zone.HAND, owner="P0")
    state.replay_initial_state = state_to_data(state)
    executor.opponent_mana_profile = opponent_mana_profile
    provider = _CapturingCounterProvider(_production_provider(), [])
    executor.bind_strategic_choice_provider(provider, controlled_player_id="P0")
    target = executor.cast(
        "P0",
        curiosity.object_id,
        targets=(TargetRef(creature.object_id),),
    )
    executor.cast(
        "P0",
        spell_pierce.object_id,
        targets=(TargetRef(target.object_id),),
    )
    assert sum(state.players["P0"].mana_pool.values()) == 0
    return state, executor, target, provider


def _resolve_top(executor: GameExecutor) -> None:
    for _ in PLAYERS:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def _counter_outcome(state: Any) -> str:
    choice = next(item for item in state.choices if item.kind == "COUNTER_UNLESS_PAY")
    return str(choice.selected["outcome"])


@pytest.mark.parametrize(
    ("opponent_mana_profile", "expected_feasible", "expected_outcome"),
    (
        ("no_known_colors", False, "DECLINE"),
        ("blue_red_available", True, "PAY"),
    ),
)
def test_live_counter_payment_profile_is_replay_exact(
    opponent_mana_profile: str,
    expected_feasible: bool,
    expected_outcome: str,
) -> None:
    state, executor, target, provider = _counter_fixture(
        opponent_mana_profile,
        seed_suffix=f"live-{opponent_mana_profile}",
    )

    _resolve_top(executor)

    assert len(provider.requests) == 1
    assert provider.requests[0].payment_result.feasible is expected_feasible
    assert _counter_outcome(state) == expected_outcome
    assert (target.object_id in state.stack) is expected_feasible
    body = transcript(state, seed=executor.seed)
    if opponent_mana_profile == "no_known_colors":
        assert body["initial_state"]["execution_context"] == {
            "opponent_mana_profile": "no_known_colors"
        }
    else:
        assert "execution_context" not in body["initial_state"]
    replayed = validate_replay(body)
    assert state_hash(replayed) == state_hash(state)


@pytest.mark.parametrize("broker_type", (ActionBroker, BaseActionBroker))
@pytest.mark.parametrize(
    ("opponent_mana_profile", "expected_feasible"),
    (("no_known_colors", False), ("blue_red_available", True)),
)
def test_broker_probe_preserves_opponent_profile_and_live_state(
    broker_type: type[BaseActionBroker],
    opponent_mana_profile: str,
    expected_feasible: bool,
) -> None:
    state, executor, _target, provider = _counter_fixture(
        opponent_mana_profile,
        seed_suffix=f"broker-{broker_type.__module__}-{opponent_mana_profile}",
    )
    state.turn.consecutive_priority_passes = len(PLAYERS) - 1
    before_hash = state_hash(state)
    before_rng_streams = deepcopy(state.rng_streams)

    assert broker_type(executor, "P0")._probe("pass_priority", {"player_id": "P0"})

    assert provider.requests[-1].payment_result.feasible is expected_feasible
    assert provider.requests[-1].legal_outcomes == (
        ("PAY", "DECLINE") if expected_feasible else ("DECLINE",)
    )
    assert state_hash(state) == before_hash
    assert state.rng_streams == before_rng_streams


@pytest.mark.parametrize("opponent_mana_profile", PROFILES)
def test_runner_successor_preserves_profile_without_mutating_live_executor(
    monkeypatch: pytest.MonkeyPatch,
    opponent_mana_profile: str,
) -> None:
    state, executor, _target, _provider = _counter_fixture(
        opponent_mana_profile,
        seed_suffix=f"runner-{opponent_mana_profile}",
    )
    state.turn.consecutive_priority_passes = len(PLAYERS) - 1
    before_hash = state_hash(state)
    before_rng_streams = deepcopy(state.rng_streams)
    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()
    pass_action = next(item for item in actions if item.kind == "PASS_PRIORITY")
    explorer = phase_c_runner._OneLayerExplorer("anchor_balanced", search_seed=113)

    def capture_successor(root: Any, *, belief_sample_seeds: Any, expand: Any) -> Any:
        successor = expand(root, pass_action, int(tuple(belief_sample_seeds)[0]))
        raise _SuccessorCaptured(successor)

    monkeypatch.setattr(explorer.search, "choose", capture_successor)
    with pytest.raises(_SuccessorCaptured) as captured:
        explorer.choose(executor, observation, actions, pass_action.handle)

    stack_identities = {
        str(item.get("identity"))
        for item in captured.value.successor.observation["objects"]
        if item.get("zone") == "STACK"
    }
    assert ("Curiosity" in stack_identities) is (opponent_mana_profile == "blue_red_available")
    assert state_hash(state) == before_hash
    assert state.rng_streams == before_rng_streams


def test_executor_constructor_rejects_invalid_explicit_opponent_profile() -> None:
    state, _executor = new_game(PLAYERS, "stage3-profile-clone-invalid")
    with pytest.raises(UnsupportedCapability, match="unsupported opponent mana profile"):
        GameExecutor(
            deepcopy(state),
            "stage3-profile-clone-invalid",
            opponent_mana_profile="not-a-profile",
        )


def test_constructor_profile_does_not_weaken_replay_history_setter_guard() -> None:
    state, _executor = new_game(PLAYERS, "stage3-profile-clone-history-guard")
    state.replay_commands.append({"operation": "test-only-recorded-command", "arguments": {}})
    clone = GameExecutor(
        deepcopy(state),
        "stage3-profile-clone-history-guard",
        opponent_mana_profile="no_known_colors",
    )

    assert clone.opponent_mana_profile == "no_known_colors"
    with pytest.raises(
        IllegalAction,
        match="opponent mana profile cannot change after replay recording begins",
    ):
        clone.opponent_mana_profile = "blue_red_available"


def test_constructor_nondefault_profile_synchronizes_existing_replay_and_replays() -> None:
    seed = "stage3-profile-clone-constructor-replay-sync"
    state, _setup = new_game(PLAYERS, seed)
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    state.turn.phase = "PRECOMBAT_MAIN"
    state.turn.step = "PRECOMBAT_MAIN"
    for symbol in ("W", "U", "B", "R", "G", "C"):
        state.players["P0"].mana_pool[symbol] = 0
    state.players["P0"].mana_pool["U"] = 2
    add_card(_setup, specs["Exotic Orchard"], Zone.BATTLEFIELD, owner="P0")
    add_card(_setup, specs["Fellwar Stone"], Zone.BATTLEFIELD, owner="P0")
    creature = add_card(_setup, specs["Dualcaster Mage"], Zone.BATTLEFIELD, owner="P0")
    curiosity = add_card(_setup, specs["Curiosity"], Zone.HAND, owner="P0")
    spell_pierce = add_card(_setup, specs["Spell Pierce"], Zone.HAND, owner="P0")
    snapshot = state_to_data(state)
    assert "execution_context" not in snapshot
    state.replay_initial_state = snapshot

    executor = GameExecutor(
        state,
        seed,
        opponent_mana_profile="no_known_colors",
    )
    provider = _CapturingCounterProvider(_production_provider(), [])
    executor.bind_strategic_choice_provider(provider, controlled_player_id="P0")
    target = executor.cast(
        "P0",
        curiosity.object_id,
        targets=(TargetRef(creature.object_id),),
    )
    executor.cast(
        "P0",
        spell_pierce.object_id,
        targets=(TargetRef(target.object_id),),
    )
    assert sum(state.players["P0"].mana_pool.values()) == 0
    _resolve_top(executor)

    assert executor.opponent_mana_profile == "no_known_colors"
    assert len(provider.requests) == 1
    assert provider.requests[0].payment_result.feasible is False
    assert _counter_outcome(state) == "DECLINE"
    assert target.object_id not in state.stack
    body = transcript(state, seed=executor.seed)
    assert body["initial_state"]["execution_context"] == {
        "opponent_mana_profile": "no_known_colors"
    }
    replayed = validate_replay(body)
    assert state_hash(replayed) == state_hash(state)
