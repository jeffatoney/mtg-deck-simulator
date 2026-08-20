"""CLEAN_ENGINE_PRODUCTION_PATH Phase A acceptance tests."""

from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from mtg_cards import PHASE_A_NAMES, load_phase_a_specs
from mtg_kernel.engine import GameExecutor
from mtg_kernel.errors import IllegalAction, ReplayError, UnsupportedCapability
from mtg_kernel.factory import add_card, add_external_public_object, new_game
from mtg_kernel.hashing import HASH_INCLUDED_ROOTS, state_hash, state_hash_document
from mtg_kernel.models import (
    Action,
    CopyKind,
    Event,
    GameObject,
    LKISnapshot,
    ObjectKind,
    ReferenceMode,
    TargetRef,
    Zone,
)
from mtg_kernel.observation import ObservationService
from mtg_kernel.replay import _digest, transcript, validate_replay


def specs_by_name():
    return {spec.name: spec for spec in load_phase_a_specs().values()}


def funded_game(players: tuple[str, ...] = ("P0", "P1")):
    state, executor = new_game(players)
    for player in state.players.values():
        for symbol in ("W", "U", "B", "R", "G", "C"):
            player.mana_pool[symbol] = 30
    return state, executor


def add_library(executor: GameExecutor, player_id: str, count: int) -> None:
    specs = specs_by_name()
    names = ("Island", "Mountain", "Opt", "Sol Ring")
    for index in range(count):
        add_card(executor, specs[names[index % len(names)]], Zone.LIBRARY, owner=player_id)


def pass_all(executor: GameExecutor) -> None:
    players = [player.player_id for player in executor.state.players.values() if player.in_game]
    for _ in players:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def active_objects(state, *, name: str | None = None, kind: ObjectKind | None = None):
    values = [obj for obj in state.objects.values() if not obj.retired and not obj.ceased_to_exist]
    if name is not None:
        values = [obj for obj in values if obj.current_characteristics.get("name") == name]
    if kind is not None:
        values = [obj for obj in values if obj.object_kind is kind]
    return values


def test_oracle_pool_namespace_and_complete_behavior_compositions() -> None:
    specs = load_phase_a_specs()
    assert {spec.name for spec in specs.values()} == set(PHASE_A_NAMES)
    assert all(spec.card_spec_id == f"oracle:{spec.oracle_id}" for spec in specs.values())
    assert all(len(spec.oracle_record_sha256) == 64 for spec in specs.values())
    assert all(spec.source_version.startswith("snapshot-v2:") for spec in specs.values())
    assert all(spec.abilities for spec in specs.values())
    assert all(
        isinstance(face["oracle_text"], str) and face["oracle_text"].strip()
        for spec in specs.values()
        for face in spec.faces
    )
    assert not any(spec.card_spec_id.startswith("fixture:") for spec in specs.values())


def test_basic_lands_sol_ring_and_treasure_use_real_mana_abilities() -> None:
    state, executor = funded_game()
    specs = specs_by_name()
    for symbol in ("U", "R", "C"):
        state.players["P0"].mana_pool[symbol] = 0
    island = add_card(executor, specs["Island"], Zone.BATTLEFIELD)
    mountain = add_card(executor, specs["Mountain"], Zone.BATTLEFIELD)
    ring = add_card(executor, specs["Sol Ring"], Zone.BATTLEFIELD)
    executor.activate("P0", island.object_id, "island:mana-u")
    executor.activate("P0", mountain.object_id, "mountain:mana-r")
    executor.activate("P0", ring.object_id, "sol-ring:mana-cc")
    assert state.players["P0"].mana_pool["U"] == 1
    assert state.players["P0"].mana_pool["R"] == 1
    assert state.players["P0"].mana_pool["C"] == 2

    cause = Action(executor.identity.new_id("action"), "TEST", "P0")
    state.actions.append(cause)
    treasure = executor.create_treasure("P0", cause)
    executor.activate("P0", treasure.object_id, "token:treasure-mana", choices={"mana_color": "U"})
    assert state.players["P0"].mana_pool["U"] == 2
    assert not active_objects(state, name="Treasure")


def test_colored_costs_commander_tax_and_atomic_illegal_cast() -> None:
    state, executor = funded_game()
    specs = specs_by_name()
    state.players["P0"].mana_pool.update({symbol: 0 for symbol in ("W", "U", "B", "R", "G", "C")})
    state.players["P0"].mana_pool["U"] = 1
    state.players["P0"].mana_pool["C"] = 2
    commander = add_card(
        executor,
        specs["Malcolm, Keen-Eyed Navigator"],
        Zone.COMMAND,
        commander=True,
    )
    first = executor.cast("P0", commander.object_id)
    assert state.commander_cast_counts[first.component_card_instance_ids[0]] == 1
    executor.counter(first.object_id)
    grave = next(obj for obj in active_objects(state) if obj.zone is Zone.GRAVEYARD)
    returned = executor.commander_return_choice("P0", grave.object_id, True)
    state.players["P0"].mana_pool["U"] = 1
    state.players["P0"].mana_pool["C"] = 3
    before = state_hash(state)
    with pytest.raises(IllegalAction):
        executor.cast("P0", returned.object_id)
    assert state_hash(state) == before
    state.players["P0"].mana_pool["C"] = 4
    second = executor.cast("P0", returned.object_id)
    assert state.commander_cast_counts[second.component_card_instance_ids[0]] == 2
    assert state.players["P0"].mana_pool["U"] == 0
    assert state.players["P0"].mana_pool["C"] == 0


