"""Stage 3 acceptance tests for controlled counter-unless-pay decisions.

These tests are intentionally written against the post-PR-#101 semantic/resource
boundaries. They do not import the PR #99 resolution-mana planner or any V2 policy.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

import mtg_kernel.resource_execution as resource_execution
from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import IllegalAction, ReplayError, UnsupportedCapability
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import TargetRef, Zone
from mtg_kernel.replay import transcript, validate_replay
from mtg_kernel.serialization import state_to_data
from mtg_kernel.strategic_choices import (
    CounterPaymentRequest,
    CounterPaymentSelection,
    CounterPaymentTarget,
    RecordedStrategicChoiceProvider,
)
from mtg_policy import (
    ContextualEvaluator,
    PolicyStrategicChoiceProvider,
    load_evaluator_config,
    load_policy_matrix,
)

PLAYERS = ("P0", "P1", "P2", "P3")
MANA_SYMBOLS = ("W", "U", "B", "R", "G", "C")
MICRO = 1_000_000


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


@dataclass
class _CapturingProductionProvider:
    provider: PolicyStrategicChoiceProvider
    requests: list[CounterPaymentRequest]

    def choose_counter_payment(self, request: CounterPaymentRequest) -> CounterPaymentSelection:
        self.requests.append(request)
        return self.provider.choose_counter_payment(request)


def _production_provider() -> PolicyStrategicChoiceProvider:
    bundle = next(
        item for item in load_policy_matrix() if item.policy_config_id == "anchor_balanced"
    )
    return PolicyStrategicChoiceProvider(bundle, ContextualEvaluator(load_evaluator_config()))


def _setup_self_counter(
    *,
    provider: object | None,
    islands: int,
    explicit_payment: bool | None = None,
) -> tuple[object, object, object]:
    provider_label = getattr(provider, "outcome", "custom") if provider else "explicit"
    seed = f"stage3-counter-{provider_label}-{islands}"
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


def _setup_syncopate_self_counter(
    *,
    provider: object,
    x_value: int,
) -> tuple[object, object, object]:
    seed = f"stage3-syncopate-x-{x_value}"
    state, executor = new_game(PLAYERS, seed)
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    state.turn.phase = "PRECOMBAT_MAIN"
    state.players["P0"].mana_pool.update({symbol: 0 for symbol in MANA_SYMBOLS})
    state.players["P0"].mana_pool["U"] = x_value + 2
    for _ in range(x_value):
        add_card(executor, specs["Island"], Zone.BATTLEFIELD, owner="P0")
    opt = add_card(executor, specs["Opt"], Zone.HAND, owner="P0")
    syncopate = add_card(executor, specs["Syncopate"], Zone.HAND, owner="P0")
    state.replay_initial_state = state_to_data(state)
    executor.bind_strategic_choice_provider(provider)
    target = executor.cast("P0", opt.object_id, choices={"scry_to_bottom": False})
    executor.cast(
        "P0",
        syncopate.object_id,
        targets=(TargetRef(target.object_id),),
        x_value=x_value,
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


def _controlled_islands(state: object) -> list[object]:
    return [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.zone is Zone.BATTLEFIELD
        and obj.controller == "P0"
        and obj.current_characteristics.get("name") == "Island"
    ]


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
        for obj in _controlled_islands(state)
        if obj.permanent_status is not None and obj.permanent_status.get("tap") == "TAPPED"
    ]
    assert len(tapped_islands) == 2
    assert target.object_id in state.stack

    replayed = validate_replay(transcript(state, seed=executor.seed))
    assert state_hash(replayed) == state_hash(state)


def test_existing_floating_pool_can_make_pay_feasible_without_source_activation() -> None:
    provider = _CounterProvider("PAY", [])
    state, executor, target = _setup_self_counter(provider=provider, islands=0)
    state.players["P0"].mana_pool["C"] = 2

    _resolve_one_stack_object(executor)

    request = provider.requests[0]
    assert request.payment_result.feasible is True
    assert request.legal_outcomes == ("PAY", "DECLINE")
    assert {
        allocation.source_semantic_id for allocation in request.payment_result.canonical_allocation
    } == {"floating:C"}
    decision = _counter_choice(state)
    assert decision.selected["outcome"] == "PAY"
    assert sum(decision.selected["payment"].values()) == 2
    assert sum(state.players["P0"].mana_pool.values()) == 0
    assert target.object_id in state.stack


def test_feasibility_does_not_activate_executor_before_policy_selection() -> None:
    holder: dict[str, object] = {}

    class _InspectingProvider:
        outcome = "PAY"

        def __init__(self) -> None:
            self.requests: list[CounterPaymentRequest] = []
            self.action_count_at_choice: int | None = None
            self.tap_states_at_choice: tuple[str, ...] = ()

        def choose_counter_payment(self, request: CounterPaymentRequest) -> CounterPaymentSelection:
            state = holder["state"]
            self.requests.append(request)
            self.action_count_at_choice = len(state.actions)
            self.tap_states_at_choice = tuple(
                str(obj.permanent_status.get("tap"))
                for obj in _controlled_islands(state)
                if obj.permanent_status is not None
            )
            return CounterPaymentSelection(
                "PAY",
                "stage3-inspecting-counter-policy",
                "2" * 64,
                {"reason_code": "STAGE3_TEST_PAY"},
            )

    provider = _InspectingProvider()
    state, executor, _target = _setup_self_counter(provider=provider, islands=2)
    holder["state"] = state
    action_count_before_resolution = len(state.actions)

    _resolve_one_stack_object(executor)

    assert provider.action_count_at_choice == action_count_before_resolution
    assert provider.tap_states_at_choice == ("UNTAPPED", "UNTAPPED")
    assert provider.requests[0].payment_result.feasible is True
    assert all(
        obj.permanent_status is not None and obj.permanent_status.get("tap") == "TAPPED"
        for obj in _controlled_islands(state)
    )


def test_decline_remains_a_distinct_legal_outcome_when_pay_is_available_and_replays() -> None:
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

    replayed = validate_replay(transcript(state, seed=executor.seed))
    assert state_hash(replayed) == state_hash(state)


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
    assert decision.selected["counter_destination"] == "GRAVEYARD"
    assert state.objects[target.object_id].retired


def test_request_rejects_legal_outcomes_that_disagree_with_shared_solver() -> None:
    infeasible_provider = _CounterProvider("DECLINE", [])
    _state, executor, _target = _setup_self_counter(
        provider=infeasible_provider,
        islands=0,
    )
    _resolve_one_stack_object(executor)
    request = infeasible_provider.requests[0]

    with pytest.raises(ValueError, match="outcomes do not match rules feasibility"):
        replace(request, legal_outcomes=("PAY", "DECLINE"))


def test_recorded_replay_rejects_outcome_not_legal_in_current_request() -> None:
    provider = _CounterProvider("DECLINE", [])
    _state, executor, _target = _setup_self_counter(provider=provider, islands=0)
    _resolve_one_stack_object(executor)
    request = provider.requests[0]

    recorded = RecordedStrategicChoiceProvider(
        [
            {
                "kind": "COUNTER_UNLESS_PAY",
                "selected": {
                    "schema_version": "counter-payment-choice-v4",
                    "decision_source": "STRATEGIC_PROVIDER",
                    "decision_owner": request.actor_id,
                    "effect_kind": request.effect_kind,
                    "target_identity": request.target.identity,
                    "amount": request.payment_amount,
                    "actual_required_payment": request.payment_amount,
                    "counter_destination": "GRAVEYARD",
                    "outcome": "PAY",
                    "evaluator_id": "recorded-test",
                    "evaluator_sha256": "3" * 64,
                    "diagnostics": {},
                },
            }
        ]
    )

    with pytest.raises(ReplayError, match="outcome is not legal"):
        recorded.choose_counter_payment(request)


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


def test_authorized_production_policy_records_full_evidence_and_freshly_recomputes() -> None:
    capturing = _CapturingProductionProvider(_production_provider(), [])
    state, executor, target = _setup_self_counter(provider=capturing, islands=2)
    _resolve_one_stack_object(executor)

    assert len(capturing.requests) == 1
    request = capturing.requests[0]
    decision = _counter_choice(state)
    selected = decision.selected

    assert selected["schema_version"] == "counter-payment-choice-v4"
    assert selected["decision_source"] == "STRATEGIC_PROVIDER"
    assert selected["actual_required_payment"] == 2
    assert selected["counter_destination"] == "GRAVEYARD"
    assert selected["legal_modeled_alternatives"] == ["PAY", "DECLINE"]
    assert selected["mana_weight_microunits"] == 8 * MICRO
    assert selected["mana_cost_valuation_microunits"] == 16 * MICRO
    assert selected["decline_incremental_value_microunits"] == 0
    assert isinstance(selected["target_evaluation"], dict)
    assert selected["evaluator_id"] == "contextual_combo_v1"
    assert len(selected["evaluator_sha256"]) == 64
    assert selected["reason_code"] in {
        "PAY_TARGET_VALUE_GREATER_THAN_PAYMENT_MANA_COST",
        "DECLINE_TARGET_VALUE_NOT_GREATER_THAN_PAYMENT_MANA_COST",
    }

    fresh = _production_provider().choose_counter_payment(request)
    assert fresh.outcome == selected["outcome"]
    assert fresh.evaluator_id == selected["evaluator_id"]
    assert fresh.evaluator_sha256 == selected["evaluator_sha256"]
    assert fresh.diagnostics["target_evaluation"] == selected["target_evaluation"]
    assert fresh.diagnostics["mana_cost_valuation_microunits"] == 16 * MICRO

    if selected["outcome"] == "PAY":
        assert target.object_id in state.stack
    else:
        assert state.objects[target.object_id].retired

    replayed = validate_replay(transcript(state, seed=executor.seed))
    assert state_hash(replayed) == state_hash(state)


def test_authorized_policy_characterizes_frozen_evaluator_dispositions_and_tie_declines() -> None:
    capture = _CounterProvider("DECLINE", [])
    _state, executor, _target = _setup_self_counter(provider=capture, islands=2)
    _resolve_one_stack_object(executor)
    base_request = capture.requests[0]
    provider = _production_provider()

    cases = (
        (CounterPaymentTarget("Synthetic Draw", 1, ("Instant",), ("DRAW",)), 13, "DECLINE"),
        (
            CounterPaymentTarget("Synthetic Interaction", 1, ("Instant",), ("COUNTER",)),
            9,
            "DECLINE",
        ),
        (CounterPaymentTarget("Synthetic Tutor", 1, ("Instant",), ("TRANSMUTE",)), 19, "PAY"),
        (
            CounterPaymentTarget(
                "Synthetic Combo Engine",
                1,
                ("Instant",),
                ("CREATE_SPELL_COPY",),
            ),
            23,
            "PAY",
        ),
        (CounterPaymentTarget("Curiosity", 1, ("Enchantment",), ("ATTACH_AURA",)), 29, "PAY"),
        (
            CounterPaymentTarget(
                "Synthetic Tie",
                1,
                ("Instant",),
                ("CANT_BE_BLOCKED", "SCRY"),
            ),
            16,
            "DECLINE",
        ),
    )

    for target, expected_score, expected_outcome in cases:
        selection = provider.choose_counter_payment(replace(base_request, target=target))
        assert selection.outcome == expected_outcome
        assert selection.diagnostics["target_evaluation"]["score_microunits"] == (
            expected_score * MICRO
        )
        assert selection.diagnostics["mana_cost_valuation_microunits"] == 16 * MICRO


def test_authorized_policy_fails_closed_if_frozen_mana_weight_drifts() -> None:
    provider = _production_provider()
    capture = _CounterProvider("DECLINE", [])
    _state, executor, _target = _setup_self_counter(provider=capture, islands=2)
    _resolve_one_stack_object(executor)
    request = capture.requests[0]

    from types import MappingProxyType

    drifted_weights = dict(provider.evaluator.config.weights)
    drifted_weights["mana"] = 4.0
    drifted_config = replace(
        provider.evaluator.config,
        weights=MappingProxyType(drifted_weights),
    )
    drifted = PolicyStrategicChoiceProvider(
        provider.bundle,
        ContextualEvaluator(drifted_config),
    )

    with pytest.raises(UnsupportedCapability, match="frozen mana weight of 8"):
        drifted.choose_counter_payment(request)


@pytest.mark.parametrize("x_value", [1, 3])
def test_syncopate_uses_cast_time_x_for_payment_valuation_and_records_exile(
    x_value: int,
) -> None:
    capturing = _CapturingProductionProvider(_production_provider(), [])
    state, executor, _target = _setup_syncopate_self_counter(
        provider=capturing,
        x_value=x_value,
    )
    _resolve_one_stack_object(executor)

    assert len(capturing.requests) == 1
    request = capturing.requests[0]
    selected = _counter_choice(state).selected
    assert request.effect_kind == "COUNTER_UNLESS_PAY_EXILE"
    assert request.payment_amount == x_value
    assert selected["amount"] == x_value
    assert selected["actual_required_payment"] == x_value
    assert selected["counter_destination"] == "EXILE"
    assert selected["mana_weight_microunits"] == 8 * MICRO
    assert selected["mana_cost_valuation_microunits"] == x_value * 8 * MICRO
    assert selected["decline_incremental_value_microunits"] == 0

    fresh = _production_provider().choose_counter_payment(request)
    assert fresh.outcome == selected["outcome"]
    assert fresh.diagnostics["mana_cost_valuation_microunits"] == x_value * 8 * MICRO

    replayed = validate_replay(transcript(state, seed=executor.seed))
    assert state_hash(replayed) == state_hash(state)


def _zero_pool(state: object, player_id: str = "P0") -> None:
    for symbol in MANA_SYMBOLS:
        state.players[player_id].mana_pool[symbol] = 0


@pytest.mark.parametrize(
    ("payment_color", "accepted"),
    [
        ("U", True),
        ("R", True),
        ("C", False),
        ("W", False),
        ("B", False),
        ("G", False),
    ],
)
def test_cascade_bluffs_exact_hybrid_payment_obeys_actual_activation_cost(
    payment_color: str,
    accepted: bool,
) -> None:
    state, executor = new_game(PLAYERS, f"stage3-review-cascade-exact-{payment_color}")
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    _zero_pool(state)
    state.players["P0"].mana_pool[payment_color] = 1
    bluffs = add_card(executor, specs["Cascade Bluffs"], Zone.BATTLEFIELD, owner="P0")
    before = state_hash(state)

    if not accepted:
        with pytest.raises(IllegalAction):
            executor.activate(
                "P0",
                bluffs.object_id,
                "cascade-bluffs:filter",
                choices={"mana_option": {"U": 2}},
                mana_payment={payment_color: 1},
            )
        assert state_hash(state) == before
        return

    executor.activate(
        "P0",
        bluffs.object_id,
        "cascade-bluffs:filter",
        choices={"mana_option": {"U": 2}},
        mana_payment={payment_color: 1},
    )
    action = state.actions[-1]
    assert action.payments["mana"] == {payment_color: 1}
    assert bluffs.permanent_status is not None
    assert bluffs.permanent_status["tap"] == "TAPPED"


def _setup_pierce_against_stack_spell(
    *,
    provider: object,
    target_name: str,
    target_kwargs: dict[str, object] | None = None,
    battlefield: tuple[str, ...] = (),
    opponent_mana_profile: str | None = None,
    cast_funding: dict[str, int] | None = None,
) -> tuple[object, object, object]:
    seed = f"stage3-review-{target_name}-{'-'.join(battlefield) or 'no-board'}"
    state, executor = new_game(PLAYERS, seed)
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    state.turn.phase = "PRECOMBAT_MAIN"
    _zero_pool(state)
    funding = {"U": 1, **(cast_funding or {})}
    for symbol, amount in funding.items():
        state.players["P0"].mana_pool[symbol] = int(amount)
    for name in battlefield:
        add_card(executor, specs[name], Zone.BATTLEFIELD, owner="P0")
    target_card = add_card(executor, specs[target_name], Zone.HAND, owner="P0")
    pierce = add_card(executor, specs["Spell Pierce"], Zone.HAND, owner="P0")
    state.replay_initial_state = state_to_data(state)
    executor.bind_strategic_choice_provider(provider)
    if opponent_mana_profile is not None:
        executor.opponent_mana_profile = opponent_mana_profile
    target = executor.cast("P0", target_card.object_id, **dict(target_kwargs or {}))
    executor.cast("P0", pierce.object_id, targets=(TargetRef(target.object_id),))
    return state, executor, target


def test_no_known_colors_excludes_orchard_and_fellwar_from_counter_payment() -> None:
    hidden = _CounterProvider("PAY", [])
    hidden_state, hidden_executor, _target = _setup_pierce_against_stack_spell(
        provider=hidden,
        target_name="Opt",
        target_kwargs={"choices": {"scry_to_bottom": False}},
        battlefield=("Exotic Orchard", "Fellwar Stone"),
        opponent_mana_profile="no_known_colors",
        cast_funding={"U": 2},
    )
    _resolve_one_stack_object(hidden_executor)
    assert hidden.requests[0].legal_outcomes == ("DECLINE",)
    assert hidden.requests[0].payment_result.feasible is False
    assert _counter_choice(hidden_executor.state).selected["outcome"] == "DECLINE"
    hidden_replayed = validate_replay(transcript(hidden_state, seed=hidden_executor.seed))
    assert state_hash(hidden_replayed) == state_hash(hidden_state)

    visible = _CounterProvider("PAY", [])
    state, executor, target = _setup_pierce_against_stack_spell(
        provider=visible,
        target_name="Opt",
        target_kwargs={"choices": {"scry_to_bottom": False}},
        battlefield=("Exotic Orchard", "Fellwar Stone"),
        opponent_mana_profile="blue_red_available",
        cast_funding={"U": 2},
    )
    _resolve_one_stack_object(executor)
    assert visible.requests[0].legal_outcomes == ("PAY", "DECLINE")
    assert visible.requests[0].payment_result.feasible is True
    decision = _counter_choice(state)
    assert decision.selected["outcome"] == "PAY"
    assert sum(decision.selected["payment"].values()) == 2
    tapped = [
        obj.current_characteristics.get("name")
        for obj in state.objects.values()
        if not obj.retired
        and obj.zone is Zone.BATTLEFIELD
        and obj.controller == "P0"
        and obj.permanent_status is not None
        and obj.permanent_status.get("tap") == "TAPPED"
        and obj.current_characteristics.get("name") in {"Exotic Orchard", "Fellwar Stone"}
    ]
    assert sorted(tapped) == ["Exotic Orchard", "Fellwar Stone"]
    assert target.object_id in state.stack
    replayed = validate_replay(transcript(state, seed=executor.seed))
    assert state_hash(replayed) == state_hash(state)


def test_signet_mountain_floating_u_honors_child_allocation_for_pay_three() -> None:
    provider = _CounterProvider("PAY", [])
    seed = "stage3-review-signet-mountain-u"
    state, executor = new_game(PLAYERS, seed)
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    state.turn.phase = "PRECOMBAT_MAIN"
    _zero_pool(state)
    state.players["P0"].mana_pool["U"] = 6
    add_card(executor, specs["Izzet Signet"], Zone.BATTLEFIELD, owner="P0")
    add_card(executor, specs["Mountain"], Zone.BATTLEFIELD, owner="P0")
    opt = add_card(executor, specs["Opt"], Zone.HAND, owner="P0")
    syncopate = add_card(executor, specs["Syncopate"], Zone.HAND, owner="P0")
    state.replay_initial_state = state_to_data(state)
    executor.bind_strategic_choice_provider(provider)
    target = executor.cast("P0", opt.object_id, choices={"scry_to_bottom": False})
    executor.cast("P0", syncopate.object_id, targets=(TargetRef(target.object_id),), x_value=3)
    assert state.players["P0"].mana_pool["U"] == 1

    _resolve_one_stack_object(executor)

    request = provider.requests[0]
    assert request.payment_amount == 3
    assert request.payment_result.feasible is True
    child = [
        allocation
        for allocation in request.payment_result.canonical_allocation
        if allocation.step_label.endswith(":source:Izzet Signet:mana-source")
    ]
    assert child
    assert {
        (item.source_semantic_id, item.color, item.requirement, item.amount) for item in child
    } == {("Mountain:mana-source", "R", "GENERIC:0", 1)}
    decision = _counter_choice(state)
    assert decision.selected["outcome"] == "PAY"
    assert sum(decision.selected["payment"].values()) == 3
    mountain = next(
        obj
        for obj in state.objects.values()
        if obj.current_characteristics.get("name") == "Mountain" and not obj.retired
    )
    signet = next(
        obj
        for obj in state.objects.values()
        if obj.current_characteristics.get("name") == "Izzet Signet" and not obj.retired
    )
    assert (
        mountain.permanent_status is not None and mountain.permanent_status.get("tap") == "TAPPED"
    )
    assert signet.permanent_status is not None and signet.permanent_status.get("tap") == "TAPPED"
    replayed = validate_replay(transcript(state, seed=executor.seed))
    assert state_hash(replayed) == state_hash(state)


def test_two_signets_and_floating_u_bind_chained_identical_sources_for_pay_four() -> None:
    provider = _CounterProvider("PAY", [])
    seed = "stage3-review-two-signets"
    state, executor = new_game(PLAYERS, seed)
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    state.turn.phase = "PRECOMBAT_MAIN"
    _zero_pool(state)
    state.players["P0"].mana_pool["U"] = 8
    add_card(executor, specs["Izzet Signet"], Zone.BATTLEFIELD, owner="P0")
    add_card(executor, specs["Izzet Signet"], Zone.BATTLEFIELD, owner="P0")
    opt = add_card(executor, specs["Opt"], Zone.HAND, owner="P0")
    syncopate = add_card(executor, specs["Syncopate"], Zone.HAND, owner="P0")
    state.replay_initial_state = state_to_data(state)
    executor.bind_strategic_choice_provider(provider)
    target = executor.cast("P0", opt.object_id, choices={"scry_to_bottom": False})
    executor.cast("P0", syncopate.object_id, targets=(TargetRef(target.object_id),), x_value=4)
    assert state.players["P0"].mana_pool["U"] == 2

    _resolve_one_stack_object(executor)

    request = provider.requests[0]
    assert request.payment_amount == 4
    assert request.payment_result.feasible is True
    child_allocations = {
        (
            allocation.source_semantic_id,
            allocation.color,
            allocation.requirement,
            allocation.amount,
        )
        for allocation in request.payment_result.canonical_allocation
        if ":source:Izzet Signet:mana-source" in allocation.step_label
    }
    assert child_allocations == {
        ("Izzet Signet:mana-source", "U", "GENERIC:0", 1),
        ("floating:U", "U", "GENERIC:0", 1),
    }
    decision = _counter_choice(state)
    assert decision.selected["outcome"] == "PAY"
    assert sum(decision.selected["payment"].values()) == 4
    tapped_signets = [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.current_characteristics.get("name") == "Izzet Signet"
        and obj.permanent_status is not None
        and obj.permanent_status.get("tap") == "TAPPED"
    ]
    assert len(tapped_signets) == 2
    replayed = validate_replay(transcript(state, seed=executor.seed))
    assert state_hash(replayed) == state_hash(state)


def test_path_marker_funding_signet_is_not_propagated_to_parent_payment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _CounterProvider("PAY", [])
    seed = "stage3-review-path-signet-marker"
    state, executor = new_game(PLAYERS, seed)
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    state.turn.phase = "PRECOMBAT_MAIN"
    _zero_pool(state)
    state.players["P0"].mana_pool["U"] = 2
    for name in ("Malcolm, Keen-Eyed Navigator", "Breeches, Brazen Plunderer"):
        add_card(executor, specs[name], Zone.COMMAND, owner="P0", commander=True)
    path = add_card(executor, specs["Path of Ancestry"], Zone.BATTLEFIELD, owner="P0")
    signet = add_card(executor, specs["Izzet Signet"], Zone.BATTLEFIELD, owner="P0")
    opt = add_card(executor, specs["Opt"], Zone.HAND, owner="P0")
    pierce = add_card(executor, specs["Spell Pierce"], Zone.HAND, owner="P0")
    state.replay_initial_state = state_to_data(state)
    executor.bind_strategic_choice_provider(provider)
    target = executor.cast("P0", opt.object_id, choices={"scry_to_bottom": False})
    executor.cast("P0", pierce.object_id, targets=(TargetRef(target.object_id),))

    marker_payments: list[tuple[dict[str, int], set[str]]] = []
    original_consume = resource_execution._consume_marked_payment

    def record_marker_payment(
        bound_executor: object,
        player_id: str,
        payment: dict[str, int],
        selected_marker_ids: set[str],
    ) -> None:
        marker_payments.append((dict(payment), set(selected_marker_ids)))
        original_consume(bound_executor, player_id, payment, selected_marker_ids)

    monkeypatch.setattr(resource_execution, "_consume_marked_payment", record_marker_payment)
    _resolve_one_stack_object(executor)

    request = provider.requests[0]
    child = [
        allocation
        for allocation in request.payment_result.canonical_allocation
        if allocation.step_label.endswith(":source:Izzet Signet:mana-source")
    ]
    assert len(child) == 1
    assert child[0].source_semantic_id == "Path of Ancestry:mana-source"
    assert child[0].requirement == "GENERIC:0"
    marked = [entry for entry in marker_payments if entry[1]]
    assert len(marked) == 1
    assert marked[0][0] == {child[0].color: 1}
    assert len(marked[0][1]) == 1
    assert marker_payments[-1][1] == set()
    assert not any(
        record.get("kind") == "MARKED_COMMANDER_MANA" for record in state.continuous_effects
    )
    assert path.permanent_status is not None and path.permanent_status["tap"] == "TAPPED"
    assert signet.permanent_status is not None and signet.permanent_status["tap"] == "TAPPED"
    assert target.object_id in state.stack
    replayed = validate_replay(transcript(state, seed=executor.seed))
    assert state_hash(replayed) == state_hash(state)


@pytest.mark.parametrize(
    ("mode", "expected_kind"),
    [
        ("damage", "DAMAGE_ALL_CREATURES_PLANESWALKERS"),
        ("artifacts", "DESTROY_ARTIFACTS_MV_LEQ"),
    ],
)
def test_brotherhoods_end_counter_payment_scores_only_selected_mode(
    mode: str,
    expected_kind: str,
) -> None:
    capturing = _CapturingProductionProvider(_production_provider(), [])
    state, executor, target = _setup_pierce_against_stack_spell(
        provider=capturing,
        target_name="Brotherhood's End",
        target_kwargs={"mode": mode},
        battlefield=("Island", "Island"),
        cast_funding={"U": 1, "R": 2, "C": 1},
    )
    _resolve_one_stack_object(executor)

    request = capturing.requests[0]
    assert request.target.identity == "Brotherhood's End"
    assert request.target.effect_kinds == (expected_kind,)
    selected = _counter_choice(state).selected
    assert selected["target_effect_kinds"] == [expected_kind]
    assert selected["outcome"] == "DECLINE"
    assert selected["reason_code"] == "DECLINE_TARGET_VALUE_NOT_GREATER_THAN_PAYMENT_MANA_COST"
    assert selected["target_evaluation"]["score_microunits"] == 9 * MICRO
    assert state.objects[target.object_id].retired
    fresh = _production_provider().choose_counter_payment(request)
    assert fresh.outcome == "DECLINE"
    assert fresh.diagnostics["target_evaluation"]["score_microunits"] == 9 * MICRO
    replayed = validate_replay(transcript(state, seed=executor.seed))
    assert state_hash(replayed) == state_hash(state)


def test_muddle_counter_target_excludes_hand_only_transmute_from_preserved_value() -> None:
    capturing = _CapturingProductionProvider(_production_provider(), [])
    seed = "stage3-cr6-muddle-stack-ability-relevance"
    state, executor = new_game(PLAYERS, seed)
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    state.turn.phase = "PRECOMBAT_MAIN"
    _zero_pool(state)
    state.players["P0"].mana_pool["U"] = 7
    for _ in range(3):
        add_card(executor, specs["Island"], Zone.BATTLEFIELD, owner="P0")
    opt = add_card(executor, specs["Opt"], Zone.HAND, owner="P0")
    muddle = add_card(executor, specs["Muddle the Mixture"], Zone.HAND, owner="P0")
    syncopate = add_card(executor, specs["Syncopate"], Zone.HAND, owner="P0")
    state.replay_initial_state = state_to_data(state)
    executor.bind_strategic_choice_provider(capturing)
    opt_spell = executor.cast("P0", opt.object_id, choices={"scry_to_bottom": False})
    muddle_spell = executor.cast(
        "P0",
        muddle.object_id,
        targets=(TargetRef(opt_spell.object_id),),
    )
    executor.cast(
        "P0",
        syncopate.object_id,
        targets=(TargetRef(muddle_spell.object_id),),
        x_value=3,
    )

    _resolve_one_stack_object(executor)

    request = capturing.requests[0]
    assert request.target.identity == "Muddle the Mixture"
    assert request.target.effect_kinds == ("COUNTER_IF",)
    selected = _counter_choice(state).selected
    assert selected["target_effect_kinds"] == ["COUNTER_IF"]
    assert selected["target_evaluation"]["score_microunits"] == 9 * MICRO
    assert selected["mana_cost_valuation_microunits"] == 24 * MICRO
    assert selected["actual_required_payment"] == 3
    assert selected["counter_destination"] == "EXILE"
    assert selected["outcome"] == "DECLINE"
    assert selected["reason_code"] == "DECLINE_TARGET_VALUE_NOT_GREATER_THAN_PAYMENT_MANA_COST"
    assert state.objects[muddle_spell.object_id].retired

    fresh = _production_provider().choose_counter_payment(request)
    assert fresh.outcome == "DECLINE"
    assert fresh.diagnostics["target_evaluation"]["score_microunits"] == 9 * MICRO
    assert fresh.diagnostics["mana_cost_valuation_microunits"] == 24 * MICRO
    replayed = validate_replay(transcript(state, seed=executor.seed))
    assert state_hash(replayed) == state_hash(state)


def test_nonmodal_curiosity_counter_target_retains_head_effect_kinds() -> None:
    provider = _CounterProvider("PAY", [])
    seed = "stage3-review-curiosity-nonmodal"
    state, executor = new_game(PLAYERS, seed)
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    state.turn.phase = "PRECOMBAT_MAIN"
    _zero_pool(state)
    state.players["P0"].mana_pool["U"] = 2
    add_card(executor, specs["Island"], Zone.BATTLEFIELD, owner="P0")
    add_card(executor, specs["Island"], Zone.BATTLEFIELD, owner="P0")
    creature = add_card(executor, specs["Dualcaster Mage"], Zone.BATTLEFIELD, owner="P0")
    curiosity = add_card(executor, specs["Curiosity"], Zone.HAND, owner="P0")
    pierce = add_card(executor, specs["Spell Pierce"], Zone.HAND, owner="P0")
    state.replay_initial_state = state_to_data(state)
    executor.bind_strategic_choice_provider(provider)
    target = executor.cast(
        "P0",
        curiosity.object_id,
        targets=(TargetRef(creature.object_id),),
    )
    executor.cast("P0", pierce.object_id, targets=(TargetRef(target.object_id),))

    _resolve_one_stack_object(executor)

    request = provider.requests[0]
    assert request.target.identity == "Curiosity"
    assert request.target.effect_kinds == ("ATTACH_AURA", "DRAW")
    assert _counter_choice(state).selected["outcome"] == "PAY"
    assert target.object_id in state.stack
    replayed = validate_replay(transcript(state, seed=executor.seed))
    assert state_hash(replayed) == state_hash(state)


def test_counter_payment_target_mana_value_includes_chosen_x_on_the_stack() -> None:
    capturing = _CapturingProductionProvider(_production_provider(), [])
    seed = "stage3-review-syncopate-as-target-x"
    state, executor = new_game(PLAYERS, seed)
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    state.turn.phase = "PRECOMBAT_MAIN"
    _zero_pool(state)
    state.players["P0"].mana_pool["U"] = 6
    add_card(executor, specs["Island"], Zone.BATTLEFIELD, owner="P0")
    add_card(executor, specs["Island"], Zone.BATTLEFIELD, owner="P0")
    opt = add_card(executor, specs["Opt"], Zone.HAND, owner="P0")
    syncopate = add_card(executor, specs["Syncopate"], Zone.HAND, owner="P0")
    pierce = add_card(executor, specs["Spell Pierce"], Zone.HAND, owner="P0")
    state.replay_initial_state = state_to_data(state)
    executor.bind_strategic_choice_provider(capturing)
    first = executor.cast("P0", opt.object_id, choices={"scry_to_bottom": False})
    target = executor.cast(
        "P0",
        syncopate.object_id,
        targets=(TargetRef(first.object_id),),
        x_value=3,
    )
    executor.cast("P0", pierce.object_id, targets=(TargetRef(target.object_id),))
    assert sum(state.players["P0"].mana_pool.values()) == 0

    _resolve_one_stack_object(executor)

    request = capturing.requests[0]
    assert request.target.identity == "Syncopate"
    assert request.target.mana_value == 4
    selected = _counter_choice(state).selected
    assert selected["target_mana_value"] == 4
    fresh = _production_provider().choose_counter_payment(request)
    assert fresh.diagnostics["target_evaluation"] == selected["target_evaluation"]
    replayed = validate_replay(transcript(state, seed=executor.seed))
    assert state_hash(replayed) == state_hash(state)
