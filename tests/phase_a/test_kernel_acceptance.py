"""CLEAN_ENGINE_PRODUCTION_PATH Phase A acceptance tests."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from mtg_cards import PHASE_A_NAMES, load_phase_a_specs
from mtg_kernel.engine import GameExecutor
from mtg_kernel.errors import IllegalAction, ReplayError, UnsupportedCapability
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import CopyKind, GameObject, ObjectKind, ReferenceMode, TargetRef, Zone
from mtg_kernel.observation import ObservationService
from mtg_kernel.replay import transcript, validate_replay


def specs_by_name():
    return {spec.name: spec for spec in load_phase_a_specs().values()}


def scenario() -> tuple[object, GameExecutor]:
    state, executor = new_game()
    state.players["P0"].mana_pool["GENERIC"] = 20
    return state, executor


def test_spec_oracle_completeness_and_named_pool() -> None:
    specs = load_phase_a_specs()
    assert {s.name for s in specs.values()} == set(PHASE_A_NAMES)
    assert all(s.card_spec_id == f"oracle:{s.oracle_id}" for s in specs.values())
    assert all(len(s.oracle_record_sha256) == 64 for s in specs.values())
    assert all(face["oracle_text"] is not None for s in specs.values() for face in s.faces)


def test_permanent_spell_stack_priority_then_battlefield() -> None:
    state, executor = scenario()
    card = add_card(executor, specs_by_name()["Sol Ring"], Zone.HAND)
    spell = executor.cast("P0", card.object_id)
    assert spell.zone is Zone.STACK and spell.object_kind is ObjectKind.SPELL
    assert state.turn.priority_holder_id == "P0"
    executor.pass_priority("P0")
    executor.pass_priority("P1")
    successors = [o for o in state.objects.values() if o.predecessor_object_id == spell.object_id]
    assert successors[0].zone is Zone.BATTLEFIELD


def test_illegal_action_is_atomic() -> None:
    state, executor = scenario()
    card = add_card(executor, specs_by_name()["Opt"], Zone.HAND)
    before = state_hash(state)
    with pytest.raises(IllegalAction):
        executor.cast("P0", card.object_id, (TargetRef("missing"),))
    assert state_hash(state) == before


def test_countered_permanent_never_enters_or_triggers() -> None:
    state, executor = scenario()
    lantern = add_card(executor, specs_by_name()["Soul-Guide Lantern"], Zone.HAND)
    spell = executor.cast("P0", lantern.object_id)
    executor.counter(spell.object_id)
    assert not state.waiting_triggers
    assert not any(
        o.zone is Zone.BATTLEFIELD and o.current_characteristics.get("name") == "Soul-Guide Lantern"
        for o in state.objects.values()
    )


def test_soul_guide_lantern_real_targeted_etb_trigger_only_with_target() -> None:
    state, executor = scenario()
    target = add_card(executor, specs_by_name()["Opt"], Zone.GRAVEYARD, owner="P1")
    lantern = add_card(executor, specs_by_name()["Soul-Guide Lantern"], Zone.HAND)
    executor.cast("P0", lantern.object_id)
    executor.resolve_top()
    trigger = state.objects[state.stack[-1]]
    assert trigger.object_kind is ObjectKind.TRIGGERED_ABILITY
    assert trigger.current_characteristics["targets"][0].object_id == target.object_id

    state2, executor2 = scenario()
    lantern2 = add_card(executor2, specs_by_name()["Soul-Guide Lantern"], Zone.HAND)
    executor2.cast("P0", lantern2.object_id)
    executor2.resolve_top()
    assert not state2.stack


def test_retired_target_does_not_follow_successor() -> None:
    state, executor = scenario()
    target = add_card(executor, specs_by_name()["Sol Ring"], Zone.BATTLEFIELD, owner="P1")
    ref = TargetRef(target.object_id)
    executor.zones.move(target.object_id, Zone.GRAVEYARD, "TEST", executor._event("TEST"))
    with pytest.raises(IllegalAction):
        executor.identity.resolve_reference(ref)


def test_zone_changes_and_same_zone_events_create_new_identity() -> None:
    state, executor = scenario()
    card = add_card(executor, specs_by_name()["Opt"], Zone.EXILE)
    next_obj = executor.zones.reincarnate_same_zone(
        card.object_id, "REEXILE", executor._event("TEST")
    )
    assert next_obj.object_id != card.object_id and next_obj.predecessor_object_id == card.object_id
    command = executor.zones.move(next_obj.object_id, Zone.COMMAND, "TEST", executor._event("TEST"))
    assert command is not None
    face_down = executor.zones.reincarnate_same_zone(
        command.object_id, "COMMAND_FACE_DOWN", executor._event("TEST")
    )
    reentered = executor.zones.reincarnate_same_zone(
        face_down.object_id, "COMMAND_REENTRY", executor._event("TEST")
    )
    assert (
        len(
            {
                card.object_id,
                next_obj.object_id,
                command.object_id,
                face_down.object_id,
                reentered.object_id,
            }
        )
        == 5
    )


def test_one_active_object_per_physical_card() -> None:
    state, executor = scenario()
    card = add_card(executor, specs_by_name()["Opt"], Zone.HAND)
    duplicate = GameObject(
        "duplicate",
        ObjectKind.CARD_IN_ZONE,
        Zone.EXILE,
        "P0",
        None,
        card.component_card_instance_ids,
    )
    state.objects[duplicate.object_id] = duplicate
    with pytest.raises(IllegalAction):
        executor.identity.validate_active_components()


def test_commander_return_is_optional_recorded_and_intermediate() -> None:
    state, executor = scenario()
    commander = add_card(
        executor, specs_by_name()["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD, commander=True
    )
    grave = executor.zones.move(
        commander.object_id, Zone.GRAVEYARD, "DESTROY", executor._event("DESTROY")
    )
    assert grave is not None and grave.zone is Zone.GRAVEYARD
    executor.check_state_based_actions()
    returned = executor.commander_return_choice("P0", grave.object_id, True)
    assert returned.zone is Zone.COMMAND and state.choices[-1].selected == "RETURN"
    assert [z.to_zone for z in state.zone_changes[-2:]] == [Zone.GRAVEYARD, Zone.COMMAND]


def test_spell_and_token_copies_are_synthetic_and_cease() -> None:
    state, executor = scenario()
    card = add_card(executor, specs_by_name()["Opt"], Zone.HAND)
    spell = executor.cast("P0", card.object_id)
    copy = executor.copy_spell(spell, "P0")
    assert (
        copy.copy_kind is CopyKind.SPELL_COPY
        and not copy.component_card_instance_ids
        and copy.was_cast is False
    )
    executor.resolve_top()
    assert copy.ceased_to_exist
    creature = add_card(executor, specs_by_name()["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD)
    token = executor.copy_permanent_token(creature, "P0")
    executor.zones.move(token.object_id, Zone.EXILE, "DELAYED", executor._event("DELAYED"))
    assert token.ceased_to_exist


def test_marked_damage_and_repeated_cleanup() -> None:
    state, executor = scenario()
    creature = add_card(executor, specs_by_name()["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD)
    creature.marked_damage = 2
    for _ in range(8):
        add_card(executor, specs_by_name()["Opt"], Zone.HAND)
    executor.cleanup()
    assert creature.marked_damage == 0
    assert state.turn.cleanup_iteration == 2
    assert len(state.zones["HAND:P0"]) == 7
    assert any(z.cause == "CLEANUP_DISCARD" for z in state.zone_changes)


def test_hidden_observation_excludes_ids_order_and_revokes_handles() -> None:
    state, executor = scenario()
    add_card(executor, specs_by_name()["Opt"], Zone.LIBRARY, visible_to=set())
    service = ObservationService(state)
    first = service.observe("P0")
    encoded = json.dumps(first)
    assert "object-" not in encoded and "card-" not in encoded and "Opt" not in encoded
    service.observe("P0")
    with pytest.raises(IllegalAction):
        service.require_current_generation(first["generation"])


def test_unsupported_continuity_fails_closed() -> None:
    state, executor = scenario()
    card = add_card(executor, specs_by_name()["Opt"], Zone.HAND)
    with pytest.raises(UnsupportedCapability):
        executor.identity.resolve_reference(
            TargetRef(card.object_id, ReferenceMode.SUCCESSOR_TRACKING, "STICKER_RETENTION")
        )


def test_terminal_stops_execution() -> None:
    state, executor = scenario()
    state.players["P1"].life = 0
    executor.check_state_based_actions()
    assert state.terminal.status == "TERMINAL"
    with pytest.raises(IllegalAction):
        executor.cleanup()


def test_replay_rejects_alteration_and_reproduces() -> None:
    def execute():
        state, executor = scenario()
        card = add_card(executor, specs_by_name()["Sol Ring"], Zone.HAND)
        executor.cast("P0", card.object_id)
        return state

    original = transcript(execute())
    assert transcript(validate_replay(original, execute)) == original
    altered = dict(original)
    altered["final_state_hash"] = "0" * 64
    with pytest.raises(ReplayError):
        validate_replay(altered, execute)


def test_replay_state_hash_matches_fresh_process() -> None:
    code = """from mtg_cards import load_phase_a_specs