def test_permanent_spell_uses_stack_priority_and_counter_blocks_etb() -> None:
    state, executor = funded_game()
    specs = specs_by_name()
    ring = add_card(executor, specs["Sol Ring"], Zone.HAND)
    spell = executor.cast("P0", ring.object_id)
    assert spell.zone is Zone.STACK and spell.object_kind is ObjectKind.SPELL
    assert state.turn.priority_holder_id == "P0"
    pass_all(executor)
    assert active_objects(state, name="Sol Ring")[0].zone is Zone.BATTLEFIELD

    target = add_card(executor, specs["Opt"], Zone.GRAVEYARD, owner="P1")
    lantern = add_card(executor, specs["Soul-Guide Lantern"], Zone.HAND)
    lantern_spell = executor.cast(
        "P0",
        lantern.object_id,
        choices={"trigger_targets": {"lantern:etb": target.object_id}},
    )
    executor.counter(lantern_spell.object_id)
    assert not state.waiting_triggers
    assert not any(
        obj.zone is Zone.BATTLEFIELD for obj in active_objects(state, name="Soul-Guide Lantern")
    )


def test_abrade_modes_targets_and_target_revalidation() -> None:
    state, executor = funded_game()
    specs = specs_by_name()
    creature = add_card(
        executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD, owner="P1"
    )
    abrade = add_card(executor, specs["Abrade"], Zone.HAND)
    executor.cast("P0", abrade.object_id, (TargetRef(creature.object_id),), mode="damage")
    pass_all(executor)
    assert not any(
        obj.zone is Zone.BATTLEFIELD
        for obj in active_objects(state, name="Malcolm, Keen-Eyed Navigator")
    )

    artifact = add_card(executor, specs["Sol Ring"], Zone.BATTLEFIELD, owner="P1")
    abrade2 = add_card(executor, specs["Abrade"], Zone.HAND)
    executor.cast("P0", abrade2.object_id, (TargetRef(artifact.object_id),), mode="destroy")
    pass_all(executor)
    assert not any(obj.zone is Zone.BATTLEFIELD for obj in active_objects(state, name="Sol Ring"))

    creature2 = add_card(executor, specs["Glint-Horn Buccaneer"], Zone.BATTLEFIELD, owner="P1")
    abrade3 = add_card(executor, specs["Abrade"], Zone.HAND)
    spell = executor.cast("P0", abrade3.object_id, (TargetRef(creature2.object_id),), mode="damage")
    executor.zones.move(creature2.object_id, Zone.GRAVEYARD, "TEST", executor._event("TEST"))
    pass_all(executor)
    assert spell.retired
    assert any(event.kind == "STACK_OBJECT_COUNTERED" for event in state.events)


def test_lantern_etb_and_both_activated_abilities() -> None:
    state, executor = funded_game()
    specs = specs_by_name()
    target = add_card(executor, specs["Opt"], Zone.GRAVEYARD, owner="P1")
    lantern = add_card(executor, specs["Soul-Guide Lantern"], Zone.HAND)
    executor.cast(
        "P0",
        lantern.object_id,
        choices={"trigger_targets": {"lantern:etb": target.object_id}},
    )
    pass_all(executor)
    trigger_action = executor._created_action(state.objects[state.stack[-1]])
    assert trigger_action.targets == (TargetRef(target.object_id),)
    pass_all(executor)
    assert any(obj.zone is Zone.EXILE for obj in active_objects(state, name="Opt"))

    state2, executor2 = funded_game()
    lantern2 = add_card(executor2, specs["Soul-Guide Lantern"], Zone.HAND)
    executor2.cast("P0", lantern2.object_id)
    pass_all(executor2)
    assert not state2.stack

    state3, executor3 = funded_game()
    add_library(executor3, "P0", 1)
    lantern3 = add_card(executor3, specs["Soul-Guide Lantern"], Zone.BATTLEFIELD)
    executor3.activate("P0", lantern3.object_id, "lantern:draw")
    pass_all(executor3)
    assert len(state3.zones["HAND:P0"]) == 1
    assert not any(
        obj.zone is Zone.BATTLEFIELD for obj in active_objects(state3, name="Soul-Guide Lantern")
    )

    state4, executor4 = funded_game()
    add_card(executor4, specs["Opt"], Zone.GRAVEYARD, owner="P1")
    lantern4 = add_card(executor4, specs["Soul-Guide Lantern"], Zone.BATTLEFIELD)
    executor4.activate("P0", lantern4.object_id, "lantern:exile-opponents")
    pass_all(executor4)
    assert not state4.zones.get("GRAVEYARD:P1", [])


