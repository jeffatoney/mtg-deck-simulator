"""Regression coverage for V2 counter-unless-pay execution choices."""

from __future__ import annotations

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import Zone
from mtg_kernel.replay import transcript, validate_replay
from mtg_kernel.serialization import state_to_data
from mtg_policy import ActionBroker
from mtg_runs.phase_c_exploratory_v2 import _execute_v2_broker_action

PLAYERS = ("P0", "P1", "P2", "P3")
MANA_SYMBOLS = ("W", "U", "B", "R", "G", "C")


def test_v2_self_counter_unless_pay_records_decline_and_replays() -> None:
    seed = "exploratory-v2-counter-unless-pay"
    state, executor = new_game(PLAYERS, seed)
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    state.turn.phase = "PRECOMBAT_MAIN"
    state.players["P0"].mana_pool.update({symbol: 0 for symbol in MANA_SYMBOLS})
    state.players["P0"].mana_pool["U"] = 2

    opt = add_card(executor, specs["Opt"], Zone.HAND, owner="P0")
    add_card(executor, specs["Spell Pierce"], Zone.HAND, owner="P0")
    state.replay_initial_state = state_to_data(state)
    target_spell = executor.cast("P0", opt.object_id, choices={"scry_to_bottom": False})

    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()
    selected = next(
        action
        for action in actions
        if action.kind == "CAST"
        and action.identity == "Spell Pierce"
        and "COUNTER_UNLESS_PAY" in action.tags
    )
    _execute_v2_broker_action(
        executor,
        broker,
        int(observation["generation"]),
        selected,
    )

    for _ in PLAYERS:
        holder = state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)

    decision = next(choice for choice in state.choices if choice.kind == "COUNTER_UNLESS_PAY")
    assert decision.player_id == "P0"
    assert decision.selected["pay"] is False
    assert decision.selected["amount"] == 2
    assert decision.selected["payment"] == {}
    assert not state.stack
    assert state.objects[target_spell.object_id].retired

    replayed = validate_replay(transcript(state, seed=seed))
    assert state_hash(replayed) == state_hash(state)