from mtg_kernel.factory import new_game,add_card
from mtg_kernel.models import Zone
from mtg_kernel.hashing import state_hash
s,e=new_game();e.state.players['P0'].mana_pool['GENERIC']=20
spec=next(x for x in load_phase_a_specs().values() if x.name=='Sol Ring')
c=add_card(e,spec,Zone.HAND);e.cast('P0',c.object_id);print(state_hash(s))"""
    first = subprocess.check_output([sys.executable, "-c", code], text=True).strip()
    second = subprocess.check_output([sys.executable, "-c", code], text=True).strip()
    assert first == second and len(first) == 64


def test_commit_handles_internal_spell_copy_and_external_objects() -> None:
    state, executor = scenario()
    commit = add_card(executor, specs_by_name()["Commit // Memory"], Zone.HAND)
    target = add_card(executor, specs_by_name()["Sol Ring"], Zone.BATTLEFIELD, owner="P1")
    executor.cast("P0", commit.object_id, (TargetRef(target.object_id),), face=0)
    executor.resolve_top()
    assert any(
        z.cause == "COMMIT" and z.from_object_id == target.object_id for z in state.zone_changes
    )

    state2, executor2 = scenario()
    opt = add_card(executor2, specs_by_name()["Opt"], Zone.HAND, owner="P1")
    spell = executor2.cast("P1", opt.object_id)
    copy = executor2.copy_spell(spell, "P1")
    commit2 = add_card(executor2, specs_by_name()["Commit // Memory"], Zone.HAND)
    executor2.cast("P0", commit2.object_id, (TargetRef(copy.object_id),), face=0)
    executor2.resolve_top()
    assert copy.ceased_to_exist

    state3, executor3 = scenario()
    external = GameObject(
        "external", ObjectKind.EXTERNAL_PUBLIC_OBJECT, Zone.BATTLEFIELD, "P1", "P1"
    )
    state3.objects[external.object_id] = external
    executor3.zones.register(external)
    commit3 = add_card(executor3, specs_by_name()["Commit // Memory"], Zone.HAND)
    executor3.cast("P0", commit3.object_id, (TargetRef(external.object_id),), face=0)
    executor3.resolve_top()
    assert state3.external_object_ledger[-1]["destination"] == "LIBRARY"
    assert state3.external_object_ledger[-1]["position"] == "SECOND_FROM_TOP"


def test_memory_casts_only_from_graveyard_and_rejects_targets() -> None:
    state, executor = scenario()
    memory = add_card(executor, specs_by_name()["Commit // Memory"], Zone.GRAVEYARD)
    spell = executor.cast("P0", memory.object_id, face=1)
    assert spell.zone is Zone.STACK
    state2, executor2 = scenario()
    memory2 = add_card(executor2, specs_by_name()["Commit // Memory"], Zone.GRAVEYARD)
    with pytest.raises(IllegalAction):
        executor2.cast("P0", memory2.object_id, (TargetRef(memory2.object_id),), face=1)


def test_twinflame_uses_token_copy_and_delayed_trigger_path() -> None:
    state, executor = scenario()
    creature = add_card(executor, specs_by_name()["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD)
    twinflame = add_card(executor, specs_by_name()["Twinflame"], Zone.HAND)
    executor.cast("P0", twinflame.object_id, (TargetRef(creature.object_id),))
    executor.resolve_top()
    tokens = [
        o for o in state.objects.values() if o.copy_kind is CopyKind.TOKEN_COPY and not o.retired
    ]
    assert len(tokens) == 1 and tokens[0].object_id in state.delayed_triggers
    executor.zones.move(
        tokens[0].object_id, Zone.EXILE, "DELAYED_TRIGGER", executor._event("DELAYED_TRIGGER")
    )
    assert tokens[0].ceased_to_exist


def test_dualcaster_etb_creates_real_trigger_and_uncast_spell_copy() -> None:
    state, executor = scenario()
    opt = add_card(executor, specs_by_name()["Opt"], Zone.HAND)
    original = executor.cast("P0", opt.object_id)
    dualcaster = add_card(executor, specs_by_name()["Dualcaster Mage"], Zone.HAND)
    executor.cast("P0", dualcaster.object_id)
    executor.resolve_top()
    assert state.objects[state.stack[-1]].object_kind is ObjectKind.TRIGGERED_ABILITY
    executor.resolve_top()
    copies = [
        o for o in state.objects.values() if o.copy_kind is CopyKind.SPELL_COPY and not o.retired
    ]
    assert len(copies) == 1 and copies[0].copied_from_object_id == original.object_id
    assert copies[0].was_cast is False and not copies[0].component_card_instance_ids
