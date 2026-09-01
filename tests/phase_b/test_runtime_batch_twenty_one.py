"""Direct production-path evidence for Spell Pierce and Syncopate."""

from __future__ import annotations

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import IllegalAction, UnsupportedCapability
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import TargetRef, Zone

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


def cast_opt_from_p1(state, executor, specs, *, generic_mana: int = 0):
    state.players["P1"].mana_pool["U"] = 1
    state.players["P1"].mana_pool["C"] = generic_mana
    opt = add_card(executor, specs["Opt"], Zone.HAND, owner="P1")
    executor.pass_priority("P0")
    spell = executor.cast("P1", opt.object_id, choices={"scry_to_bottom": False})
    executor.pass_priority("P1")
    return spell


def test_spell_pierce_requires_qualifying_target_and_explicit_controller_decision() -> None:
    state, executor, specs = game_with_exact_mana("runtime-twenty-one-pierce-predicate")
    state.turn.active_player_id = "P1"
    state.turn.priority_holder_id = "P1"
    state.turn.phase = "PRECOMBAT_MAIN"
    state.players["P1"].mana_pool["R"] = 2
    state.players["P0"].mana_pool["U"] = 1
    creature = add_card(executor, specs["Wily Goblin"], Zone.HAND, owner="P1")
    creature_spell = executor.cast("P1", creature.object_id)
    executor.pass_priority("P1")
    pierce = add_card(executor, specs["Spell Pierce"], Zone.HAND, owner="P0")

    before = state_hash(state)
    with pytest.raises(IllegalAction, match="counter predicate"):
        executor.cast(
            "P0",
            pierce.object_id,
            targets=(TargetRef(creature_spell.object_id),),
            choices={"counter_payment": {"player_id": "P1", "pay": False}},
        )
    assert state_hash(state) == before

    state, executor, specs = game_with_exact_mana("runtime-twenty-one-pierce-choice")
    state.players["P0"].mana_pool["U"] = 1
    target_spell = cast_opt_from_p1(state, executor, specs)
    pierce = add_card(executor, specs["Spell Pierce"], Zone.HAND, owner="P0")
    executor.cast("P0", pierce.object_id, targets=(TargetRef(target_spell.object_id),))
    executor.pass_priority("P0")
    before = state_hash(state)
    with pytest.raises(UnsupportedCapability, match="unmodeled opponent"):
        executor.pass_priority("P1")
    assert state_hash(state) == before
    assert len(state.stack) == 2


def test_spell_pierce_decline_counters_qualifying_spell_and_records_choice() -> None:
    state, executor, specs = game_with_exact_mana("runtime-twenty-one-pierce-decline")
    state.players["P0"].mana_pool["U"] = 1
    target_spell = cast_opt_from_p1(state, executor, specs, generic_mana=2)
    pierce = add_card(executor, specs["Spell Pierce"], Zone.HAND, owner="P0")
    executor.cast(
        "P0",
        pierce.object_id,
        targets=(TargetRef(target_spell.object_id),),
        choices={"counter_payment": {"player_id": "P1", "pay": False}},
    )

    pass_all(executor)

    assert not state.stack
    assert len(active_named(state, "Opt", Zone.GRAVEYARD)) == 1
    assert state.players["P1"].mana_pool["C"] == 2
    decision = next(choice for choice in state.choices if choice.kind == "COUNTER_UNLESS_PAY")
    assert decision.player_id == "P1"
    assert decision.selected["pay"] is False
    assert decision.selected["amount"] == 2
    assert decision.selected["payment"] == {}


def test_spell_pierce_controller_payment_preserves_target_and_records_mana() -> None:
    state, executor, specs = game_with_exact_mana("runtime-twenty-one-pierce-pay")
    state.players["P0"].mana_pool["U"] = 1
    add_card(executor, specs["Island"], Zone.LIBRARY, owner="P1")
    target_spell = cast_opt_from_p1(state, executor, specs, generic_mana=2)
    pierce = add_card(executor, specs["Spell Pierce"], Zone.HAND, owner="P0")
    executor.cast(
        "P0",
        pierce.object_id,
        targets=(TargetRef(target_spell.object_id),),
        choices={"counter_payment": {"player_id": "P1", "pay": True}},
    )

    pass_all(executor)

    assert state.stack == [target_spell.object_id]
    assert state.players["P1"].mana_pool["C"] == 0
    decision = next(choice for choice in state.choices if choice.kind == "COUNTER_UNLESS_PAY")
    assert decision.player_id == "P1"
    assert decision.selected["schema_version"] == "counter-payment-choice-v4"
    assert decision.selected["decision_source"] == "EXPLICIT_ACTION_CHOICE"
    assert decision.selected["decision_owner"] == "P1"
    assert decision.selected["target_identity"] == "Opt"
    assert decision.selected["counter_destination"] == "GRAVEYARD"
    assert decision.selected["outcome"] == "PAY"
    assert decision.selected["pay"] is True
    assert decision.selected["amount"] == 2
    assert decision.selected["actual_required_payment"] == 2
    assert decision.selected["payment"] == {"C": 2}
    assert "target_object_id" not in decision.selected

    pass_all(executor)
    assert not state.stack
    assert len(active_named(state, "Opt", Zone.GRAVEYARD)) == 1
    assert len(state.zones.get("HAND:P1", ())) == 1


def test_syncopate_uses_x_for_payment_and_exiles_when_declined() -> None:
    state, executor, specs = game_with_exact_mana("runtime-twenty-one-syncopate-decline")
    state.players["P0"].mana_pool.update({"U": 1, "C": 3})
    target_spell = cast_opt_from_p1(state, executor, specs, generic_mana=3)
    syncopate = add_card(executor, specs["Syncopate"], Zone.HAND, owner="P0")
    executor.cast(
        "P0",
        syncopate.object_id,
        targets=(TargetRef(target_spell.object_id),),
        x_value=3,
        choices={"counter_payment": {"player_id": "P1", "pay": False}},
    )

    pass_all(executor)

    assert not state.stack
    assert len(active_named(state, "Opt", Zone.EXILE)) == 1
    decision = next(choice for choice in state.choices if choice.kind == "COUNTER_UNLESS_PAY")
    assert decision.selected["amount"] == 3
    assert decision.selected["actual_required_payment"] == 3
    assert decision.selected["counter_destination"] == "EXILE"
    assert decision.selected["pay"] is False

    state, executor, specs = game_with_exact_mana("runtime-twenty-one-syncopate-atomic")
    state.players["P0"].mana_pool.update({"U": 1, "C": 3})
    target_spell = cast_opt_from_p1(state, executor, specs, generic_mana=2)
    syncopate = add_card(executor, specs["Syncopate"], Zone.HAND, owner="P0")
    executor.cast(
        "P0",
        syncopate.object_id,
        targets=(TargetRef(target_spell.object_id),),
        x_value=3,
        choices={"counter_payment": {"player_id": "P1", "pay": True}},
    )
    executor.pass_priority("P0")
    before = state_hash(state)
    with pytest.raises(IllegalAction, match="cannot be paid legally"):
        executor.pass_priority("P1")
    assert state_hash(state) == before
    assert state.players["P1"].mana_pool["C"] == 2
    assert len(state.stack) == 2
