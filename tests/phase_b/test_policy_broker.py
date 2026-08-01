from __future__ import annotations

import json

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.engine import GameExecutor
from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card
from mtg_kernel.land_actions import play_land
from mtg_kernel.models import GameState, PlayerState, TurnState, Zone
from mtg_policy.broker import ActionBroker


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
    encoded = json.dumps({"observation": observation, "actions": [action.__dict__ for action in actions]})
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
    encoded = json.dumps({"observation": observation, "actions": [action.__dict__ for action in actions]})
    assert hidden.object_id not in encoded
    assert hidden.component_card_instance_ids[0] not in encoded
    assert "Twinflame" not in encoded


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


def test_broker_does_not_offer_choice_incomplete_land_actions() -> None:
    _, executor, specs = scenario()
    add_card(executor, specs["Thriving Isle"], Zone.HAND)
    _, actions = ActionBroker(executor, "P0").refresh()
    assert not any(action.kind == "PLAY_LAND" for action in actions)
