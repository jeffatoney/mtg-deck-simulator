"""Fail-closed broker coverage and hidden-state boundary tests."""

from __future__ import annotations

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import UnsupportedCapability
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import Zone
from mtg_policy.broker import ActionBroker

PLAYERS = ("P0", "P1", "P2", "P3")


def scenario(seed: str):
    state, executor = new_game(PLAYERS, seed)
    for symbol in ("W", "U", "B", "R", "G", "C"):
        state.players["P0"].mana_pool[symbol] = 30
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    return state, executor, specs


def pass_all(executor) -> None:
    for _ in PLAYERS:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def test_broker_omits_casts_and_activations_without_execution_support() -> None:
    _, executor, specs = scenario("fail-closed-actions")
    add_card(executor, specs["Aetherize"], Zone.HAND)
    add_card(executor, specs["Fact or Fiction"], Zone.HAND)
    add_card(executor, specs["Shivan Reef"], Zone.BATTLEFIELD)

    _, actions = ActionBroker(executor, "P0").refresh()

    casts = {(action.identity, action.metadata.get("mode")) for action in actions if action.kind == "CAST"}
    assert ("Fact or Fiction", "default") in casts
    assert all(identity != "Aetherize" for identity, _mode in casts)

    shivan = [
        action
        for action in actions
        if action.kind == "ACTIVATE" and action.identity == "Shivan Reef"
    ]
    assert len(shivan) == 1
    assert "ADD_MANA" in shivan[0].tags
    assert "ADD_CHOSEN_MANA_AND_DAMAGE_SELF" not in shivan[0].tags


def test_broker_enumerates_both_explicit_opt_scry_choices() -> None:
    _, executor, specs = scenario("opt-choices")
    add_card(executor, specs["Opt"], Zone.HAND)
    add_card(executor, specs["Island"], Zone.LIBRARY)

    _, actions = ActionBroker(executor, "P0").refresh()
    opt = [action for action in actions if action.kind == "CAST" and action.identity == "Opt"]

    assert len(opt) == 2
    assert {action.metadata.get("scry_to_bottom") for action in opt} == {False, True}


def tutor_actions(zone: Zone):
    state, executor, specs = scenario(f"tutor-{zone.value}")
    add_card(executor, specs["Dizzy Spell"], Zone.HAND)
    add_card(executor, specs["Sol Ring"], zone)
    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()
    tutors = [
        action
        for action in actions
        if action.kind == "ACTIVATE_HAND" and action.identity == "Dizzy Spell"
    ]
    return state, executor, broker, observation, tutors


def test_tutor_action_descriptions_do_not_depend_on_current_hidden_library_contents() -> None:
    _, _, _, _, in_library = tutor_actions(Zone.LIBRARY)
    state, executor, broker, observation, absent = tutor_actions(Zone.GRAVEYARD)

    assert {action.metadata.get("tutor_identity") for action in in_library} == {
        action.metadata.get("tutor_identity") for action in absent
    }

    prefer_ring = next(
        action for action in absent if action.metadata.get("tutor_identity") == "Sol Ring"
    )
    broker.execute(int(observation["generation"]), prefer_ring.handle)
    pass_all(executor)

    assert not [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.zone is Zone.HAND
        and obj.current_characteristics.get("name") == "Sol Ring"
    ]
    assert any(
        choice.kind == "TRANSMUTE" and choice.selected == "FAIL_TO_FIND"
        for choice in state.choices
    )


def test_unverified_automatic_battlefield_behavior_is_a_hard_broker_failure() -> None:
    _, executor, specs = scenario("unsafe-static")
    add_card(executor, specs["Psychosis Crawler"], Zone.BATTLEFIELD)

    with pytest.raises(UnsupportedCapability, match="unverified automatic behavior"):
        ActionBroker(executor, "P0").refresh()


def test_pending_commander_return_choice_suppresses_priority_actions() -> None:
    state, executor, specs = scenario("commander-choice")
    commander = add_card(
        executor,
        specs["Malcolm, Keen-Eyed Navigator"],
        Zone.EXILE,
        commander=True,
    )
    executor.check_state_based_actions()

    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()

    assert {action.kind for action in actions} == {"COMMANDER_RETURN"}
    assert {action.metadata["destination"] for action in actions} == {
        "COMMAND",
        Zone.EXILE.value,
    }
    return_action = next(
        action for action in actions if action.metadata["destination"] == "COMMAND"
    )
    broker.execute(int(observation["generation"]), return_action.handle)

    successors = [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.zone is Zone.COMMAND
        and obj.component_card_instance_ids == commander.component_card_instance_ids
    ]
    assert len(successors) == 1
    assert not state.pending_commander_choices
