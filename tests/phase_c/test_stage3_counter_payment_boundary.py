"""Stage 3 acceptance tests for controlled counter-unless-pay decisions.

These tests are intentionally written against the post-PR-#101 semantic/resource
boundaries.  They do not import the PR #99 resolution-mana planner or any V2 policy.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import UnsupportedCapability
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import TargetRef, Zone
from mtg_kernel.replay import transcript, validate_replay
from mtg_kernel.serialization import state_to_data
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
            "stage3-test-counter-policy",
            "1" * 64,
            {"reason_code": f"STAGE3_TEST_{selected}"},
        )


def _setup_self_counter(
    *,
    provider: _CounterProvider | None,
    islands: int,
    explicit_payment: bool | None = None,
) -> tuple[object, object, object]:
    seed = f"stage3-counter-{provider.outcome if provider else 'explicit'}-{islands}"
    state, executor = new_game(PLAYERS, seed)
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    state.turn.phase = "PRECOMBAT_MAIN"
    state.players["P0"].mana_pool.update({symbol: 0 for symbol in MANA_SYMBOLS})
    state.players["P0"].mana_pool["U"] = 2
    for _ in range(islands):
        add_card(executor, specs["Island"], Zone.BATTLEFIELD, owner="P0")
    opt = add_card(executor, specs["Opt"], Zone.HAND, owner="P0")
    pierce = add_card(executor, specs["Spell Pierce"], Zone.HAND, owner="P0")
    state.replay_initial_state = state_to_data(state)
    if provider is not None:
        executor.bind_strategic_choice_provider(provider)
    target = executor.cast("P0", opt.object_id, choices={"scry_to_bottom": False})
    counter_choices = (
        {}
        if explicit_payment is None
        else {"counter_payment": {"player_id": "P0", "pay": explicit_payment}}
    )
    executor.cast(
        "P0",
        pierce.object_id,
        targets=(TargetRef(target.object_id),),
        choices=counter_choices,
    )
    assert sum(state.players["P0"].mana_pool.values()) == 0
    return state, executor, target


def _resolve_one_stack_object(executor: object) -> None:
    for _ in PLAYERS:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def _counter_choice(state: object) -> object:
    return next(choice for choice in state.choices if choice.kind == "COUNTER_UNLESS_PAY")


def test_payment_impossible_exposes_only_decline_from_shared_solver() -> None:
    provider = _CounterProvider("PAY", [])
    state, executor, target = _setup_self_counter(provider=provider, islands=0)
    _resolve_one_stack_object(executor)

    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request.legal_outcomes == ("DECLINE",)
    assert request.payment_result.feasible is False
    assert request.payment_result.canonical_allocation == ()
    assert not hasattr(request, "pay_mana_ability_plan")
    assert not hasattr(request.target, "handle")

    decision = _counter_choice(state)
    assert decision.selected["outcome"] == "DECLINE"
    assert decision.selected["pay_legally_available"] is False
    assert state.objects[target.object_id].retired


def test_payment_possible_uses_semantic_solver_result_then_rules_execution_and_replays() -> None:
    provider = _CounterProvider("PAY", [])
    state, executor, target = _setup_self_counter(provider=provider, islands=2)
    _resolve_one_stack_object(executor)

    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request.legal_outcomes == ("PAY", "DECLINE")
    assert request.payment_result.feasible is True
    assert {
        allocation.source_semantic_id for allocation in request.payment_result.canonical_allocation
    } == {"Island:mana-source"}
    assert sum(allocation.amount for allocation in request.payment_result.canonical_allocation) == 2
    assert not hasattr(request, "pay_mana_ability_plan")
    assert not hasattr(request.target, "handle")

    decision = _counter_choice(state)
    assert decision.selected["outcome"] == "PAY"
    assert decision.selected["pay_legally_available"] is True
    assert "mana_ability_plan" not in decision.selected
    assert "target_handle" not in decision.selected
    assert sum(decision.selected["payment"].values()) == 2

    tapped_islands = [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.zone is Zone.BATTLEFIELD
        and obj.controller == "P0"
        and obj.current_characteristics.get("name") == "Island"
        and obj.permanent_status is not None
        and obj.permanent_status.get("tap") == "TAPPED"
    ]
    assert len(tapped_islands) == 2
    assert target.object_id in state.stack

    replayed = validate_replay(transcript(state, seed=executor.seed))
    assert state_hash(replayed) == state_hash(state)


def test_decline_remains_a_distinct_legal_outcome_when_pay_is_available() -> None:
    provider = _CounterProvider("DECLINE", [])
    state, executor, target = _setup_self_counter(provider=provider, islands=2)
    _resolve_one_stack_object(executor)

    request = provider.requests[0]
    assert request.legal_outcomes == ("PAY", "DECLINE")
    assert request.payment_result.feasible is True
    decision = _counter_choice(state)
    assert decision.selected["outcome"] == "DECLINE"
    assert decision.selected["pay_legally_available"] is True
    assert state.objects[target.object_id].retired


def test_explicit_rules_choice_remains_supported_without_a_policy_provider() -> None:
    state, executor, target = _setup_self_counter(
        provider=None,
        islands=2,
        explicit_payment=False,
    )
    _resolve_one_stack_object(executor)

    decision = _counter_choice(state)
    assert decision.selected["decision_source"] == "EXPLICIT_ACTION_CHOICE"
    assert decision.selected["outcome"] == "DECLINE"
    assert decision.selected["pay_legally_available"] is True
    assert state.objects[target.object_id].retired


def test_unmodeled_opponent_payment_without_explicit_choice_fails_closed() -> None:
    seed = "stage3-counter-unmodeled-opponent"
    state, executor = new_game(PLAYERS, seed)
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    state.turn.phase = "PRECOMBAT_MAIN"
    for player in ("P0", "P1"):
        state.players[player].mana_pool.update({symbol: 0 for symbol in MANA_SYMBOLS})
        state.players[player].mana_pool["U"] = 2
    opt = add_card(executor, specs["Opt"], Zone.HAND, owner="P1")
    pierce = add_card(executor, specs["Spell Pierce"], Zone.HAND, owner="P0")
    state.turn.priority_holder_id = "P1"
    target = executor.cast("P1", opt.object_id, choices={"scry_to_bottom": False})
    state.turn.priority_holder_id = "P0"
    executor.cast("P0", pierce.object_id, targets=(TargetRef(target.object_id),))

    with pytest.raises(UnsupportedCapability, match="unmodeled opponent"):
        _resolve_one_stack_object(executor)
