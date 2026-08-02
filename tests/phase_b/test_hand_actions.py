"""Focused competencies for Phase B hand actions and opponent choices."""

from __future__ import annotations

import json
from typing import Any

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card, add_external_public_object, new_game
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import ObjectKind, TargetRef, Zone
from mtg_kernel.observation import ObservationService
from mtg_kernel.phase_b_actions import activate_hand_ability, foretell
from mtg_kernel.replay import transcript, validate_replay
from mtg_policy import (
    ContextualEvaluator,
    PolicyStrategicChoiceProvider,
    load_evaluator_config,
    load_policy_matrix,
)
from mtg_policy.broker import ActionBroker

PLAYERS = ("P0", "P1", "P2", "P3")


def specs_by_name() -> dict[str, Any]:
    return {spec.name: spec for spec in load_full_deck_specs().values()}


def funded_game(seed: str = "phase-b-actions"):
    state, executor = new_game(PLAYERS, seed)
    for symbol in ("W", "U", "B", "R", "G", "C"):
        state.players["P0"].mana_pool[symbol] = 30
    executor.bind_strategic_choice_provider(
        PolicyStrategicChoiceProvider(
            load_policy_matrix()[0],
            ContextualEvaluator(load_evaluator_config()),
        )
    )
    return state, executor, specs_by_name()


def pass_all(executor) -> None:
    for _ in PLAYERS:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def active_objects(state, *, name: str | None = None, zone: Zone | None = None):
    values = [obj for obj in state.objects.values() if not obj.retired and not obj.ceased_to_exist]
    if name is not None:
        values = [obj for obj in values if obj.current_characteristics.get("name") == name]
    if zone is not None:
        values = [obj for obj in values if obj.zone is zone]
    return values


def test_transmute_is_sorcery_speed_stack_action_with_discard_cost_and_search() -> None:
    state, executor, specs = funded_game("transmute")
    dizzy = add_card(executor, specs["Dizzy Spell"], Zone.HAND)
    first_ring = add_card(executor, specs["Sol Ring"], Zone.LIBRARY)
    add_card(executor, specs["Mountain"], Zone.LIBRARY)
    add_card(executor, specs["Sol Ring"], Zone.LIBRARY)

    state.turn.phase = "COMBAT"
    before = state_hash(state)
    with pytest.raises(IllegalAction, match="sorcery timing"):
        activate_hand_ability(executor, "P0", dizzy.object_id, "dizzy-spell:transmute")
    assert state_hash(state) == before

    state.turn.phase = "PRECOMBAT_MAIN"
    ability = activate_hand_ability(executor, "P0", dizzy.object_id, "dizzy-spell:transmute")
    assert ability.object_kind is ObjectKind.ACTIVATED_ABILITY
    assert state.stack == [ability.object_id]
    assert active_objects(state, name="Dizzy Spell", zone=Zone.GRAVEYARD)
    with pytest.raises(IllegalAction, match="only after all players pass"):
        executor.resolve_top()

    pass_all(executor)

    rings = active_objects(state, name="Sol Ring", zone=Zone.HAND)
    assert len(rings) == 1
    assert rings[0].component_card_instance_ids == first_ring.component_card_instance_ids
    assert any(
        choice.kind == "TRANSMUTE" and choice.selected["identity"] == "Sol Ring"
        for choice in state.choices
    )
    assert any(event.kind == "LIBRARY_SHUFFLED" for event in state.events)


def test_typecycling_uses_stack_at_instant_timing_and_reveals_selected_type() -> None:
    state, executor, specs = funded_game("wizardcycling")
    step = add_card(executor, specs["Step Through"], Zone.HAND)
    wizard = add_card(executor, specs["Vedalken Aethermage"], Zone.LIBRARY)
    add_card(executor, specs["Island"], Zone.LIBRARY)
    state.turn.phase = "COMBAT"

    ability = activate_hand_ability(executor, "P0", step.object_id, "step-through:wizardcycling")
    assert state.stack == [ability.object_id]
    assert active_objects(state, name="Step Through", zone=Zone.GRAVEYARD)

    pass_all(executor)

    selected = active_objects(state, name="Vedalken Aethermage", zone=Zone.HAND)
    assert len(selected) == 1
    assert selected[0].component_card_instance_ids == wizard.component_card_instance_ids
    assert any(
        event.kind == "SEARCH_CARD_REVEALED"
        and event.payload.get("identity") == "Vedalken Aethermage"
        for event in state.events
    )


