"""Direct production-path evidence for Lazotep Plating."""

from __future__ import annotations

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card, add_external_public_object, new_game
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import TargetRef, Zone
from mtg_kernel.phase_b_runtime_effects_amass import HEXPROOF_EFFECT_KIND

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


def active_named(state, name: str, zone: Zone):
    return [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and not obj.ceased_to_exist
        and obj.zone is zone
        and obj.current_characteristics.get("name") == name
    ]


def add_army(executor, object_id: str):
    return add_external_public_object(
        executor,
        object_id,
        Zone.BATTLEFIELD,
        "P0",
        "P0",
        {
            "name": object_id,
            "card_types": ["Creature"],
            "subtypes": ["Zombie", "Army"],
            "colors": ["B"],
            "keywords": [],
            "abilities": [],
            "power": 1,
            "toughness": 1,
        },
    )


def test_lazotep_plating_amasses_and_protects_until_cleanup() -> None:
    state, executor, specs = game_with_exact_mana("runtime-twenty-six-lazotep")
    state.players["P0"].mana_pool.update({"U": 1, "C": 1})
    protected = add_card(executor, specs["Sol Ring"], Zone.BATTLEFIELD, owner="P0")
    plating = add_card(executor, specs["Lazotep Plating"], Zone.HAND, owner="P0")

    executor.cast("P0", plating.object_id)
    pass_all(executor)

    armies = active_named(state, "Zombie Army", Zone.BATTLEFIELD)
    assert len(armies) == 1
    army = armies[0]
    assert army.counters["+1/+1"] == 1
    assert army.current_characteristics["power"] == 1
    assert army.current_characteristics["toughness"] == 1
    assert any(
        record.get("kind") == HEXPROOF_EFFECT_KIND
        and record.get("player_id") == "P0"
        and record.get("protect_player") is True
        and record.get("protect_controlled_permanents") is True
        for record in state.continuous_effects
    )

    state.players["P1"].mana_pool.update({"R": 1, "C": 1})
    abrade = add_card(executor, specs["Abrade"], Zone.HAND, owner="P1")
    state.turn.priority_holder_id = "P1"
    before = state_hash(state)
    with pytest.raises(IllegalAction, match="illegal ARTIFACT target"):
        executor.cast(
            "P1",
            abrade.object_id,
            (TargetRef(protected.object_id),),
            mode="destroy",
        )
    assert state_hash(state) == before

    executor.cleanup()
    assert not any(
        record.get("kind") == HEXPROOF_EFFECT_KIND for record in state.continuous_effects
    )

    state.turn.priority_holder_id = "P1"
    executor.cast(
        "P1",
        abrade.object_id,
        (TargetRef(protected.object_id),),
        mode="destroy",
    )
    pass_all(executor)
    assert protected.retired
    assert active_named(state, "Sol Ring", Zone.GRAVEYARD)


def test_lazotep_plating_requires_explicit_choice_for_multiple_armies_atomically() -> None:
    state, executor, specs = game_with_exact_mana("runtime-twenty-six-choice-failure")
    state.players["P0"].mana_pool.update({"U": 1, "C": 1})
    first = add_army(executor, "external:first-army")
    second = add_army(executor, "external:second-army")
    plating = add_card(executor, specs["Lazotep Plating"], Zone.HAND, owner="P0")
    spell = executor.cast("P0", plating.object_id)
    executor.pass_priority("P0")
    before = state_hash(state)

    with pytest.raises(IllegalAction, match="explicit Army choice"):
        executor.pass_priority("P1")

    assert state_hash(state) == before
    assert spell.object_id in state.stack
    assert first.counters == {}
    assert second.counters == {}
    assert not state.continuous_effects

    state2, executor2, specs2 = game_with_exact_mana("runtime-twenty-six-choice-success")
    state2.players["P0"].mana_pool.update({"U": 1, "C": 1})
    first2 = add_army(executor2, "external:first-army")
    second2 = add_army(executor2, "external:second-army")
    plating2 = add_card(executor2, specs2["Lazotep Plating"], Zone.HAND, owner="P0")
    executor2.cast(
        "P0",
        plating2.object_id,
        choices={"amass_army_object_id": second2.object_id},
    )
    pass_all(executor2)

    assert first2.counters == {}
    assert first2.current_characteristics["power"] == 1
    assert second2.counters["+1/+1"] == 1
    assert second2.current_characteristics["power"] == 2
    assert state2.choices[-1].kind == "AMASS_ARMY"
    assert state2.choices[-1].selected == second2.object_id
