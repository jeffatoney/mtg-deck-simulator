"""Executable coverage for conditional counters and simple exact-deck spells."""

from __future__ import annotations

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import TargetRef, Zone


def funded_game(seed: str):
    state, executor = new_game(("P0", "P1"), seed)
    for player in state.players.values():
        for symbol in ("W", "U", "B", "R", "G", "C"):
            player.mana_pool[symbol] = 30
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    return state, executor, specs


def pass_all(executor) -> None:
    for _ in range(2):
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def opponent_spell(executor, specs, name: str, **cast_options):
    executor.state.turn.active_player_id = "P1"
    executor.state.turn.priority_holder_id = "P1"
    card = add_card(executor, specs[name], Zone.HAND, owner="P1")
    spell = executor.cast("P1", card.object_id, **cast_options)
    executor.pass_priority("P1")
    return spell


def test_negate_counters_a_noncreature_spell_and_rejects_a_creature_spell() -> None:
    state, executor, specs = funded_game("negate-valid")
    target = opponent_spell(executor, specs, "Opt", choices={"scry_to_bottom": False})
    negate = add_card(executor, specs["Negate"], Zone.HAND)

    executor.cast("P0", negate.object_id, (TargetRef(target.object_id),))
    pass_all(executor)

    assert target.retired
    assert not any(not obj.retired and obj.zone is Zone.STACK for obj in state.objects.values())

    illegal_state, illegal_executor, illegal_specs = funded_game("negate-invalid")
    creature_spell = opponent_spell(illegal_executor, illegal_specs, "Wily Goblin")
    illegal_negate = add_card(illegal_executor, illegal_specs["Negate"], Zone.HAND)
    mana_before = dict(illegal_state.players["P0"].mana_pool)

    with pytest.raises(IllegalAction, match="counter predicate"):
        illegal_executor.cast(
            "P0", illegal_negate.object_id, (TargetRef(creature_spell.object_id),)
        )

    assert not illegal_negate.retired and illegal_negate.zone is Zone.HAND
    assert not creature_spell.retired and creature_spell.zone is Zone.STACK
    assert illegal_state.players["P0"].mana_pool == mana_before


@pytest.mark.parametrize(
    ("mode", "target_name"),
    (("small", "Wily Goblin"), ("red_green", "Niv-Mizzet, the Firemind")),
)
def test_change_the_equation_executes_both_counter_modes(mode: str, target_name: str) -> None:
    state, executor, specs = funded_game(f"change-equation-{mode}")
    target = opponent_spell(executor, specs, target_name)
    counter = add_card(executor, specs["Change the Equation"], Zone.HAND)

    executor.cast("P0", counter.object_id, (TargetRef(target.object_id),), mode=mode)
    pass_all(executor)

    assert target.retired
    assert not any(not obj.retired and obj.zone is Zone.STACK for obj in state.objects.values())


def test_change_the_equation_small_mode_rejects_a_large_spell_without_mutation() -> None:
    state, executor, specs = funded_game("change-equation-invalid")
    target = opponent_spell(executor, specs, "Niv-Mizzet, the Firemind")
    counter = add_card(executor, specs["Change the Equation"], Zone.HAND)
    mana_before = dict(state.players["P0"].mana_pool)

    with pytest.raises(IllegalAction, match="counter predicate"):
        executor.cast(
            "P0",
            counter.object_id,
            (TargetRef(target.object_id),),
            mode="small",
        )

    assert not counter.retired and counter.zone is Zone.HAND
    assert not target.retired and target.zone is Zone.STACK
    assert state.players["P0"].mana_pool == mana_before


def test_echoing_truth_returns_all_nonland_permanents_with_the_same_name() -> None:
    state, executor, specs = funded_game("echoing-truth")
    first = add_card(executor, specs["Sol Ring"], Zone.BATTLEFIELD, owner="P1")
    add_card(executor, specs["Sol Ring"], Zone.BATTLEFIELD, owner="P1")
    unaffected = add_card(executor, specs["Mind Stone"], Zone.BATTLEFIELD, owner="P1")
    spell = add_card(executor, specs["Echoing Truth"], Zone.HAND)

    executor.cast("P0", spell.object_id, (TargetRef(first.object_id),))
    pass_all(executor)

    returned = [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.zone is Zone.HAND
        and obj.owner == "P1"
        and obj.current_characteristics.get("name") == "Sol Ring"
    ]
    assert len(returned) == 2
    assert not unaffected.retired and unaffected.zone is Zone.BATTLEFIELD


def test_expedite_grants_haste_and_draws_a_card() -> None:
    state, executor, specs = funded_game("expedite")
    creature = add_card(executor, specs["Wily Goblin"], Zone.BATTLEFIELD)
    add_card(executor, specs["Island"], Zone.LIBRARY)
    spell = add_card(executor, specs["Expedite"], Zone.HAND)

    executor.cast("P0", spell.object_id, (TargetRef(creature.object_id),))
    pass_all(executor)

    assert "Haste" in creature.current_characteristics.get("keywords", ())
    assert any(
        not obj.retired
        and obj.zone is Zone.HAND
        and obj.current_characteristics.get("name") == "Island"
        for obj in state.objects.values()
    )


def test_opt_scries_then_draws_through_the_shared_sequence_path() -> None:
    state, executor, specs = funded_game("opt")
    add_card(executor, specs["Island"], Zone.LIBRARY)
    add_card(executor, specs["Mountain"], Zone.LIBRARY)
    spell = add_card(executor, specs["Opt"], Zone.HAND)

    executor.cast("P0", spell.object_id, choices={"scry_to_bottom": True})
    pass_all(executor)

    assert any(choice.kind == "SCRY_1" for choice in state.choices)
    assert (
        len(
            [
                obj
                for obj in state.objects.values()
                if not obj.retired and obj.zone is Zone.HAND and obj.owner == "P0"
            ]
        )
        == 1
    )


def test_introduction_to_annihilation_exiles_and_lets_the_controller_draw() -> None:
    state, executor, specs = funded_game("introduction-annihilation")
    target = add_card(executor, specs["Sol Ring"], Zone.BATTLEFIELD, owner="P1")
    add_card(executor, specs["Island"], Zone.LIBRARY, owner="P1")
    spell = add_card(executor, specs["Introduction to Annihilation"], Zone.HAND)

    executor.cast("P0", spell.object_id, (TargetRef(target.object_id),))
    pass_all(executor)

    assert target.retired
    assert any(
        not obj.retired
        and obj.zone is Zone.EXILE
        and obj.owner == "P1"
        and obj.current_characteristics.get("name") == "Sol Ring"
        for obj in state.objects.values()
    )
    assert any(
        not obj.retired
        and obj.zone is Zone.HAND
        and obj.owner == "P1"
        and obj.current_characteristics.get("name") == "Island"
        for obj in state.objects.values()
    )