def test_opt_scry_and_draw_changes_real_library_order() -> None:
    state, executor = funded_game()
    specs = specs_by_name()
    bottom = add_card(executor, specs["Island"], Zone.LIBRARY)
    top = add_card(executor, specs["Mountain"], Zone.LIBRARY)
    opt = add_card(executor, specs["Opt"], Zone.HAND)
    executor.cast("P0", opt.object_id, choices={"scry_to_bottom": True})
    pass_all(executor)
    hand_names = [
        state.objects[obj].current_characteristics["name"] for obj in state.zones["HAND:P0"]
    ]
    assert "Island" in hand_names
    assert state.zones["LIBRARY:P0"] == [top.object_id]
    assert bottom.retired


def test_commit_handles_physical_copy_commander_and_external_objects() -> None:
    specs = specs_by_name()
    state, executor = funded_game()
    target = add_card(executor, specs["Sol Ring"], Zone.BATTLEFIELD, owner="P1")
    commit = add_card(executor, specs["Commit // Memory"], Zone.HAND)
    executor.cast("P0", commit.object_id, (TargetRef(target.object_id),), face=0)
    pass_all(executor)
    assert any(
        change.cause == "COMMIT" and change.from_object_id == target.object_id
        for change in state.zone_changes
    )

    state2, executor2 = funded_game()
    add_library(executor2, "P0", 1)
    original_card = add_card(executor2, specs["Opt"], Zone.HAND)
    original = executor2.cast("P0", original_card.object_id)
    cause = Action(executor2.identity.new_id("action"), "COPY_EFFECT", "P0")
    state2.actions.append(cause)
    copy = executor2.copy_spell(original, "P0", None, cause)
    commit2 = add_card(executor2, specs["Commit // Memory"], Zone.HAND)
    executor2.cast("P0", commit2.object_id, (TargetRef(copy.object_id),), face=0)
    pass_all(executor2)
    assert copy.retired
    assert any(
        obj.copy_kind is CopyKind.SPELL_COPY and obj.ceased_to_exist
        for obj in state2.objects.values()
    )

    state3, executor3 = funded_game()
    commander = add_card(
        executor3,
        specs["Malcolm, Keen-Eyed Navigator"],
        Zone.BATTLEFIELD,
        owner="P1",
        commander=True,
    )
    commit3 = add_card(executor3, specs["Commit // Memory"], Zone.HAND)
    executor3.cast(
        "P0",
        commit3.object_id,
        (TargetRef(commander.object_id),),
        face=0,
        choices={"commander_to_command": True},
    )
    pass_all(executor3)
    assert active_objects(state3, name="Malcolm, Keen-Eyed Navigator")[0].zone is Zone.COMMAND
    assert state3.choices[-1].selected == "COMMAND"

    state4, executor4 = funded_game()
    external = add_external_public_object(
        executor4,
        "external:artifact",
        Zone.BATTLEFIELD,
        "P1",
        "P1",
        {"name": "External Artifact", "card_types": ["Artifact"]},
    )
    commit4 = add_card(executor4, specs["Commit // Memory"], Zone.HAND)
    executor4.cast("P0", commit4.object_id, (TargetRef(external.object_id),), face=0)
    pass_all(executor4)
    assert state4.external_object_ledger[-1]["destination"] == "LIBRARY"
    assert state4.external_object_ledger[-1]["position"] == "SECOND_FROM_TOP"


def test_memory_aftermath_shuffle_draw_and_commander_replacement() -> None:
    state, executor = funded_game()
    specs = specs_by_name()
    add_library(executor, "P0", 8)
    add_library(executor, "P1", 8)
    commander = add_card(
        executor,
        specs["Malcolm, Keen-Eyed Navigator"],
        Zone.HAND,
        commander=True,
    )
    add_card(executor, specs["Opt"], Zone.GRAVEYARD)
    memory = add_card(executor, specs["Commit // Memory"], Zone.GRAVEYARD)
    executor.cast(
        "P0",
        memory.object_id,
        face=1,
        choices={"commander_replacements": {commander.object_id: True}},
    )
    pass_all(executor)
    assert active_objects(state, name="Malcolm, Keen-Eyed Navigator")[0].zone is Zone.COMMAND
    assert active_objects(state, name="Commit // Memory")[0].zone is Zone.EXILE
    assert len(state.zones["HAND:P0"]) == 7
    assert len(state.zones["HAND:P1"]) == 7

    state2, executor2 = funded_game()
    memory2 = add_card(executor2, specs["Commit // Memory"], Zone.HAND)
    with pytest.raises(IllegalAction):
        executor2.cast("P0", memory2.object_id, face=1)


