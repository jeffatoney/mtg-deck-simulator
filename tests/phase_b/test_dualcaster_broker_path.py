"""Phase B broker-path coverage for Dualcaster Mage and Twinflame."""

from __future__ import annotations

from collections.abc import Callable

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.engine import GameExecutor
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import CopyKind, ObjectKind, Zone
from mtg_policy import ActionBroker
from mtg_policy.broker import ObservedAction


def funded_game() -> tuple[object, GameExecutor, dict[str, object]]:
    state, executor = new_game(("P0", "P1"), seed="phase-b-dualcaster-broker")
    for player in state.players.values():
        for symbol in ("W", "U", "B", "R", "G", "C"):
            player.mana_pool[symbol] = 30
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    return state, executor, specs


def execute_matching(
    executor: GameExecutor,
    player_id: str,
    predicate: Callable[[ObservedAction], bool],
) -> tuple[dict[str, object], ObservedAction]:
    broker = ActionBroker(executor, player_id)
    observation, actions = broker.refresh()
    selected = next(action for action in actions if predicate(action))
    broker.execute(int(observation["generation"]), selected.handle)
    return observation, selected


def pass_priority_round(executor: GameExecutor) -> None:
    players = [player.player_id for player in executor.state.players.values() if player.in_game]
    for _ in players:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        execute_matching(executor, holder, lambda action: action.kind == "PASS_PRIORITY")


def test_dualcaster_twinflame_execute_through_full_deck_broker_path() -> None:
    state, executor, specs = funded_game()
    add_card(executor, specs["Island"], Zone.LIBRARY)
    add_card(executor, specs["Mountain"], Zone.LIBRARY)
    add_card(executor, specs["Opt"], Zone.HAND)
    dualcaster = add_card(executor, specs["Dualcaster Mage"], Zone.HAND)
    add_card(executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD)
    add_card(executor, specs["Glint-Horn Buccaneer"], Zone.BATTLEFIELD)
    twinflame = add_card(executor, specs["Twinflame"], Zone.HAND)

    _, opt_action = execute_matching(
        executor,
        "P0",
        lambda action: action.kind == "CAST" and action.identity == "Opt",
    )
    assert opt_action.identity == "Opt"
    original = state.objects[state.stack[-1]]
    assert original.current_characteristics["name"] == "Opt"

    observation, dualcaster_action = execute_matching(
        executor,
        "P0",
        lambda action: action.kind == "CAST" and action.identity == "Dualcaster Mage",
    )
    opt_handle = next(
        item["handle"]
        for item in observation["objects"]
        if item.get("identity") == "Opt" and item.get("zone") == "STACK"
    )
    assert dualcaster_action.metadata["trigger_target_handles"] == {"dualcaster:etb": opt_handle}
    assert dualcaster.zone is Zone.HAND

    pass_priority_round(executor)
    trigger = state.objects[state.stack[-1]]
    assert trigger.object_kind is ObjectKind.TRIGGERED_ABILITY
    pass_priority_round(executor)
    spell_copy = state.objects[state.stack[-1]]
    assert spell_copy.copy_kind is CopyKind.SPELL_COPY
    assert spell_copy.was_cast is False
    assert not spell_copy.component_card_instance_ids
    pass_priority_round(executor)
    assert spell_copy.retired
    pass_priority_round(executor)
    assert not state.stack

    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()
    desired_handles = {
        item["handle"]
        for item in observation["objects"]
        if item.get("identity") in {"Malcolm, Keen-Eyed Navigator", "Glint-Horn Buccaneer"}
        and item.get("zone") == "BATTLEFIELD"
    }
    twinflame_action = next(
        action
        for action in actions
        if action.kind == "CAST"
        and action.identity == "Twinflame"
        and action.target_count == 2
        and set(action.metadata.get("target_handles", ())) == desired_handles
    )
    broker.execute(int(observation["generation"]), twinflame_action.handle)
    assert twinflame_action.identity == "Twinflame"
    assert twinflame.zone is Zone.HAND
    pass_priority_round(executor)

    tokens = [
        obj
        for obj in state.objects.values()
        if not obj.retired and obj.copy_kind is CopyKind.TOKEN_COPY
    ]
    assert len(tokens) == 2
    assert all(not token.component_card_instance_ids for token in tokens)
    assert len(state.delayed_triggers) == 2

    executor.begin_step("END")
    pass_priority_round(executor)
    pass_priority_round(executor)
    assert not [
        obj
        for obj in state.objects.values()
        if not obj.retired and obj.copy_kind is CopyKind.TOKEN_COPY
    ]
    assert all(token.retired for token in tokens)
