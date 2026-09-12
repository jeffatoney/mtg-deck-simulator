"""Role-matrix regressions for Stage 3 strategic-choice ownership."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import UnsupportedCapability
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import TargetRef, Zone
from mtg_kernel.strategic_choices import CounterPaymentRequest, CounterPaymentSelection

PLAYERS = ("P0", "P1", "P2", "P3")
MANA_SYMBOLS = ("W", "U", "B", "R", "G", "C")


@dataclass
class _CounterProvider:
    outcome: str
    requests: list[CounterPaymentRequest]

    def choose_counter_payment(self, request: CounterPaymentRequest) -> CounterPaymentSelection:
        self.requests.append(request)
        selected = self.outcome if self.outcome in request.legal_outcomes else "DECLINE"
        return CounterPaymentSelection(
            selected,
            "stage3-ownership-test",
            "1" * 64,
            {"reason_code": f"STAGE3_OWNERSHIP_{selected}"},
        )


def _resolve_one_stack_object(executor: object) -> None:
    for _ in PLAYERS:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def _cast_counter(
    *,
    target_owner: str,
    counter_owner: str,
    bound_player: str,
    seed: str,
) -> tuple[object, object, _CounterProvider]:
    state, executor = new_game(PLAYERS, seed)
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    state.turn.phase = "PRECOMBAT_MAIN"
    for player in (target_owner, counter_owner):
        state.players[player].mana_pool.update({symbol: 0 for symbol in MANA_SYMBOLS})
        state.players[player].mana_pool["U"] = 2
    opt = add_card(executor, specs["Opt"], Zone.HAND, owner=target_owner)
    pierce = add_card(executor, specs["Spell Pierce"], Zone.HAND, owner=counter_owner)
    provider = _CounterProvider("PAY", [])
    executor.bind_strategic_choice_provider(provider, controlled_player_id=bound_player)
    state.turn.priority_holder_id = target_owner
    target = executor.cast(target_owner, opt.object_id, choices={"scry_to_bottom": False})
    state.turn.priority_holder_id = counter_owner
    executor.cast(counter_owner, pierce.object_id, targets=(TargetRef(target.object_id),))
    return state, executor, provider


def test_case_a_opponent_counters_controlled_spell_provider_may_choose() -> None:
    state, executor, provider = _cast_counter(
        target_owner="P0",
        counter_owner="P1",
        bound_player="P0",
        seed="stage3-ownership-a",
    )
    _resolve_one_stack_object(executor)
    assert len(provider.requests) == 1
    assert provider.requests[0].actor_id == "P0"
    decision = next(choice for choice in state.choices if choice.kind == "COUNTER_UNLESS_PAY")
    assert decision.player_id == "P0"
    assert decision.selected["decision_source"] == "STRATEGIC_PROVIDER"


def test_case_b_controlled_player_counters_opponent_spell_provider_must_not_choose() -> None:
    _state, executor, provider = _cast_counter(
        target_owner="P1",
        counter_owner="P0",
        bound_player="P0",
        seed="stage3-ownership-b",
    )
    with pytest.raises(UnsupportedCapability, match="unmodeled opponent"):
        _resolve_one_stack_object(executor)
    assert provider.requests == []


def test_case_c_controlled_player_counters_own_spell_provider_may_choose() -> None:
    state, executor, provider = _cast_counter(
        target_owner="P0",
        counter_owner="P0",
        bound_player="P0",
        seed="stage3-ownership-c",
    )
    _resolve_one_stack_object(executor)
    assert len(provider.requests) == 1
    assert provider.requests[0].actor_id == "P0"
    decision = next(choice for choice in state.choices if choice.kind == "COUNTER_UNLESS_PAY")
    assert decision.selected["decision_source"] == "STRATEGIC_PROVIDER"


def test_case_d_opponent_counters_own_spell_provider_must_not_choose() -> None:
    _state, executor, provider = _cast_counter(
        target_owner="P1",
        counter_owner="P1",
        bound_player="P0",
        seed="stage3-ownership-d",
    )
    with pytest.raises(UnsupportedCapability, match="unmodeled opponent"):
        _resolve_one_stack_object(executor)
    assert provider.requests == []


def test_case_e_third_player_counter_follows_payer_not_caster() -> None:
    state, executor, provider = _cast_counter(
        target_owner="P0",
        counter_owner="P2",
        bound_player="P0",
        seed="stage3-ownership-e-authorized",
    )
    _resolve_one_stack_object(executor)
    assert len(provider.requests) == 1
    assert provider.requests[0].actor_id == "P0"
    decision = next(choice for choice in state.choices if choice.kind == "COUNTER_UNLESS_PAY")
    assert decision.player_id == "P0"

    _state, blocked, blocked_provider = _cast_counter(
        target_owner="P1",
        counter_owner="P2",
        bound_player="P0",
        seed="stage3-ownership-e-blocked",
    )
    with pytest.raises(UnsupportedCapability, match="unmodeled opponent"):
        _resolve_one_stack_object(blocked)
    assert blocked_provider.requests == []
