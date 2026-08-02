"""Fail-closed broker coverage and hidden-state boundary tests."""
from __future__ import annotations
import pytest
from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import UnsupportedCapability
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import Zone
from mtg_policy import ContextualEvaluator, bind_policy_strategic_choices, load_evaluator_config
from mtg_policy.broker import ActionBroker
from mtg_policy.config import load_policy_matrix
PLAYERS=("P0","P1","P2","P3")

def scenario(seed:str):
    state,executor=new_game(PLAYERS,seed)
    for symbol in ("W","U","B","R","G","C"): state.players["P0"].mana_pool[symbol]=30
    return state,executor,{spec.name:spec for spec in load_full_deck_specs().values()}

def pass_all(executor)->None:
    for _ in PLAYERS:
        holder=executor.state.turn.priority_holder_id; assert holder is not None; executor.pass_priority(holder)

def test_broker_omits_casts_and_activations_without_execution_support()->None:
    _,executor,specs=scenario("fail-closed-actions"); add_card(executor,specs["Aetherize"],Zone.HAND); add_card(executor,specs["Fact or Fiction"],Zone.HAND); add_card(executor,specs["Shivan Reef"],Zone.BATTLEFIELD)
    _,actions=ActionBroker(executor,"P0").refresh(); casts={(a.identity,a.metadata.get("mode")) for a in actions if a.kind=="CAST"}; assert ("Fact or Fiction","default") in casts and all(i!="Aetherize" for i,_ in casts)

def test_broker_enumerates_both_explicit_opt_scry_choices()->None:
    _,executor,specs=scenario("opt-choices"); add_card(executor,specs["Opt"],Zone.HAND); add_card(executor,specs["Island"],Zone.LIBRARY); _,actions=ActionBroker(executor,"P0").refresh(); opt=[a for a in actions if a.kind=="CAST" and a.identity=="Opt"]; assert len(opt)==2 and {a.metadata.get("scry_to_bottom") for a in opt}=={False,True}

def tutor_actions(zone:Zone):
    state,executor,specs=scenario(f"tutor-{zone.value}"); add_card(executor,specs["Dizzy Spell"],Zone.HAND); add_card(executor,specs["Sol Ring"],zone); bind_policy_strategic_choices(executor,load_policy_matrix()[0],ContextualEvaluator(load_evaluator_config())); broker=ActionBroker(executor,"P0"); observation,actions=broker.refresh(); tutors=[a for a in actions if a.kind=="ACTIVATE_HAND" and a.identity=="Dizzy Spell"]; return state,executor,broker,observation,tutors

def test_tutor_action_descriptions_do_not_depend_on_current_hidden_library_contents()->None:
    _,_,_,_,in_library=tutor_actions(Zone.LIBRARY); state,executor,broker,observation,absent=tutor_actions(Zone.GRAVEYARD)
    assert len(in_library)==len(absent)==1 and in_library[0].metadata==absent[0].metadata and in_library[0].metadata["choice_timing"]=="RESOLUTION" and "Sol Ring" in in_library[0].metadata["eligible_tutor_identities"] and "tutor_identity" not in in_library[0].metadata
    broker.execute(int(observation["generation"]),absent[0].handle); pass_all(executor)
    assert not [o for o in state.objects.values() if not o.retired and o.zone is Zone.HAND and o.current_characteristics.get("name")=="Sol Ring"]
    assert any(c.kind=="TRANSMUTE" and isinstance(c.selected,dict) and c.selected.get("identity")=="FAIL_TO_FIND" and c.selected.get("chosen_at")=="RESOLUTION" for c in state.choices)

def test_unverified_automatic_battlefield_behavior_is_a_hard_broker_failure()->None:
    _,executor,specs=scenario("unsafe-static"); add_card(executor,specs["Psychosis Crawler"],Zone.BATTLEFIELD)
    with pytest.raises(UnsupportedCapability,match="unverified automatic behavior"): ActionBroker(executor,"P0").refresh()

def test_pending_commander_return_choice_suppresses_priority_actions()->None:
    state,executor,specs=scenario("commander-choice"); commander=add_card(executor,specs["Malcolm, Keen-Eyed Navigator"],Zone.EXILE,commander=True); executor.check_state_based_actions(); broker=ActionBroker(executor,"P0"); observation,actions=broker.refresh(); assert {a.kind for a in actions}=={"COMMANDER_RETURN"}; return_action=next(a for a in actions if a.metadata["destination"]=="COMMAND"); broker.execute(int(observation["generation"]),return_action.handle); successors=[o for o in state.objects.values() if not o.retired and o.zone is Zone.COMMAND and o.component_card_instance_ids==commander.component_card_instance_ids]; assert len(successors)==1 and not state.pending_commander_choices