def test_malcolm_and_glint_horn_use_real_trigger_and_stack_order() -> None:
    state, executor = funded_game()
    specs = specs_by_name()
    malcolm = add_card(executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD)
    executor.deal_damage_to_player(malcolm.object_id, "P1", 2, combat=True)
    assert state.objects[state.stack[-1]].object_kind is ObjectKind.TRIGGERED_ABILITY
    pass_all(executor)
    assert active_objects(state, name="Treasure")

    state2, executor2 = funded_game()
    add_library(executor2, "P0", 1)
    glint = add_card(executor2, specs["Glint-Horn Buccaneer"], Zone.BATTLEFIELD)
    glint.current_characteristics["attacking"] = True
    discarded = add_card(executor2, specs["Opt"], Zone.HAND)
    executor2.activate(
        "P0",
        glint.object_id,
        "glint-horn:attack-loot",
        choices={"discard_ids": [discarded.object_id]},
    )
    assert state2.objects[state2.stack[-1]].object_kind is ObjectKind.TRIGGERED_ABILITY
    pass_all(executor2)
    assert state2.players["P1"].life == 39
    pass_all(executor2)
    assert len(state2.zones["HAND:P0"]) == 1


def test_dualcaster_copy_and_twinflame_delayed_exile_are_real_objects() -> None:
    state, executor = funded_game()
    specs = specs_by_name()
    add_library(executor, "P0", 2)
    opt = add_card(executor, specs["Opt"], Zone.HAND)
    original = executor.cast("P0", opt.object_id)
    dualcaster = add_card(executor, specs["Dualcaster Mage"], Zone.HAND)
    executor.cast(
        "P0",
        dualcaster.object_id,
        choices={"trigger_targets": {"dualcaster:etb": original.object_id}},
    )
    pass_all(executor)
    trigger = state.objects[state.stack[-1]]
    assert trigger.object_kind is ObjectKind.TRIGGERED_ABILITY
    trigger_action = executor._created_action(trigger)
    assert trigger_action.targets == (TargetRef(original.object_id),)
    pass_all(executor)
    copy = state.objects[state.stack[-1]]
    assert copy.copy_kind is CopyKind.SPELL_COPY
    assert copy.was_cast is False and not copy.component_card_instance_ids
    pass_all(executor)
    assert copy.retired
    copy_successors = [
        obj for obj in state.objects.values() if obj.predecessor_object_id == copy.object_id
    ]
    assert len(copy_successors) == 1
    copy_successor = copy_successors[0]
    assert copy_successor.copy_kind is CopyKind.SPELL_COPY
    assert copy_successor.zone is Zone.GRAVEYARD
    assert copy_successor.retired and copy_successor.ceased_to_exist
    assert original.object_id in state.stack

    state2, executor2 = funded_game()
    first = add_card(executor2, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD)
    second = add_card(executor2, specs["Glint-Horn Buccaneer"], Zone.BATTLEFIELD)
    twin = add_card(executor2, specs["Twinflame"], Zone.HAND)
    executor2.cast(
        "P0",
        twin.object_id,
        (TargetRef(first.object_id), TargetRef(second.object_id)),
    )
    pass_all(executor2)
    tokens = [obj for obj in active_objects(state2) if obj.copy_kind is CopyKind.TOKEN_COPY]
    assert len(tokens) == 2
    token_ids = {token.object_id for token in tokens}
    assert all("Haste" in token.current_characteristics["keywords"] for token in tokens)
    assert all(not token.component_card_instance_ids for token in tokens)

    delayed_ids = tuple(state2.delayed_triggers)
    assert len(delayed_ids) == 2
    assert {state2.objects[trigger_id].source_object_id for trigger_id in delayed_ids} == token_ids

    executor2.begin_step("END")
    assert len(state2.stack) == 2
    pass_all(executor2)
    pass_all(executor2)
    assert not [obj for obj in active_objects(state2) if obj.copy_kind is CopyKind.TOKEN_COPY]
    for token in tokens:
        assert token.retired
        successors = [
            obj for obj in state2.objects.values() if obj.predecessor_object_id == token.object_id
        ]
        assert len(successors) == 1
        successor = successors[0]
        assert successor.copy_kind is CopyKind.TOKEN_COPY
        assert successor.zone is Zone.EXILE
        assert successor.retired and successor.ceased_to_exist


def test_curiosity_attachment_optional_trigger_and_aura_sba() -> None:
    state, executor = funded_game()
    specs = specs_by_name()
    add_library(executor, "P0", 1)
    creature = add_card(executor, specs["Glint-Horn Buccaneer"], Zone.BATTLEFIELD)
    curiosity = add_card(executor, specs["Curiosity"], Zone.HAND)
    executor.cast("P0", curiosity.object_id, (TargetRef(creature.object_id),))
    pass_all(executor)
    aura = active_objects(state, name="Curiosity")[0]
    assert aura.attached_to_ref == TargetRef(creature.object_id)
    executor.deal_damage_to_player(
        creature.object_id,
        "P1",
        2,
        choices={"optional": {"curiosity:damage-trigger": True}},
    )
    pass_all(executor)
    assert len(state.zones["HAND:P0"]) == 1
    executor.zones.move(creature.object_id, Zone.GRAVEYARD, "TEST", executor._event("TEST"))
    executor.check_state_based_actions()
    assert active_objects(state, name="Curiosity")[0].zone is Zone.GRAVEYARD


