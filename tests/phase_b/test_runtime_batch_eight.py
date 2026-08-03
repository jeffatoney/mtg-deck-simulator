"""Executable coverage for utility spells, cycling, and transmute cards."""

from __future__ import annotations

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import TargetRef, Zone
from mtg_kernel.phase_b_actions import activate_hand_ability
from mtg_policy import (
    ContextualEvaluator,
    PolicyStrategicChoiceProvider,
    load_evaluator_config,
    load_policy_matrix,
)

PLAYERS = ("P0", "P1")


def funded_game(seed: str):
    state, executor = new_game(PLAYERS, seed)
    for player in state.players.values():
        for symbol in ("W", "U", "B", "R", "G", "C"):
            player.mana_pool[symbol] = 30
    executor.bind_strategic_choice_provider(
        PolicyStrategicChoiceProvider(
            load_policy_matrix()[0],
            ContextualEvaluator(load_evaluator_config()),
        )
    )
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    return state, executor, specs


def pass_all(executor) -> None:
    for _ in PLAYERS:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def active_objects(
    state,
    *,
    name: str | None = None,
    zone: Zone | None = None,
    owner: str | None = None,
):
    values = [obj for obj in state.objects.values() if not obj.retired and not obj.ceased_to_exist]
    if name is not None:
        values = [obj for obj in values if obj.current_characteristics.get("name") == name]
    if zone is not None:
        values = [obj for obj in values if obj.zone is zone]
    if owner is not None:
        values = [obj for obj in values if obj.owner == owner]
    return values


def reset_pool(state, player_id: str = "P0", **mana: int) -> None:
    for symbol in ("W", "U", "B", "R", "G", "C"):
        state.players[player_id].mana_pool[symbol] = int(mana.get(symbol, 0))


def test_ash_barrens_mana_and_basic_landcycling_paths() -> None:
    mana_state, mana_executor, mana_specs = funded_game("ash-barrens-mana")
    barrens = add_card(mana_executor, mana_specs["Ash Barrens"], Zone.BATTLEFIELD)
    reset_pool(mana_state)

    mana_executor.activate("P0", barrens.object_id, "ash-barrens:c")

    assert mana_state.players["P0"].mana_pool["C"] == 1
    assert mana_state.stack == []

    state, executor, specs = funded_game("ash-barrens-landcycling")
    cycling = add_card(executor, specs["Ash Barrens"], Zone.HAND)
    add_card(executor, specs["Island"], Zone.LIBRARY)
    state.turn.phase = "COMBAT"

    activate_hand_ability(executor, "P0", cycling.object_id, "ash-barrens:basic-landcycling")
    pass_all(executor)

    assert active_objects(state, name="Ash Barrens", zone=Zone.GRAVEYARD)
    selected = [
        obj
        for obj in active_objects(state, zone=Zone.HAND, owner="P0")
        if obj.current_characteristics.get("name") in {"Island", "Mountain"}
    ]
    assert len(selected) == 1
    assert any(event.kind == "LIBRARY_SHUFFLED" for event in state.events)


def test_dizzy_spell_modifies_power_and_transmute_is_already_shared_runtime() -> None:
    state, executor, specs = funded_game("dizzy-spell")
    target = add_card(executor, specs["Wily Goblin"], Zone.BATTLEFIELD, owner="P1")
    spell = add_card(executor, specs["Dizzy Spell"], Zone.HAND)

    executor.cast("P0", spell.object_id, (TargetRef(target.object_id),))
    pass_all(executor)

    assert target.current_characteristics["power"] == -2
    assert target.current_characteristics["toughness"] == 1
    assert any(event.kind == "POWER_TOUGHNESS_MODIFIED" for event in state.events)


def test_muddle_the_mixture_counters_and_transmutes() -> None:
    state, executor, specs = funded_game("muddle-counter")
    add_card(executor, specs["Island"], Zone.LIBRARY, owner="P1")
    target_card = add_card(executor, specs["Opt"], Zone.HAND, owner="P1")
    muddle = add_card(executor, specs["Muddle the Mixture"], Zone.HAND)
    state.turn.active_player_id = "P1"
    state.turn.priority_holder_id = "P1"

    target_spell = executor.cast(
        "P1",
        target_card.object_id,
        choices={"scry_to_bottom": False},
    )
    executor.pass_priority("P1")
    executor.cast("P0", muddle.object_id, (TargetRef(target_spell.object_id),))
    pass_all(executor)

    assert target_spell.retired
    assert active_objects(state, name="Opt", zone=Zone.GRAVEYARD, owner="P1")

    transmute_state, transmute_executor, transmute_specs = funded_game("muddle-transmute")
    source = add_card(
        transmute_executor,
        transmute_specs["Muddle the Mixture"],
        Zone.HAND,
    )
    add_card(transmute_executor, transmute_specs["Arcane Signet"], Zone.LIBRARY)
    transmute_state.turn.phase = "PRECOMBAT_MAIN"

    activate_hand_ability(transmute_executor, "P0", source.object_id, "muddle:transmute")
    pass_all(transmute_executor)

    assert active_objects(
        transmute_state,
        name="Muddle the Mixture",
        zone=Zone.GRAVEYARD,
    )
    assert len(active_objects(transmute_state, name="Arcane Signet", zone=Zone.HAND)) == 1


def test_rebuild_returns_all_artifacts_while_cycling_remains_available() -> None:
    state, executor, specs = funded_game("rebuild")
    add_card(executor, specs["Arcane Signet"], Zone.BATTLEFIELD, owner="P0")
    add_card(executor, specs["Sol Ring"], Zone.BATTLEFIELD, owner="P1")
    add_card(executor, specs["Mind Stone"], Zone.BATTLEFIELD, owner="P1")
    spell = add_card(executor, specs["Rebuild"], Zone.HAND)

    executor.cast("P0", spell.object_id)
    pass_all(executor)

    assert len(active_objects(state, name="Arcane Signet", zone=Zone.HAND, owner="P0")) == 1
    assert len(active_objects(state, name="Sol Ring", zone=Zone.HAND, owner="P1")) == 1
    assert len(active_objects(state, name="Mind Stone", zone=Zone.HAND, owner="P1")) == 1
    assert not [
        obj
        for obj in active_objects(state, zone=Zone.BATTLEFIELD)
        if "Artifact" in obj.current_characteristics.get("card_types", ())
    ]


def test_step_through_bounces_two_creatures_and_wizardcycling_remains_available() -> None:
    state, executor, specs = funded_game("step-through")
    first = add_card(executor, specs["Wily Goblin"], Zone.BATTLEFIELD, owner="P1")
    second = add_card(executor, specs["Spectral Sailor"], Zone.BATTLEFIELD, owner="P1")
    spell = add_card(executor, specs["Step Through"], Zone.HAND)

    executor.cast(
        "P0",
        spell.object_id,
        (TargetRef(first.object_id), TargetRef(second.object_id)),
    )
    pass_all(executor)

    assert first.retired and second.retired
    assert len(active_objects(state, name="Wily Goblin", zone=Zone.HAND, owner="P1")) == 1
    assert len(active_objects(state, name="Spectral Sailor", zone=Zone.HAND, owner="P1")) == 1
