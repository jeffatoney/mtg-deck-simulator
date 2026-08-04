"""Direct production-path evidence for Path of Ancestry marked mana."""

from __future__ import annotations

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.hashing import state_hash
from mtg_kernel.land_actions import play_land
from mtg_kernel.models import Zone
from mtg_kernel.phase_b_marked_mana import MARKED_COMMANDER_MANA_KIND

PLAYERS = ("P0", "P1")
MANA_SYMBOLS = ("W", "U", "B", "R", "G", "C")


def game_with_commanders(seed: str):
    state, executor = new_game(PLAYERS, seed)
    for player in state.players.values():
        player.mana_pool.update({symbol: 0 for symbol in MANA_SYMBOLS})
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    add_card(
        executor,
        specs["Malcolm, Keen-Eyed Navigator"],
        Zone.COMMAND,
        owner="P0",
        commander=True,
    )
    add_card(
        executor,
        specs["Breeches, Brazen Plunderer"],
        Zone.COMMAND,
        owner="P0",
        commander=True,
    )
    return state, executor, specs


def pass_all(executor) -> None:
    for _ in PLAYERS:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def marked_records(state):
    return [
        record
        for record in state.continuous_effects
        if record.get("kind") == MARKED_COMMANDER_MANA_KIND
    ]


def test_path_of_ancestry_enters_tapped_and_marked_mana_triggers_scry() -> None:
    state, executor, specs = game_with_commanders("runtime-twenty-seven-path")
    path_card = add_card(executor, specs["Path of Ancestry"], Zone.HAND, owner="P0")
    path = play_land(executor, "P0", path_card.object_id)
    assert path.permanent_status is not None
    assert path.permanent_status["tap"] == "TAPPED"

    path.permanent_status["tap"] = "UNTAPPED"
    state.players["P0"].mana_pool["C"] = 2
    executor.activate("P0", path.object_id, "path:mana", choices={"mana_color": "R"})
    assert state.players["P0"].mana_pool == {
        "W": 0,
        "U": 0,
        "B": 0,
        "R": 1,
        "G": 0,
        "C": 2,
    }
    assert len(marked_records(state)) == 1

    bottom = add_card(executor, specs["Island"], Zone.LIBRARY, owner="P0")
    top = add_card(executor, specs["Opt"], Zone.LIBRARY, owner="P0")
    pirate = add_card(executor, specs["Lightning-Rig Crew"], Zone.HAND, owner="P0")
    spell = executor.cast("P0", pirate.object_id, choices={"scry_to_bottom": True})

    assert state.stack[-1] != spell.object_id
    trigger = state.objects[state.stack[-1]]
    assert trigger.current_characteristics["ability"]["ability_id"] == "path:spent"
    assert not marked_records(state)

    pass_all(executor)
    library = state.zones["LIBRARY:P0"]
    assert library[0] == top.object_id
    assert library[-1] == bottom.object_id
    scry_choice = next(choice for choice in state.choices if choice.kind == "SCRY_1")
    assert scry_choice.selected == "BOTTOM"


def test_path_of_ancestry_requires_explicit_scry_choice_atomically() -> None:
    state, executor, specs = game_with_commanders("runtime-twenty-seven-path-atomic")
    path = add_card(executor, specs["Path of Ancestry"], Zone.BATTLEFIELD, owner="P0")
    state.players["P0"].mana_pool["C"] = 2
    executor.activate("P0", path.object_id, "path:mana", choices={"mana_color": "R"})
    pirate = add_card(executor, specs["Lightning-Rig Crew"], Zone.HAND, owner="P0")
    before = state_hash(state)

    with pytest.raises(IllegalAction, match="explicit scry choice"):
        executor.cast("P0", pirate.object_id)

    assert state_hash(state) == before
    assert state.objects[pirate.object_id].zone is Zone.HAND
    assert len(marked_records(state)) == 1
    assert state.players["P0"].mana_pool["C"] == 2
    assert state.players["P0"].mana_pool["R"] == 1


def test_path_marked_mana_is_consumed_without_trigger_for_nonshared_creature() -> None:
    state, executor, specs = game_with_commanders("runtime-twenty-seven-nonshared")
    path = add_card(executor, specs["Path of Ancestry"], Zone.BATTLEFIELD, owner="P0")
    state.players["P0"].mana_pool["C"] = 4
    executor.activate("P0", path.object_id, "path:mana", choices={"mana_color": "U"})
    crawler = add_card(executor, specs["Psychosis Crawler"], Zone.HAND, owner="P0")

    spell = executor.cast("P0", crawler.object_id)

    assert state.stack == [spell.object_id]
    assert not marked_records(state)
    assert not any(
        obj.current_characteristics.get("ability", {}).get("ability_id") == "path:spent"
        and not obj.retired
        for obj in state.objects.values()
    )