def test_zone_successors_are_fresh_and_same_zone_reincarnation_is_new_identity() -> None:
    state, executor = funded_game()
    specs = specs_by_name()
    card = add_card(executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD)
    card.counters["PLUS1_PLUS1"] = 3
    card.marked_damage = 1
    card.current_characteristics["until_end_of_turn"] = {"power": 99}
    card.permanent_status["tap"] = "TAPPED"
    successor = executor.zones.move(card.object_id, Zone.GRAVEYARD, "TEST", executor._event("TEST"))
    assert successor is not None
    assert successor.counters == {} and successor.marked_damage == 0
    assert successor.attached_to_ref is None and successor.permanent_status is None
    assert "until_end_of_turn" not in successor.current_characteristics
    assert successor.controller is None

    exile = executor.zones.move(successor.object_id, Zone.EXILE, "TEST", executor._event("TEST"))
    assert exile is not None
    reexiled = executor.zones.reincarnate_same_zone(
        exile.object_id, "REEXILE", executor._event("TEST")
    )
    command = executor.zones.move(reexiled.object_id, Zone.COMMAND, "TEST", executor._event("TEST"))
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
                successor.object_id,
                exile.object_id,
                reexiled.object_id,
                command.object_id,
                face_down.object_id,
                reentered.object_id,
            }
        )
        == 7
    )


def test_identity_component_copy_and_controller_invariants() -> None:
    state, executor = funded_game()
    specs = specs_by_name()
    hand = add_card(executor, specs["Opt"], Zone.HAND)
    assert hand.controller is None
    duplicate = GameObject(
        "opaque-id-that-must-not-be-parsed",
        ObjectKind.CARD_IN_ZONE,
        Zone.EXILE,
        "P0",
        None,
        hand.component_card_instance_ids,
    )
    state.objects[duplicate.object_id] = duplicate
    with pytest.raises(IllegalAction):
        executor.identity.validate_active_components()
    state.objects.pop(duplicate.object_id)
    assert executor.identity.resolve_reference(TargetRef(hand.object_id)) is hand

    spell = executor.cast("P0", hand.object_id)
    assert spell.controller == "P0"
    trigger = executor._queue_trigger(
        spell,
        {
            "ability_id": "test:trigger",
            "kind": "TRIGGERED",
            "trigger": "TEST",
            "target_schema": {"kind": "NONE", "min": 0, "max": 0, "unique": True},
            "effect": {"kind": "NONE"},
        },
        {},
    )
    assert trigger.owner is None and trigger.controller == "P0"
    executor.identity.validate_object_schema()


def test_reference_modes_lki_and_continuity_fail_closed() -> None:
    state, executor = funded_game()
    card = add_card(executor, specs_by_name()["Opt"], Zone.HAND)
    old_id = card.object_id
    grave = executor.zones.move(old_id, Zone.GRAVEYARD, "TEST", executor._event("TEST"))
    assert grave is not None
    with pytest.raises(IllegalAction):
        executor.identity.resolve_reference(TargetRef(old_id))
    with pytest.raises(IllegalAction):
        executor.identity.resolve_reference(TargetRef(old_id, ReferenceMode.LAST_KNOWN_INFORMATION))
    lki = executor.identity.resolve_reference(
        TargetRef(old_id, ReferenceMode.LAST_KNOWN_INFORMATION, authority="CR-608.2h")
    )
    assert isinstance(lki, LKISnapshot)
    tracked = executor.identity.resolve_reference(
        TargetRef(
            old_id,
            ReferenceMode.SUCCESSOR_TRACKING,
            "SAME_EFFECT_FINDS_MOVED_OBJECT",
        )
    )
    assert tracked is grave
    hand = executor.zones.move(grave.object_id, Zone.HAND, "TEST", executor._event("TEST"))
    assert hand is not None
    with pytest.raises(IllegalAction):
        executor.identity.resolve_reference(
            TargetRef(
                grave.object_id,
                ReferenceMode.SUCCESSOR_TRACKING,
                "SAME_EFFECT_FINDS_MOVED_OBJECT",
            )
        )
    with pytest.raises(UnsupportedCapability):
        executor.identity.resolve_reference(
            TargetRef(old_id, ReferenceMode.SUCCESSOR_TRACKING, "STICKER_RETENTION")
        )