def test_cycling_discards_as_cost_then_draws_only_when_the_ability_resolves() -> None:
    state, executor, specs = funded_game("cycling")
    rebuild = add_card(executor, specs["Rebuild"], Zone.HAND)
    top = add_card(executor, specs["Island"], Zone.LIBRARY)

    activate_hand_ability(executor, "P0", rebuild.object_id, "rebuild:cycling")
    assert active_objects(state, name="Rebuild", zone=Zone.GRAVEYARD)
    assert not active_objects(state, name="Island", zone=Zone.HAND)

    pass_all(executor)

    drawn = active_objects(state, name="Island", zone=Zone.HAND)
    assert len(drawn) == 1
    assert drawn[0].component_card_instance_ids == top.component_card_instance_ids


def test_foretell_is_no_stack_hidden_special_action_and_later_uses_alternative_cost() -> None:
    state, executor, specs = funded_game("foretell")
    ravenform = add_card(executor, specs["Ravenform"], Zone.HAND)
    target = add_external_public_object(
        executor,
        "opponent-artifact",
        Zone.BATTLEFIELD,
        "P1",
        "P1",
        {"name": "Opponent Artifact", "card_types": ["Artifact"], "abilities": []},
    )

    foretold = foretell(executor, "P0", ravenform.object_id, "ravenform:foretell")
    assert state.stack == []
    assert foretold.zone is Zone.EXILE
    assert foretold.nonbattlefield_orientation == "FACE_DOWN"

    owner_view = ObservationService(state).observe("P0")
    opponent_view = ObservationService(state).observe("P1")
    assert any(obj["identity"] == "Ravenform" for obj in owner_view["objects"])
    assert all(
        obj["identity"] is None
        for obj in opponent_view["objects"]
        if obj["zone"] == Zone.EXILE.value and obj["face_down"]
    )

    before = state_hash(state)
    with pytest.raises(IllegalAction, match="during the turn it was foretold"):
        executor.cast("P0", foretold.object_id, (TargetRef(target.object_id),), mode="foretell")
    assert state_hash(state) == before

    state.turn.number += 1
    for symbol in state.players["P0"].mana_pool:
        state.players["P0"].mana_pool[symbol] = 0
    state.players["P0"].mana_pool["U"] = 1
    spell = executor.cast("P0", foretold.object_id, (TargetRef(target.object_id),), mode="foretell")
    assert executor._created_action(spell).payments["cost"]["U"] == 1
    assert sum(executor._created_action(spell).payments["cost"].values()) == 1

    pass_all(executor)

    assert state.external_object_ledger[-1]["object_id"] == target.object_id
    assert state.external_object_ledger[-1]["destination"] == Zone.EXILE.value
    birds = active_objects(state, name="Bird", zone=Zone.BATTLEFIELD)
    assert len(birds) == 1
    assert birds[0].controller == "P1"
    assert birds[0].owner == "P1"
    assert birds[0].current_characteristics["power"] == 1
    assert birds[0].current_characteristics["toughness"] == 1


