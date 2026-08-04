"""Executable coverage for X spells, artifact interaction, and cast-origin counters."""

from __future__ import annotations

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import GameObject, TargetRef, Zone


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


def active_permanent(state, name: str, controller: str = "P0") -> GameObject:
    return next(
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.zone is Zone.BATTLEFIELD
        and obj.controller == controller
        and obj.current_characteristics.get("name") == name
    )


def opponent_spell(executor, specs, name: str, **cast_options):
    executor.state.turn.active_player_id = "P1"
    executor.state.turn.priority_holder_id = "P1"
    card = add_card(executor, specs[name], Zone.HAND, owner="P1")
    spell = executor.cast("P1", card.object_id, **cast_options)
    executor.pass_priority("P1")
    return spell


def test_by_force_requires_x_targets_and_destroys_each_selected_artifact() -> None:
    state, executor, specs = funded_game("by-force")
    first = add_card(executor, specs["Sol Ring"], Zone.BATTLEFIELD, owner="P1")
    second = add_card(executor, specs["Mind Stone"], Zone.BATTLEFIELD, owner="P1")
    spell = add_card(executor, specs["By Force"], Zone.HAND)

    executor.cast(
        "P0",
        spell.object_id,
        (TargetRef(first.object_id), TargetRef(second.object_id)),
        x_value=2,
    )
    pass_all(executor)

    assert first.retired and second.retired
    assert (
        sum(
            1
            for obj in state.objects.values()
            if not obj.retired and obj.zone is Zone.GRAVEYARD and obj.owner == "P1"
        )
        == 2
    )

    invalid_state, invalid_executor, invalid_specs = funded_game("by-force-invalid")
    invalid_first = add_card(
        invalid_executor, invalid_specs["Sol Ring"], Zone.BATTLEFIELD, owner="P1"
    )
    invalid_second = add_card(
        invalid_executor, invalid_specs["Mind Stone"], Zone.BATTLEFIELD, owner="P1"
    )
    invalid_spell = add_card(invalid_executor, invalid_specs["By Force"], Zone.HAND)
    mana_before = dict(invalid_state.players["P0"].mana_pool)

    with pytest.raises(IllegalAction, match="targets must equal"):
        invalid_executor.cast(
            "P0",
            invalid_spell.object_id,
            (TargetRef(invalid_first.object_id), TargetRef(invalid_second.object_id)),
            x_value=1,
        )

    assert invalid_spell.zone is Zone.HAND and not invalid_spell.retired
    assert invalid_state.players["P0"].mana_pool == mana_before


def test_curse_of_the_swine_exiles_x_creatures_and_creates_one_boar_each() -> None:
    state, executor, specs = funded_game("curse-of-the-swine")
    first = add_card(executor, specs["Wily Goblin"], Zone.BATTLEFIELD, owner="P1")
    second = add_card(executor, specs["Spectral Sailor"], Zone.BATTLEFIELD, owner="P1")
    spell = add_card(executor, specs["Curse of the Swine"], Zone.HAND)

    executor.cast(
        "P0",
        spell.object_id,
        (TargetRef(first.object_id), TargetRef(second.object_id)),
        x_value=2,
    )
    pass_all(executor)

    assert first.retired and second.retired
    assert (
        sum(
            1
            for obj in state.objects.values()
            if not obj.retired
            and obj.zone is Zone.EXILE
            and obj.owner == "P1"
            and obj.current_characteristics.get("name") in {"Wily Goblin", "Spectral Sailor"}
        )
        == 2
    )
    boars = [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.zone is Zone.BATTLEFIELD
        and obj.controller == "P1"
        and obj.current_characteristics.get("name") == "Boar"
    ]
    assert len(boars) == 2
    assert all(
        obj.current_characteristics.get("power") == 2
        and obj.current_characteristics.get("toughness") == 2
        for obj in boars
    )