def test_commander_optional_return_and_commander_damage_terminal() -> None:
    state, executor = funded_game()
    commander = add_card(
        executor,
        specs_by_name()["Malcolm, Keen-Eyed Navigator"],
        Zone.BATTLEFIELD,
        commander=True,
    )
    grave = executor.zones.move(
        commander.object_id, Zone.GRAVEYARD, "DESTROY", executor._event("DESTROY")
    )
    assert grave is not None
    executor.check_state_based_actions()
    assert grave.object_id in state.pending_commander_choices
    declined = executor.commander_return_choice("P0", grave.object_id, False)
    assert declined.zone is Zone.GRAVEYARD and state.choices[-1].selected == "DECLINE"
    executor.check_state_based_actions()
    assert grave.object_id not in state.pending_commander_choices

    moved_again = executor.zones.move(grave.object_id, Zone.EXILE, "TEST", executor._event("TEST"))
    assert moved_again is not None
    executor.check_state_based_actions()
    assert state.pending_commander_choices == [moved_again.object_id]

    state2, executor2 = funded_game()
    commander2 = add_card(
        executor2,
        specs_by_name()["Malcolm, Keen-Eyed Navigator"],
        Zone.BATTLEFIELD,
        commander=True,
    )
    executor2.deal_damage_to_player(commander2.object_id, "P1", 21, combat=True)
    assert state2.terminal.status == "TERMINAL"
    assert state2.players["P1"].loss_reasons == ["COMMANDER_DAMAGE"]


def test_cleanup_discard_trigger_priority_and_repeated_cleanup() -> None:
    state, executor = funded_game()
    specs = specs_by_name()
    glint = add_card(executor, specs["Glint-Horn Buccaneer"], Zone.BATTLEFIELD)
    hand = [add_card(executor, specs["Opt"], Zone.HAND) for _ in range(8)]
    glint.marked_damage = 1
    executor.cleanup((hand[0].object_id,))
    assert glint.marked_damage == 0
    assert state.turn.cleanup_iteration == 1
    assert state.turn.cleanup_repeat_pending
    assert state.objects[state.stack[-1]].object_kind is ObjectKind.TRIGGERED_ABILITY
    pass_all(executor)
    pass_all(executor)
    assert state.turn.cleanup_iteration == 2
    assert not state.turn.cleanup_repeat_pending
    assert len(state.zones["HAND:P0"]) == 7


def test_hidden_observation_masks_library_opponent_hand_and_face_down_identity() -> None:
    state, executor = funded_game()
    specs = specs_by_name()
    own = add_card(executor, specs["Opt"], Zone.HAND)
    add_card(executor, specs["Mountain"], Zone.LIBRARY)
    add_card(executor, specs["Sol Ring"], Zone.HAND, owner="P1")
    hidden_command = add_card(
        executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.COMMAND, face_down=True
    )
    service = ObservationService(state)
    first = service.observe("P0")
    encoded = json.dumps(first)
    assert "Mountain" not in encoded and "Sol Ring" not in encoded
    assert all(obj["identity"] is None for obj in first["objects"] if obj["face_down"])
    own_entry = next(obj for obj in first["objects"] if obj["identity"] == "Opt")
    assert service.resolve_handle("P0", first["generation"], own_entry["handle"]) is own
    hidden_entry = next(obj for obj in first["objects"] if obj["face_down"])
    assert (
        service.resolve_handle("P0", first["generation"], hidden_entry["handle"]) is hidden_command
    )
    service.observe("P0")
    with pytest.raises(IllegalAction):
        service.resolve_handle("P0", first["generation"], own_entry["handle"])


def test_identity_shuffle_and_policy_rng_domains_are_independent() -> None:
    state, executor = funded_game()
    before = {name: stream.draw_count for name, stream in state.rng_streams.items()}
    executor.identity.new_id("object")
    after_identity = {name: stream.draw_count for name, stream in state.rng_streams.items()}
    assert after_identity["identity"] == before["identity"] + 1
    assert after_identity["shuffle"] == before["shuffle"]
    assert after_identity["policy"] == before["policy"]
    executor.identity.random_index("shuffle", 3, "test-shuffle")
    executor.identity.random_index("policy", 3, "test-policy")
    assert state.rng_streams["shuffle"].draw_count == before["shuffle"] + 1
    assert state.rng_streams["policy"].draw_count == before["policy"] + 1
    assert state.rng_streams["identity"].domain != state.rng_streams["shuffle"].domain
    assert state.rng_streams["shuffle"].domain != state.rng_streams["policy"].domain


def test_hash_allowlist_schema_and_float_rejection() -> None:
    state, executor = funded_game()
    card = add_card(executor, specs_by_name()["Sol Ring"], Zone.HAND)
    document = state_hash_document(state)
    assert tuple(document) == HASH_INCLUDED_ROOTS
    assert document["schema_version"] == "identity-state-v2.0.0"
    original = state_hash(state)
    state.events.append(Event("history-only", "TEST", None))
    assert state_hash(state) == original
    state.players["P0"].life -= 1
    assert state_hash(state) != original
    card.current_characteristics["float"] = 0.5
    with pytest.raises(TypeError):
        state_hash(state)


