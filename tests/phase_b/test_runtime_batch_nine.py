"""Executable coverage for split-card, transmute, and protection paths."""

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


def add_library(executor, specs, player_id: str, count: int) -> None:
    names = ("Island", "Mountain", "Opt", "Sol Ring")
    for index in range(count):
        add_card(executor, specs[names[index % len(names)]], Zone.LIBRARY, owner=player_id)


def test_commit_and_memory_execute_both_exact_deck_faces() -> None:
    state, executor, specs = funded_game("commit-face")
    target = add_card(executor, specs["Sol Ring"], Zone.BATTLEFIELD, owner="P1")
    commit = add_card(executor, specs["Commit // Memory"], Zone.HAND)

    executor.cast("P0", commit.object_id, (TargetRef(target.object_id),), face=0)
    pass_all(executor)

    assert target.retired
    assert any(
        change.cause == "COMMIT" and change.from_object_id == target.object_id
        for change in state.zone_changes
    )
    assert len(active_objects(state, name="Sol Ring", zone=Zone.LIBRARY, owner="P1")) == 1

    memory_state, memory_executor, memory_specs = funded_game("memory-face")
    add_library(memory_executor, memory_specs, "P0", 8)
    add_library(memory_executor, memory_specs, "P1", 8)
    add_card(memory_executor, memory_specs["Opt"], Zone.HAND, owner="P0")
    add_card(memory_executor, memory_specs["Mountain"], Zone.GRAVEYARD, owner="P0")
    add_card(memory_executor, memory_specs["Sol Ring"], Zone.HAND, owner="P1")
    add_card(memory_executor, memory_specs["Opt"], Zone.GRAVEYARD, owner="P1")
    memory = add_card(memory_executor, memory_specs["Commit // Memory"], Zone.GRAVEYARD)

    memory_executor.cast("P0", memory.object_id, face=1)
    pass_all(memory_executor)

    assert len(active_objects(memory_state, zone=Zone.HAND, owner="P0")) == 7
    assert len(active_objects(memory_state, zone=Zone.HAND, owner="P1")) == 7
    assert len(active_objects(memory_state, name="Commit // Memory", zone=Zone.EXILE)) == 1
    assert sum(event.kind == "LIBRARY_SHUFFLED" for event in memory_state.events) == 2


def test_drift_of_phantasms_transmutes_for_one_mana_value_three_card() -> None:
    state, executor, specs = funded_game("drift-transmute")
    source = add_card(executor, specs["Drift of Phantasms"], Zone.HAND)
    add_card(executor, specs["Lightning-Rig Crew"], Zone.LIBRARY)
    state.turn.phase = "PRECOMBAT_MAIN"

    activate_hand_ability(executor, "P0", source.object_id, "drift:transmute")
    pass_all(executor)

    assert len(active_objects(state, name="Drift of Phantasms", zone=Zone.GRAVEYARD)) == 1
    assert len(active_objects(state, name="Lightning-Rig Crew", zone=Zone.HAND)) == 1
    assert any(event.kind == "LIBRARY_SHUFFLED" for event in state.events)


def test_siren_stormtamer_counters_a_spell_targeting_its_controller() -> None:
    state, executor, specs = funded_game("stormtamer-counter")
    protected = add_card(executor, specs["Wily Goblin"], Zone.BATTLEFIELD, owner="P0")
    stormtamer = add_card(executor, specs["Siren Stormtamer"], Zone.BATTLEFIELD, owner="P0")
    abrade = add_card(executor, specs["Abrade"], Zone.HAND, owner="P1")
    state.turn.active_player_id = "P1"
    state.turn.priority_holder_id = "P1"

    target_spell = executor.cast(
        "P1",
        abrade.object_id,
        (TargetRef(protected.object_id),),
        mode="damage",
    )
    executor.pass_priority("P1")
    executor.activate(
        "P0",
        stormtamer.object_id,
        "stormtamer:counter",
        (TargetRef(target_spell.object_id),),
    )
    pass_all(executor)

    assert target_spell.retired
    assert len(active_objects(state, name="Abrade", zone=Zone.GRAVEYARD, owner="P1")) == 1
    assert len(active_objects(state, name="Siren Stormtamer", zone=Zone.GRAVEYARD, owner="P0")) == 1
    assert len(active_objects(state, name="Wily Goblin", zone=Zone.BATTLEFIELD, owner="P0")) == 1