def _fact_or_fiction_result(seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    state, executor, specs = funded_game(seed)
    for name in ("Island", "Mountain", "Sol Ring", "Opt", "Dualcaster Mage"):
        add_card(executor, specs[name], Zone.LIBRARY)
    fact = add_card(executor, specs["Fact or Fiction"], Zone.HAND)
    executor.cast("P0", fact.object_id)
    pass_all(executor)
    split = next(choice for choice in state.choices if choice.kind == "FACT_OR_FICTION_SPLIT")
    selected = next(choice for choice in state.choices if choice.kind == "FACT_OR_FICTION_PILE")
    assert split.player_id == "P1"
    assert selected.player_id == "P0"
    split_value = dict(split.selected)
    selected_value = dict(selected.selected)
    assert split_value["evaluator_id"] == "contextual_combo_v1"
    assert selected_value["evaluator_id"] == "contextual_combo_v1"
    diagnostics = selected_value["diagnostics"]
    assert "pile_a_evaluation" in diagnostics
    assert "pile_b_evaluation" in diagnostics
    moved_names = {
        str(obj.current_characteristics.get("name"))
        for obj in active_objects(state)
        if obj.zone in {Zone.HAND, Zone.GRAVEYARD}
        and obj.current_characteristics.get("name") != "Fact or Fiction"
    }
    assert moved_names == {"Island", "Mountain", "Sol Ring", "Opt", "Dualcaster Mage"}
    assert not state.zones.get("LIBRARY:P0")
    return split_value, selected_value


def test_fact_or_fiction_uses_contextual_policy_evaluation_and_records_both_choices() -> None:
    first = _fact_or_fiction_result("fact-or-fiction")
    second = _fact_or_fiction_result("fact-or-fiction")
    assert first == second


def test_phase_b_special_actions_and_hand_abilities_round_trip_through_replay() -> None:
    state, executor, specs = funded_game("phase-b-replay")
    land = add_card(executor, specs["Thriving Isle"], Zone.HAND)
    ravenform = add_card(executor, specs["Ravenform"], Zone.HAND)
    rebuild = add_card(executor, specs["Rebuild"], Zone.HAND)
    add_card(executor, specs["Island"], Zone.LIBRARY)

    from mtg_kernel.land_actions import play_land

    play_land(executor, "P0", land.object_id, {"chosen_color": "R"})
    foretell(executor, "P0", ravenform.object_id, "ravenform:foretell")
    activate_hand_ability(executor, "P0", rebuild.object_id, "rebuild:cycling")
    pass_all(executor)

    recorded = transcript(state, seed="phase-b-replay")
    assert [command["operation"] for command in recorded["commands"]][:3] == [
        "play_land",
        "foretell",
        "activate_hand",
    ]
    replayed = validate_replay(recorded)
    assert state_hash(replayed) == state_hash(state)


def test_broker_enumerates_mana_reveal_tutor_and_foretell_choices_without_raw_ids() -> None:
    _state, executor, specs = funded_game("broker-choices")
    temple = add_card(executor, specs["Temple of Epiphany"], Zone.BATTLEFIELD)
    snarl = add_card(executor, specs["Frostboil Snarl"], Zone.HAND)
    reveal = add_card(executor, specs["Island"], Zone.HAND)
    dizzy = add_card(executor, specs["Dizzy Spell"], Zone.HAND)
    hidden_ring = add_card(executor, specs["Sol Ring"], Zone.LIBRARY, visible_to=set())
    ravenform = add_card(executor, specs["Ravenform"], Zone.HAND)

    _, actions = ActionBroker(executor, "P0").refresh()
    mana = [
        action
        for action in actions
        if action.kind == "ACTIVATE"
        and action.identity == "Temple of Epiphany"
        and "mana_color" in action.metadata
    ]
    assert {action.metadata["mana_color"] for action in mana} == {"U", "R"}

    lands = [
        action
        for action in actions
        if action.kind == "PLAY_LAND" and action.identity == snarl.current_characteristics["name"]
    ]
    assert {action.metadata.get("reveal_identity") for action in lands} == {None, "Island"}

    tutors = [action for action in actions if action.kind == "ACTIVATE_HAND" and action.identity == "Dizzy Spell"]
    assert len(tutors) == 1
    assert tutors[0].metadata["choice_timing"] == "RESOLUTION"
    assert "Sol Ring" in tutors[0].metadata["eligible_tutor_identities"]
    assert any(action.kind == "FORETELL" and action.identity == "Ravenform" for action in actions)

    encoded = json.dumps([action.__dict__ for action in actions])
    for obj in (temple, snarl, reveal, dizzy, hidden_ring, ravenform):
        assert obj.object_id not in encoded
        if obj.component_card_instance_ids:
            assert obj.component_card_instance_ids[0] not in encoded