def test_replay_executes_recorded_actions_and_rejects_tampering_in_fresh_process(
    tmp_path: Path,
) -> None:
    state, executor = funded_game()
    ring = add_card(executor, specs_by_name()["Sol Ring"], Zone.HAND)
    executor.cast("P0", ring.object_id)
    pass_all(executor)
    recorded = transcript(state)
    replayed = validate_replay(recorded)
    assert state_hash(replayed) == state_hash(state)

    variants: list[dict[str, object]] = []
    omitted = deepcopy(recorded)
    omitted["commands"] = omitted["commands"][:-1]
    variants.append(omitted)
    duplicated = deepcopy(recorded)
    duplicated["commands"] = duplicated["commands"] + [duplicated["commands"][-1]]
    variants.append(duplicated)
    reordered = deepcopy(recorded)
    reordered["commands"] = list(reversed(reordered["commands"]))
    variants.append(reordered)
    altered = deepcopy(recorded)
    altered["commands"][0]["arguments"]["actor"] = "P1"
    variants.append(altered)
    for variant in variants:
        without_digest = dict(variant)
        without_digest.pop("digest")
        variant["digest"] = _digest(without_digest)
        with pytest.raises(ReplayError):
            validate_replay(variant)

    transcript_path = tmp_path / "transcript.json"
    transcript_path.write_text(json.dumps(recorded), encoding="utf-8")
    code = (
        "import json,sys;"
        "from mtg_kernel.replay import validate_replay;"
        "from mtg_kernel.hashing import state_hash;"
        "print(state_hash(validate_replay(json.load(open(sys.argv[1])))))"
    )
    fresh = subprocess.check_output(
        [sys.executable, "-c", code, str(transcript_path)], text=True
    ).strip()
    assert fresh == state_hash(state)


def test_terminal_state_stops_further_actions_and_external_objects_never_enter_player_zones() -> (
    None
):
    state, executor = funded_game()
    external = add_external_public_object(
        executor,
        "external:creature",
        Zone.BATTLEFIELD,
        "P1",
        "P1",
        {"name": "External Creature", "card_types": ["Creature"], "toughness": 2},
    )
    executor.zones.move(external.object_id, Zone.GRAVEYARD, "TEST", executor._event("TEST"))
    assert state.external_object_ledger[-1]["owner"] == "P1"
    assert not any("external:creature" in objects for objects in state.zones.values())
    state.players["P1"].life = 0
    executor.check_state_based_actions()
    with pytest.raises(IllegalAction):
        executor.begin_step("UPKEEP")


def test_activated_abilities_require_priority_including_standalone_mana_abilities() -> None:
    state, executor = funded_game()
    specs = specs_by_name()
    lantern = add_card(executor, specs["Soul-Guide Lantern"], Zone.BATTLEFIELD)
    island = add_card(executor, specs["Island"], Zone.BATTLEFIELD)
    state.turn.priority_holder_id = "P1"
    state.players["P0"].mana_pool["U"] = 0

    before = state_hash(state)
    with pytest.raises(IllegalAction, match="does not have priority"):
        executor.activate("P0", lantern.object_id, "lantern:exile-opponents")
    assert state_hash(state) == before

    with pytest.raises(IllegalAction, match="does not have priority"):
        executor.activate("P0", island.object_id, "island:mana-u")
    assert state_hash(state) == before

    state.turn.priority_holder_id = "P0"
    executor.activate("P0", island.object_id, "island:mana-u")
    assert state.players["P0"].mana_pool["U"] == 1
    assert state.turn.priority_holder_id == "P0"


def test_stack_resolution_requires_completed_priority_pass_transition() -> None:
    state, executor = funded_game()
    sol_ring_card = add_card(executor, specs_by_name()["Sol Ring"], Zone.HAND)
    spell = executor.cast("P0", sol_ring_card.object_id)
    cast_action = executor._created_action(spell)
    assert state.stack[-1] == spell.object_id
    assert cast_action.action_id in state.pending_actions
    before = state_hash(state)

    with pytest.raises(IllegalAction, match="only after all players pass"):
        executor.resolve_top()
    assert state_hash(state) == before
    assert state.stack[-1] == spell.object_id

    with pytest.raises(TypeError):
        executor.resolve_top(_all_players_passed=True)  # type: ignore[call-arg]
    assert state_hash(state) == before
    assert state.stack[-1] == spell.object_id

    with pytest.raises(IllegalAction, match="only after all players pass"):
        executor.execute_replay_command({"operation": "resolve_top", "arguments": {}})
    assert state_hash(state) == before
    assert state.stack[-1] == spell.object_id

    pass_all(executor)

    assert state.objects[spell.object_id].retired
    permanents = active_objects(state, name="Sol Ring", kind=ObjectKind.PERMANENT)
    assert len(permanents) == 1
    assert permanents[0].object_id != spell.object_id
    assert permanents[0].zone is Zone.BATTLEFIELD
    assert cast_action.action_id not in state.pending_actions