def test_resculpt_exiles_the_target_and_creates_the_correct_elemental() -> None:
    state, executor, specs = funded_game("resculpt")
    target = add_card(executor, specs["Sol Ring"], Zone.BATTLEFIELD, owner="P1")
    spell = add_card(executor, specs["Resculpt"], Zone.HAND)

    executor.cast("P0", spell.object_id, (TargetRef(target.object_id),))
    pass_all(executor)

    assert target.retired
    elemental = active_permanent(state, "Elemental", controller="P1")
    assert elemental.current_characteristics.get("power") == 4
    assert elemental.current_characteristics.get("toughness") == 4
    assert set(elemental.current_characteristics.get("colors", ())) == {"U", "R"}


def test_spectral_sailor_casts_and_its_activated_ability_draws() -> None:
    state, executor, specs = funded_game("spectral-sailor")
    card = add_card(executor, specs["Spectral Sailor"], Zone.HAND)
    add_card(executor, specs["Island"], Zone.LIBRARY)

    executor.cast("P0", card.object_id)
    pass_all(executor)
    sailor = active_permanent(state, "Spectral Sailor")
    executor.activate("P0", sailor.object_id, "sailor:draw")
    pass_all(executor)

    assert any(
        not obj.retired
        and obj.zone is Zone.HAND
        and obj.owner == "P0"
        and obj.current_characteristics.get("name") == "Island"
        for obj in state.objects.values()
    )


def test_vandalblast_executes_target_and_overload_modes() -> None:
    target_state, target_executor, target_specs = funded_game("vandalblast-target")
    selected = add_card(target_executor, target_specs["Sol Ring"], Zone.BATTLEFIELD, owner="P1")
    unaffected = add_card(target_executor, target_specs["Mind Stone"], Zone.BATTLEFIELD, owner="P1")
    target_spell = add_card(target_executor, target_specs["Vandalblast"], Zone.HAND)

    target_executor.cast(
        "P0", target_spell.object_id, (TargetRef(selected.object_id),), mode="target"
    )
    pass_all(target_executor)

    assert selected.retired
    assert not unaffected.retired and unaffected.zone is Zone.BATTLEFIELD

    state, executor, specs = funded_game("vandalblast-overload")
    opponent_first = add_card(executor, specs["Sol Ring"], Zone.BATTLEFIELD, owner="P1")
    opponent_second = add_card(executor, specs["Mind Stone"], Zone.BATTLEFIELD, owner="P1")
    controlled = add_card(executor, specs["Arcane Signet"], Zone.BATTLEFIELD, owner="P0")
    spell = add_card(executor, specs["Vandalblast"], Zone.HAND)

    executor.cast("P0", spell.object_id, mode="overload")
    pass_all(executor)

    assert opponent_first.retired and opponent_second.retired
    assert not controlled.retired and controlled.zone is Zone.BATTLEFIELD


def test_wash_away_uses_cast_origin_for_normal_mode_and_cleave_counters_any_spell() -> None:
    state, executor, specs = funded_game("wash-away-normal")
    state.turn.active_player_id = "P1"
    state.turn.priority_holder_id = "P1"
    commander = add_card(
        executor,
        specs["Breeches, Brazen Plunderer"],
        Zone.COMMAND,
        owner="P1",
        commander=True,
    )
    target = executor.cast("P1", commander.object_id)
    assert target.current_characteristics.get("cast_from_zone") == Zone.COMMAND.value
    executor.pass_priority("P1")
    wash = add_card(executor, specs["Wash Away"], Zone.HAND)

    executor.cast("P0", wash.object_id, (TargetRef(target.object_id),), mode="normal")
    pass_all(executor)

    assert target.retired

    cleave_state, cleave_executor, cleave_specs = funded_game("wash-away-cleave")
    hand_spell = opponent_spell(
        cleave_executor,
        cleave_specs,
        "Opt",
        choices={"scry_to_bottom": False},
    )
    assert hand_spell.current_characteristics.get("cast_from_zone") == Zone.HAND.value
    cleave = add_card(cleave_executor, cleave_specs["Wash Away"], Zone.HAND)

    cleave_executor.cast("P0", cleave.object_id, (TargetRef(hand_spell.object_id),), mode="cleave")
    pass_all(cleave_executor)

    assert hand_spell.retired
    assert not any(
        not obj.retired and obj.zone is Zone.STACK for obj in cleave_state.objects.values()
    )
