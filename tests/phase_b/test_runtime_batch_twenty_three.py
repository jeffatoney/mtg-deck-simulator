"""Direct production-path evidence for Arcane Denial delayed draws."""

from __future__ import annotations

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import TargetRef, Zone

PLAYERS = ("P0", "P1")
MANA_SYMBOLS = ("W", "U", "B", "R", "G", "C")


def game_with_exact_mana(seed: str):
    state, executor = new_game(PLAYERS, seed)
    for player in state.players.values():
        player.mana_pool.update({symbol: 0 for symbol in MANA_SYMBOLS})
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    return state, executor, specs


def pass_all(executor) -> None:
    for _ in PLAYERS:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def cast_arcane_denial(state, executor, specs) -> str:
    state.players["P0"].mana_pool.update({"U": 1, "C": 1})
    state.players["P1"].mana_pool.update({"U": 1})
    target = add_card(executor, specs["Opt"], Zone.HAND, owner="P1")
    denial = add_card(executor, specs["Arcane Denial"], Zone.HAND, owner="P0")

    state.turn.priority_holder_id = "P1"
    target_spell = executor.cast("P1", target.object_id)
    executor.pass_priority("P1")
    executor.cast("P0", denial.object_id, targets=(TargetRef(target_spell.object_id),))
    pass_all(executor)

    assert target_spell.retired
    assert len(state.delayed_triggers) == 1
    return state.delayed_triggers[0]


def test_arcane_denial_counters_and_executes_explicit_next_upkeep_draw_count() -> None:
    state, executor, specs = game_with_exact_mana("runtime-twenty-three-draw-two")
    for _ in range(2):
        add_card(executor, specs["Island"], Zone.LIBRARY, owner="P1")
    add_card(executor, specs["Island"], Zone.LIBRARY, owner="P0")
    trigger_id = cast_arcane_denial(state, executor, specs)

    state.turn.number += 1
    state.turn.active_player_id = "P1"
    executor.begin_step(
        "UPKEEP",
        choices={
            "delayed_trigger_choices": {
                trigger_id: {
                    "arcane_denial_draw_count": {"player_id": "P1", "count": 2}
                }
            }
        },
    )
    assert trigger_id not in state.delayed_triggers
    assert state.stack == [trigger_id]
    pass_all(executor)

    assert len(state.zones.get("HAND:P1", [])) == 2
    assert len(state.zones.get("HAND:P0", [])) == 1
    assert any(
        choice.kind == "ARCANE_DENIAL_DRAW_COUNT"
        and choice.player_id == "P1"
        and choice.selected == 2
        for choice in state.choices
    )
    assert sum(event.kind == "CARD_DRAWN" for event in state.events) == 3


def test_arcane_denial_waits_for_next_turn_upkeep_and_allows_zero_cards() -> None:
    state, executor, specs = game_with_exact_mana("runtime-twenty-three-draw-zero")
    add_card(executor, specs["Island"], Zone.LIBRARY, owner="P1")
    add_card(executor, specs["Island"], Zone.LIBRARY, owner="P0")
    trigger_id = cast_arcane_denial(state, executor, specs)

    executor.begin_step("END")
    assert state.delayed_triggers == [trigger_id]
    assert state.stack == []

    state.turn.number += 1
    state.turn.active_player_id = "P1"
    executor.begin_step(
        "UPKEEP",
        choices={
            "delayed_trigger_choices": {
                trigger_id: {
                    "arcane_denial_draw_count": {"player_id": "P1", "count": 0}
                }
            }
        },
    )
    pass_all(executor)

    assert len(state.zones.get("HAND:P1", [])) == 0
    assert len(state.zones.get("HAND:P0", [])) == 1
    assert any(
        choice.kind == "ARCANE_DENIAL_DRAW_COUNT" and choice.selected == 0
        for choice in state.choices
    )


def test_arcane_denial_missing_draw_choice_fails_closed_atomically() -> None:
    state, executor, specs = game_with_exact_mana("runtime-twenty-three-missing-choice")
    add_card(executor, specs["Island"], Zone.LIBRARY, owner="P1")
    add_card(executor, specs["Island"], Zone.LIBRARY, owner="P0")
    trigger_id = cast_arcane_denial(state, executor, specs)

    state.turn.number += 1
    state.turn.active_player_id = "P1"
    executor.begin_step("UPKEEP")
    assert state.stack == [trigger_id]
    executor.pass_priority("P1")
    with pytest.raises(IllegalAction, match="explicit draw-count choice"):
        executor.pass_priority("P0")

    assert state.stack == [trigger_id]
    assert len(state.zones.get("HAND:P1", [])) == 0
    assert len(state.zones.get("HAND:P0", [])) == 0
