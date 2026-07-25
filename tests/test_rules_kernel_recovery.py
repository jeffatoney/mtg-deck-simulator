from copy import deepcopy

import pytest

from mtg_sim.rules_kernel import (
    Action,
    CardInstance,
    ExternalObjectRef,
    GameObject,
    KernelError,
    KernelExecutor,
    KernelState,
    PermanentObject,
    TriggeredAbilityObject,
    Zone,
    replay,
)
from mtg_sim.structured_cards import VERTICAL_SLICE
from mtg_sim.game_executor import GameExecutor


def state_with(name: str, zone: Zone = Zone.HAND, owner: str = "self") -> tuple[KernelState, str]:
    state = KernelState()
    spec = VERTICAL_SLICE[name]
    state.definitions[spec.definition.definition_id] = spec.definition
    iid, oid = "card:1", "object:1"
    state.instances[iid] = CardInstance(
        iid, spec.definition.definition_id, owner, name == "Malcolm, Keen-Eyed Navigator"
    )
    state.objects[oid] = GameObject(oid, iid, owner, owner, zone)
    state.zones[(owner, zone)] = [oid]
    return state, oid


def test_sol_ring_and_lantern_use_real_stack_and_trigger_object():
    state, oid = state_with("Sol Ring")
    ex = KernelExecutor(state)
    ex.execute(Action("cast", "card:1"))
    assert state.stack == [oid] and not state.zones.get(("self", Zone.BATTLEFIELD))
    ex.execute(Action("resolve", object_id=oid))
    assert oid in state.zones[("self", Zone.BATTLEFIELD)]

    state, oid = state_with("Soul-Guide Lantern")
    grave = GameObject("grave:1", "grave-card", "self", "self", Zone.GRAVEYARD)
    state.objects[grave.object_id] = grave
    state.zones[("self", Zone.GRAVEYARD)] = [grave.object_id]
    ex = KernelExecutor(state)
    ex.execute(Action("cast", "card:1"))
    ex.execute(Action("resolve", object_id=oid))
    trigger = state.objects[state.stack[-1]]
    assert isinstance(trigger, TriggeredAbilityObject) and trigger.targets == ("grave:1",)


def test_game_executor_vertical_path_is_the_kernel_path():
    game = GameExecutor(1, 1, "phase_a", "recovery")
    state, oid = state_with("Sol Ring")
    game.kernel_state = state
    game.kernel = KernelExecutor(state)
    result = game.execute_kernel_actions([Action("cast", "card:1")])
    assert result.stack == [oid]


def test_commit_external_owner_ledger_and_targetless_memory():
    state, oid = state_with("Commit // Memory")
    state.external["opp-spell"] = ExternalObjectRef(
        "opp-spell", "opp1", "opp1", Zone.STACK, "spell", ("Instant",), targets=("malcolm",)
    )
    state.stack.append("opp-spell")
    ex = KernelExecutor(state)
    ex.execute(Action("cast", "card:1", face="Commit", targets=("opp-spell",)))
    ex.execute(Action("resolve", object_id=oid))
    assert state.external_ledger[-1].owner_id == "opp1"
    assert state.external_ledger[-1].library_position == 1
    assert "opp-spell" not in state.zones.get(("self", Zone.LIBRARY), [])

    state, oid = state_with("Commit // Memory", Zone.GRAVEYARD)
    ex = KernelExecutor(state)
    with pytest.raises(KernelError):
        ex.execute(Action("cast", "card:1", face="Memory", targets=("x",)))
    ex.execute(Action("cast", "card:1", face="Memory"))
    ex.execute(Action("resolve", object_id=oid))
    assert oid in state.zones[("self", Zone.EXILE)]


def test_cleanup_attack_commander_replacement_and_action_replay():
    state, oid = state_with("Glint-Horn Buccaneer", Zone.BATTLEFIELD)
    state.objects[oid] = PermanentObject(
        oid, "card:1", "self", "self", Zone.BATTLEFIELD, marked_damage=2, power=2, toughness=4
    )
    before = deepcopy(state)
    ex = KernelExecutor(state)
    ex.execute(Action("declare_attacker", object_id=oid))
    assert state.objects[oid].attacking
    ex.execute(Action("cleanup"))
    assert state.objects[oid].marked_damage == 0
    records = deepcopy(state.actions)
    replayed = replay(before, records)
    assert replayed.state_hash() == state.state_hash()

    state, oid = state_with("Malcolm, Keen-Eyed Navigator", Zone.BATTLEFIELD)
    KernelExecutor(state).zones.move(oid, Zone.GRAVEYARD, commander_to_command=True)
    assert state.objects[oid].current_zone is Zone.COMMAND


def test_pending_card_fails_closed_and_copy_ceases():
    state, _ = state_with("Island")
    state.definitions["pending"] = VERTICAL_SLICE["Island"].definition.__class__(
        "pending", "pending", "Pending", ("Artifact",)
    )
    state.instances["pending-card"] = CardInstance("pending-card", "pending", "self")
    state.objects["pending-object"] = GameObject(
        "pending-object", "pending-card", "self", "self", Zone.HAND
    )
    with pytest.raises(KernelError):
        KernelExecutor(state).execute(Action("cast", "pending-card"))
    token = GameObject("copy", None, "self", "self", Zone.STACK, copy=True)
    state.objects["copy"] = token
    state.stack.append("copy")
    KernelExecutor(state).zones.move("copy", Zone.LIBRARY)
    assert token.current_zone is Zone.VOID