def test_lethal_damage_defers_state_based_actions_until_resolution_finishes() -> None:
    state, executor = funded_game()
    specs = specs_by_name()
    state.players["P1"].life = 1
    add_library(executor, "P0", 1)
    glint = add_card(executor, specs["Glint-Horn Buccaneer"], Zone.BATTLEFIELD)
    glint.current_characteristics["attacking"] = True
    discarded = add_card(executor, specs["Opt"], Zone.HAND)
    executor.activate(
        "P0",
        glint.object_id,
        "glint-horn:attack-loot",
        choices={"discard_ids": [discarded.object_id]},
    )

    assert len(state.stack) == 2
    activated_id, trigger_id = state.stack
    assert state.objects[activated_id].object_kind is ObjectKind.ACTIVATED_ABILITY
    assert state.objects[trigger_id].object_kind is ObjectKind.TRIGGERED_ABILITY
    pass_all(executor)

    discarded_index = next(
        index for index, event in enumerate(state.events) if event.kind == "CARD_DISCARDED"
    )
    trigger_stack_index = next(
        index
        for index, event in enumerate(state.events)
        if event.kind == "TRIGGER_PUT_ON_STACK"
        and event.payload.get("object_id", trigger_id) == trigger_id
    )
    damage_index = next(
        index for index, event in enumerate(state.events) if event.kind == "DAMAGE_DEALT"
    )
    resolved_index = next(
        index
        for index, event in enumerate(state.events)
        if event.kind == "STACK_OBJECT_RESOLVED" and event.payload.get("object_id") == trigger_id
    )
    terminal_index = next(
        index for index, event in enumerate(state.events) if event.kind == "GAME_TERMINATED"
    )
    required_order = [
        discarded_index,
        trigger_stack_index,
        damage_index,
        resolved_index,
        terminal_index,
    ]
    assert required_order == sorted(required_order)
    assert len(set(required_order)) == len(required_order)
    assert terminal_index == len(state.events) - 1
    assert state.stack == [activated_id]
    assert state.terminal.status == "TERMINAL"
    assert state.players["P1"].loss_reasons == ["LIFE_TOTAL"]


def test_commit_clears_pending_action_for_removed_spell_copy() -> None:
    state, executor = funded_game()
    specs = specs_by_name()
    add_library(executor, "P0", 1)
    opt = add_card(executor, specs["Opt"], Zone.HAND)
    original = executor.cast("P0", opt.object_id)
    cause = Action(executor.identity.new_id("action"), "COPY_EFFECT", "P0")
    state.actions.append(cause)
    copy = executor.copy_spell(original, "P0", None, cause)
    copy_action = executor._created_action(copy)
    original_action = executor._created_action(original)
    assert copy_action.action_id != original_action.action_id
    assert copy_action.action_id in state.pending_actions
    assert original_action.action_id in state.pending_actions

    commit = add_card(executor, specs["Commit // Memory"], Zone.HAND)
    commit_spell = executor.cast("P0", commit.object_id, (TargetRef(copy.object_id),), face=0)
    commit_action = executor._created_action(commit_spell)
    assert commit_action.action_id in state.pending_actions
    pass_all(executor)

    assert copy_action.action_id not in state.pending_actions
    assert commit_action.action_id not in state.pending_actions
    assert original_action.action_id in state.pending_actions
    assert original.object_id in state.stack
    assert copy.object_id not in state.stack
    assert commit_spell.retired

    placement_event = next(
        event
        for event in state.events
        if event.kind == "PUT_IN_LIBRARY" and event.cause_action_id == commit_action.action_id
    )
    assert placement_event.payload["target_object_id"] == copy.object_id
    assert placement_event.payload["position"] == "SECOND_FROM_TOP"

    change = next(
        change
        for change in state.zone_changes
        if change.from_object_id == copy.object_id and change.cause == "COMMIT"
    )
    assert change.to_zone is Zone.LIBRARY
    assert change.to_object_id is not None
    successor = state.objects[change.to_object_id]
    assert successor.predecessor_object_id == copy.object_id
    assert successor.zone is Zone.LIBRARY
    assert successor.retired and successor.ceased_to_exist


def test_terminal_damage_does_not_put_waiting_triggers_on_stack() -> None:
    state, executor = funded_game()
    malcolm = add_card(
        executor,
        specs_by_name()["Malcolm, Keen-Eyed Navigator"],
        Zone.BATTLEFIELD,
    )
    state.players["P1"].life = 1

    executor.deal_damage_to_player(malcolm.object_id, "P1", 1, combat=True)

    assert state.terminal.status == "TERMINAL"
    assert not state.stack
    assert state.events[-1].kind == "GAME_TERMINATED"
    terminal_index = next(
        index for index, event in enumerate(state.events) if event.kind == "GAME_TERMINATED"
    )
    assert not any(
        event.kind == "TRIGGER_PUT_ON_STACK" for event in state.events[terminal_index + 1 :]
    )
