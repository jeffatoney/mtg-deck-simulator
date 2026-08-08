from __future__ import annotations

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import TargetRef, Zone
from mtg_kernel.replay import transcript, validate_replay
from mtg_policy import ContextualEvaluator, bind_policy_strategic_choices, load_evaluator_config
from mtg_policy.config import load_policy_matrix


def _funded_game(seed: str):
    state, executor = new_game(("P0", "P1"), seed)
    for player in state.players.values():
        for symbol in ("W", "U", "B", "R", "G", "C"):
            player.mana_pool[symbol] = 10
    bundle = next(
        value for value in load_policy_matrix() if value.policy_config_id == "anchor_balanced"
    )
    bind_policy_strategic_choices(executor, bundle, ContextualEvaluator(load_evaluator_config()))
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    return state, executor, specs


def _pass_cycle(executor) -> None:
    for _ in range(2):
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def test_spell_pierce_payment_is_chosen_at_resolution_and_replays() -> None:
    seed = "counter-payment-policy-replay"
    state, executor, specs = _funded_game(seed)
    target_card = add_card(executor, specs["Opt"], Zone.HAND, owner="P0")
    pierce_card = add_card(executor, specs["Spell Pierce"], Zone.HAND, owner="P1")

    target_spell = executor.cast("P0", target_card.object_id)
    executor.pass_priority("P0")
    executor.cast(
        "P1",
        pierce_card.object_id,
        targets=(TargetRef(target_spell.object_id),),
    )
    _pass_cycle(executor)

    payment_choices = [choice for choice in state.choices if choice.kind == "COUNTER_UNLESS_PAY"]
    assert len(payment_choices) == 1
    selected = payment_choices[0].selected
    assert selected["player_id"] == "P0"
    assert selected["pay"] is True
    assert selected["amount"] == 2
    assert selected["chosen_at"] == "RESOLUTION"
    assert selected["diagnostics"]["strategy"] == "PAY_IF_CURRENT_POOL_CAN_PAY"
    assert target_spell.object_id in state.stack

    recorded = transcript(state, seed=seed)
    replayed = validate_replay(recorded)
    assert replayed.replay_commands == state.replay_commands
    replay_choices = [choice for choice in replayed.choices if choice.kind == "COUNTER_UNLESS_PAY"]
    assert len(replay_choices) == 1
    assert replay_choices[0].selected["pay"] is True
