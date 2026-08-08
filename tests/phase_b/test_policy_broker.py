from __future__ import annotations

import json

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.engine import GameExecutor
from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card
from mtg_kernel.land_actions import play_land
from mtg_kernel.models import GameState, PlayerState, TurnState, Zone
from mtg_policy.broker import ActionBroker, ObservedAction
from mtg_policy.config import load_policy_matrix
from mtg_policy.standard import StandardPolicy


def scenario() -> tuple[GameState, GameExecutor, dict[str, object]]:
    state = GameState(
        "broker-test",
        {player: PlayerState(player) for player in ("P0", "P1", "P2", "P3")},
        TurnState("P0", priority_holder_id="P0"),
    )
    executor = GameExecutor(state, "broker-test")
    state.players["P0"].mana_pool["C"] = 3
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    return state, executor, specs


def _semantic_action(action: ObservedAction) -> tuple[object, ...]:
    return (
        action.kind,
        action.identity,
        action.mana_value,
        action.tags,
        action.target_count,
        json.dumps(action.metadata, sort_keys=True, separators=(",", ":")),
    )


def test_broker_probes_the_production_executor_without_mutating_live_state() -> None:
    state, executor, specs = scenario()
    island = add_card(executor, specs["Island"], Zone.HAND)
    ring = add_card(executor, specs["Sol Ring"], Zone.HAND)
    before_actions = tuple(state.actions)
    before_zones = {key: tuple(value) for key, value in state.zones.items()}

    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()

    assert tuple(state.actions) == before_actions
    assert {key: tuple(value) for key, value in state.zones.items()} == before_zones
    assert {action.kind for action in actions} >= {"PLAY_LAND", "CAST", "PASS_PRIORITY"}
    encoded = json.dumps(
        {"observation": observation, "actions": [action.__dict__ for action in actions]}
    )
    assert island.object_id not in encoded
    assert ring.object_id not in encoded
    assert island.component_card_instance_ids[0] not in encoded
    assert ring.component_card_instance_ids[0] not in encoded


def test_broker_handles_are_one_shot_and_state_bound() -> None:
    state, executor, specs = scenario()
    add_card(executor, specs["Island"], Zone.HAND)
    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()
    land = next(action for action in actions if action.kind == "PLAY_LAND")
    broker.execute(int(observation["generation"]), land.handle)
    assert any(action.kind == "PLAY_LAND" for action in state.actions)
    with pytest.raises(IllegalAction):
        broker.execute(int(observation["generation"]), land.handle)


def test_hidden_library_identity_never_enters_policy_observation_or_actions() -> None:
    _, executor, specs = scenario()
    hidden = add_card(executor, specs["Twinflame"], Zone.LIBRARY, visible_to=set())
    observation, actions = ActionBroker(executor, "P0").refresh()
    encoded = json.dumps(
        {"observation": observation, "actions": [action.__dict__ for action in actions]}
    )
    assert hidden.object_id not in encoded
    assert hidden.component_card_instance_ids[0] not in encoded
    assert "Twinflame" not in encoded


def test_standard_policy_tie_break_ignores_opaque_action_handles() -> None:
    policy = StandardPolicy(load_policy_matrix()[0])
    observation = {"generation": 1, "turn": 2}
    first = (
        ObservedAction("handle-a", "PLAY_LAND", "Island", 0, ("Land",), 0, {}),
        ObservedAction("handle-b", "PLAY_LAND", "Mountain", 0, ("Land",), 0, {}),
    )
    second = (
        ObservedAction("different-z", "PLAY_LAND", "Island", 0, ("Land",), 0, {}),
        ObservedAction("different-a", "PLAY_LAND", "Mountain", 0, ("Land",), 0, {}),
    )

    selected_first = policy.select_action(observation, first)
    selected_second = policy.select_action(observation, second)
    semantic_first = _semantic_action(
        next(action for action in first if action.handle == selected_first)
    )
    semantic_second = _semantic_action(
        next(action for action in second if action.handle == selected_second)
    )

    assert semantic_first == semantic_second


def test_hidden_only_state_change_cannot_change_selected_semantic_action() -> None:
    first_state, first_executor, first_specs = scenario()
    add_card(first_executor, first_specs["Island"], Zone.HAND)
    add_card(first_executor, first_specs["Mountain"], Zone.HAND)
    first_hidden = add_card(
        first_executor,
        first_specs["Twinflame"],
        Zone.LIBRARY,
        visible_to=set(),
    )

    second_state, second_executor, second_specs = scenario()
    add_card(second_executor, second_specs["Island"], Zone.HAND)
    add_card(second_executor, second_specs["Mountain"], Zone.HAND)
    second_hidden = add_card(
        second_executor,
        second_specs["Twinflame"],
        Zone.LIBRARY,
        visible_to=set(),
    )
    second_hidden.current_characteristics["private_test_marker"] = "hidden-only-change"

    first_observation, first_actions = ActionBroker(first_executor, "P0").refresh()
    second_observation, second_actions = ActionBroker(second_executor, "P0").refresh()

    assert first_hidden.object_id == second_hidden.object_id
    assert first_observation == second_observation
    assert sorted(_semantic_action(action) for action in first_actions) == sorted(
        _semantic_action(action) for action in second_actions
    )
    assert {action.handle for action in first_actions} != {
        action.handle for action in second_actions
    }

    policy = StandardPolicy(load_policy_matrix()[0])
    first_handle = policy.select_action(first_observation, first_actions)
    second_handle = policy.select_action(second_observation, second_actions)
    first_selected = next(action for action in first_actions if action.handle == first_handle)
    second_selected = next(action for action in second_actions if action.handle == second_handle)

    assert _semantic_action(first_selected) == _semantic_action(second_selected)
    assert first_state.terminal.status == second_state.terminal.status == "ACTIVE"


def test_land_play_uses_priority_and_records_as_enters_choice_before_entry() -> None:
    state, executor, specs = scenario()
    thriving = add_card(executor, specs["Thriving Isle"], Zone.HAND)
    state.turn.priority_holder_id = "P1"
    with pytest.raises(IllegalAction):
        play_land(executor, "P0", thriving.object_id, {"chosen_color": "R"})
    state.turn.priority_holder_id = "P0"
    permanent = play_land(executor, "P0", thriving.object_id, {"chosen_color": "R"})
    assert permanent.permanent_status is not None
    assert permanent.permanent_status["tap"] == "TAPPED"
    assert permanent.current_characteristics["chosen_color"] == "R"
    kinds = [event.kind for event in state.events]
    assert kinds.index("LAND_COLOR_CHOSEN") < kinds.index("LAND_PLAYED")


def test_broker_offers_only_complete_explicit_land_choice_variants() -> None:
    _, executor, specs = scenario()
    add_card(executor, specs["Thriving Isle"], Zone.HAND)
    _, actions = ActionBroker(executor, "P0").refresh()
    land_actions = [action for action in actions if action.kind == "PLAY_LAND"]
    assert {action.metadata.get("chosen_color") for action in land_actions} == {
        "W",
        "B",
        "R",
        "G",
    }
    assert len(land_actions) == 4
