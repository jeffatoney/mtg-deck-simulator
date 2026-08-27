"""Fast minimal-state contracts for the shared solver-to-executor boundary."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from unittest.mock import patch

import pytest

import mtg_kernel.replay as replay_module
import mtg_kernel.resource_execution as resource_execution
from mtg_kernel.engine import GameExecutor
from mtg_kernel.errors import IllegalAction, ReplayError, UnsupportedCapability
from mtg_kernel.factory import add_card
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import (
    CardInstance,
    CardSpec,
    GameObject,
    GameState,
    ObjectKind,
    PlayerState,
    TargetRef,
    TurnState,
    Zone,
)
from mtg_kernel.phase_b_marked_mana import (
    MARKED_COMMANDER_MANA_KIND,
    PATH_SHARED_TYPE_TRIGGER,
)
from mtg_kernel.resource_payment import (
    PaymentStep,
    PaymentWindow,
    ResourcePaymentResult,
)
from mtg_kernel.replay import transcript, validate_replay
from mtg_kernel.resource_sources import solve_state_payment
from mtg_kernel.serialization import state_to_data
from mtg_kernel.strategic_choices import (
    CounterPaymentRequest,
    CounterPaymentSelection,
)

PLAYER = "P0"
COLORS = ("W", "U", "B", "R", "G", "C")


def _mana_source(
    object_id: str,
    name: str,
    effect: dict[str, object],
    *,
    activation_cost: str = "",
    marked: bool = False,
) -> GameObject:
    cost: dict[str, object] = {"tap": True}
    if activation_cost:
        cost["mana"] = activation_cost
    abilities: list[dict[str, object]] = [
        {
            "ability_id": f"{object_id}:mana",
            "kind": "ACTIVATED",
            "cost": cost,
            "target_schema": {"kind": "NONE", "min": 0, "max": 0, "unique": True},
            "mana_ability": True,
            "effect": effect,
        }
    ]
    if marked:
        abilities.append(
            {
                "ability_id": f"{object_id}:spent",
                "kind": "TRIGGERED",
                "trigger": PATH_SHARED_TYPE_TRIGGER,
                "effect": {"kind": "SCRY", "count": 1},
            }
        )
    return GameObject(
        object_id,
        ObjectKind.PERMANENT,
        Zone.BATTLEFIELD,
        PLAYER,
        PLAYER,
        current_characteristics={
            "name": name,
            "card_types": ["Artifact"],
            "abilities": abilities,
        },
        permanent_status={"tap": "UNTAPPED", "controller_since_turn": "1"},
    )


def _minimal_state(
    *sources: GameObject,
    floating: dict[str, int] | None = None,
    commander_colors: tuple[str, ...] = (),
) -> GameState:
    state = GameState(
        "kernel-resource-contract",
        {
            PLAYER: PlayerState(PLAYER),
            "P1": PlayerState("P1"),
        },
        TurnState(
            active_player_id=PLAYER,
            number=2,
            phase="PRECOMBAT_MAIN",
            step="PRECOMBAT_MAIN",
            priority_holder_id=PLAYER,
        ),
    )
    state.players[PLAYER].mana_pool.update({color: 0 for color in COLORS})
    state.players[PLAYER].mana_pool.update(floating or {})
    state.objects = {source.object_id: source for source in sources}
    state.zones = {"BATTLEFIELD:shared": [source.object_id for source in sources]}
    if commander_colors:
        spec = CardSpec(
            "contract-commander-spec",
            "Contract Commander",
            "contract-oracle",
            "0" * 64,
            "contract-source",
            "",
            0,
            (),
            ("Creature",),
            ("Wizard",),
            commander_colors,
            commander_colors,
            (),
            None,
            None,
            None,
            (),
            (),
        )
        instance = CardInstance(
            "contract-commander-instance",
            spec.card_spec_id,
            "contract-commander-slot",
            PLAYER,
            commander_designation=True,
        )
        state.card_specs[spec.card_spec_id] = spec
        state.card_instances[instance.card_instance_id] = instance
        state.commander_designations[instance.card_instance_id] = PLAYER
    return state


def _payment_step(mana_cost: str) -> PaymentStep:
    return PaymentStep(
        "contract-payment",
        mana_cost,
        PaymentWindow(0, "contract-resolution"),
        ("COUNTER_PAYMENT",),
    )


def _synthetic_instant(
    identity: str,
    effect: dict[str, object],
    *,
    target_kind: str = "NONE",
) -> CardSpec:
    ability = {
        "ability_id": f"{identity}:spell",
        "kind": "SPELL",
        "face": 0,
        "mode": "default",
        "target_schema": {
            "kind": target_kind,
            "min": 1 if target_kind != "NONE" else 0,
            "max": 1 if target_kind != "NONE" else 0,
            "unique": True,
        },
        "effect": effect,
    }
    face = {
        "name": identity,
        "mana_cost": "",
        "mana_value": 0,
        "supertypes": [],
        "card_types": ["Instant"],
        "subtypes": [],
        "keywords": [],
        "oracle_text": "Synthetic kernel contract.",
        "abilities": [ability],
        "spell_modes": [ability],
        "activated_abilities": [],
        "triggered_abilities": [],
    }
    return CardSpec(
        card_spec_id=f"contract:{identity}",
        name=identity,
        oracle_id=f"contract:{identity}",
        oracle_record_sha256="0" * 64,
        source_version="synthetic-kernel-contract",
        mana_cost="",
        mana_value=0,
        supertypes=(),
        card_types=("Instant",),
        subtypes=(),
        colors=(),
        color_identity=(),
        keywords=(),
        power=None,
        toughness=None,
        oracle_text="Synthetic kernel contract.",
        faces=(face,),
        abilities=(ability,),
    )


class _DeclineCounterProvider:
    def choose_counter_payment(
        self,
        request: CounterPaymentRequest,
    ) -> CounterPaymentSelection:
        assert request.legal_outcomes == ("DECLINE",)
        assert request.payment_result.feasible is False
        return CounterPaymentSelection(
            "DECLINE",
            "synthetic-kernel-provider",
            "1" * 64,
            {"reason_code": "SYNTHETIC_PROFILE_DECLINE"},
        )


def _nondefault_profile_replay() -> tuple[GameState, GameExecutor]:
    opponent_source = _mana_source(
        "profile-source",
        "Synthetic Profile Source",
        {"kind": "ADD_OPPONENT_PROFILE_COLOR"},
    )
    state = _minimal_state(opponent_source)
    executor = GameExecutor(state, "kernel-replay-profile-contract")
    target_card = add_card(
        executor,
        _synthetic_instant("Synthetic Target", {"kind": "NONE"}),
        Zone.HAND,
        owner=PLAYER,
    )
    counter_card = add_card(
        executor,
        _synthetic_instant(
            "Synthetic Counter",
            {"kind": "COUNTER_UNLESS_PAY", "amount": 1},
            target_kind="SPELL",
        ),
        Zone.HAND,
        owner=PLAYER,
    )
    state.replay_initial_state = state_to_data(state)
    executor.opponent_mana_profile = "no_known_colors"
    executor.bind_strategic_choice_provider(_DeclineCounterProvider())
    target = executor.cast(PLAYER, target_card.object_id)
    executor.cast(
        PLAYER,
        counter_card.object_id,
        targets=(TargetRef(target.object_id),),
    )
    for _ in state.players:
        holder = state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)
    return state, executor


def _allocation_colors(
    result: ResourcePaymentResult,
    label: str,
) -> dict[str, int]:
    colors: Counter[str] = Counter()
    for allocation in result.canonical_allocation:
        if allocation.step_label == label:
            colors[allocation.color] += int(allocation.amount)
    return dict(colors)


def _assert_execution_matches_allocation(
    state: GameState,
    result: ResourcePaymentResult,
    step: PaymentStep,
    payment: dict[str, int],
) -> None:
    assert payment == _allocation_colors(result, step.label)
    expected_pool = {color: 0 for color in COLORS}
    expected_pool.update(dict(result.remaining_mana))
    assert state.players[PLAYER].mana_pool == expected_pool

    allocated_sources = {
        allocation.source_semantic_id
        for allocation in result.canonical_allocation
        if not allocation.source_semantic_id.startswith("floating:")
    }
    activated_sources = {
        f"{state.objects[action.source_object_id].current_characteristics['name']}:mana-source"
        for action in state.actions
        if action.kind == "ACTIVATE" and action.source_object_id is not None
    }
    assert activated_sources == allocated_sources
    for action in state.actions:
        if action.kind != "ACTIVATE" or action.source_object_id is None:
            continue
        source = state.objects[action.source_object_id]
        source_id = f"{source.current_characteristics['name']}:mana-source"
        child_label = f"{step.label}:source:{source_id}"
        assert action.payments["mana"] == _allocation_colors(result, child_label)


def _round_trip(
    state: GameState,
    mana_cost: str,
    *,
    opponent_mana_profile: str = "blue_red_available",
) -> tuple[ResourcePaymentResult, dict[str, int]]:
    step = _payment_step(mana_cost)
    result = solve_state_payment(
        state,
        PLAYER,
        (step,),
        opponent_mana_profile=opponent_mana_profile,
    )
    assert result.feasible
    executor = GameExecutor(state, "kernel-resource-contract", probing=True)
    executor._resolution_depth = 1
    with patch.object(
        resource_execution,
        "solve_state_payment",
        wraps=solve_state_payment,
    ) as authority:
        payment = resource_execution.execute_resource_payment_during_resolution(
            executor,
            PLAYER,
            step,
            result,
            opponent_mana_profile=opponent_mana_profile,
        )
    authority.assert_called_once_with(
        state,
        PLAYER,
        (step,),
        opponent_mana_profile=opponent_mana_profile,
    )
    _assert_execution_matches_allocation(state, result, step, payment)
    return result, payment


def test_floating_mana_round_trips_without_inventing_a_source() -> None:
    state = _minimal_state(floating={"U": 1})

    result, payment = _round_trip(state, "{U}")

    assert payment == {"U": 1}
    assert result.canonical_allocation[0].source_semantic_id == "floating:U"
    assert state.actions == []


def test_ordinary_colored_source_round_trips_exactly() -> None:
    red_source = _mana_source(
        "red-source",
        "Red Source",
        {"kind": "ADD_MANA", "mana": {"R": 1}},
    )
    state = _minimal_state(red_source)

    result, payment = _round_trip(state, "{R}")

    assert payment == {"R": 1}
    assert result.canonical_allocation[0].requirement == "R:0"
    assert red_source.permanent_status is not None
    assert red_source.permanent_status["tap"] == "TAPPED"


def test_repeated_activation_units_with_one_semantic_source_identity_execute() -> None:
    first = _mana_source(
        "repeated-source-a",
        "Repeated Semantic Source",
        {"kind": "ADD_MANA", "mana": {"U": 1}},
    )
    second = _mana_source(
        "repeated-source-b",
        "Repeated Semantic Source",
        {"kind": "ADD_MANA", "mana": {"U": 1}},
    )
    state = _minimal_state(first, second)

    result, payment = _round_trip(state, "{U}{U}")

    assert payment == {"U": 2}
    assert {allocation.source_semantic_id for allocation in result.canonical_allocation} == {
        "Repeated Semantic Source:mana-source"
    }
    assert (
        len(
            [
                action
                for action in state.actions
                if action.kind == "ACTIVATE" and action.source_object_id is not None
            ]
        )
        == 2
    )
    assert first.permanent_status is not None
    assert second.permanent_status is not None
    assert first.permanent_status["tap"] == "TAPPED"
    assert second.permanent_status["tap"] == "TAPPED"


def test_chained_source_uses_solver_generic_activation_requirement() -> None:
    red_source = _mana_source(
        "red-source",
        "Red Source",
        {"kind": "ADD_MANA", "mana": {"R": 1}},
    )
    filter_source = _mana_source(
        "generic-filter",
        "Generic Filter",
        {"kind": "ADD_MANA", "mana": {"U": 1, "R": 1}},
        activation_cost="{1}",
    )
    state = _minimal_state(red_source, filter_source)

    result, payment = _round_trip(state, "{U}{R}")

    child = [
        allocation
        for allocation in result.canonical_allocation
        if allocation.step_label.endswith(":source:Generic Filter:mana-source")
    ]
    assert payment == {"U": 1, "R": 1}
    assert len(child) == 1
    assert (
        child[0].source_semantic_id,
        child[0].color,
        child[0].requirement,
    ) == ("Red Source:mana-source", "R", "GENERIC:0")


@pytest.mark.parametrize(
    ("activation_cost", "funding_color", "expected_requirement"),
    [
        pytest.param("{U}", "U", "U:0", id="colored"),
        pytest.param("{U/R}", "U", "HYBRID:U/R:0", id="hybrid-blue"),
        pytest.param("{U/R}", "R", "HYBRID:U/R:0", id="hybrid-red"),
    ],
)
def test_colored_and_hybrid_activations_use_exact_solver_selected_floating_color(
    activation_cost: str,
    funding_color: str,
    expected_requirement: str,
) -> None:
    filter_source = _mana_source(
        "colored-filter",
        "Colored Filter",
        {"kind": "ADD_MANA", "mana": {"U": 1, "R": 1}},
        activation_cost=activation_cost,
    )
    state = _minimal_state(filter_source, floating={funding_color: 1})

    result, payment = _round_trip(state, "{U}{R}")

    child = [
        allocation
        for allocation in result.canonical_allocation
        if allocation.step_label.endswith(":source:Colored Filter:mana-source")
    ]
    assert payment == {"U": 1, "R": 1}
    assert len(child) == 1
    assert (
        child[0].source_semantic_id,
        child[0].color,
        child[0].requirement,
    ) == (f"floating:{funding_color}", funding_color, expected_requirement)


def test_opponent_profile_is_identical_for_solver_and_execution() -> None:
    opponent_source = _mana_source(
        "opponent-source",
        "Opponent Source",
        {"kind": "ADD_OPPONENT_PROFILE_COLOR"},
    )
    state = _minimal_state(opponent_source)
    step = _payment_step("{U}")
    result = solve_state_payment(
        state,
        PLAYER,
        (step,),
        opponent_mana_profile="blue_red_available",
    )
    hidden = solve_state_payment(
        state,
        PLAYER,
        (step,),
        opponent_mana_profile="no_known_colors",
    )
    assert result.feasible
    assert not hidden.feasible

    executor = GameExecutor(state, "kernel-resource-profile-contract", probing=True)
    executor._resolution_depth = 1
    with pytest.raises(IllegalAction, match="resource feasibility changed"):
        resource_execution.execute_resource_payment_during_resolution(
            executor,
            PLAYER,
            step,
            result,
            opponent_mana_profile="no_known_colors",
        )
    assert state.actions == []

    with patch.object(
        resource_execution,
        "solve_state_payment",
        wraps=solve_state_payment,
    ) as authority:
        payment = resource_execution.execute_resource_payment_during_resolution(
            executor,
            PLAYER,
            step,
            result,
            opponent_mana_profile="blue_red_available",
        )
    authority.assert_called_once_with(
        state,
        PLAYER,
        (step,),
        opponent_mana_profile="blue_red_available",
    )
    _assert_execution_matches_allocation(state, result, step, payment)


def test_nondefault_opponent_profile_round_trips_through_production_replay() -> None:
    state, executor = _nondefault_profile_replay()

    body = transcript(state, seed=executor.seed)

    assert body["initial_state"]["execution_context"] == {
        "opponent_mana_profile": "no_known_colors"
    }
    decision = next(choice for choice in state.choices if choice.kind == "COUNTER_UNLESS_PAY")
    assert decision.selected["outcome"] == "DECLINE"
    assert decision.selected["pay_legally_available"] is False
    replayed = validate_replay(body)
    assert state_hash(replayed) == state_hash(state)
    replayed_decision = next(
        choice for choice in replayed.choices if choice.kind == "COUNTER_UNLESS_PAY"
    )
    assert replayed_decision.selected["pay_legally_available"] is False


def test_unknown_opponent_profile_fails_closed_live_and_during_replay() -> None:
    state = _minimal_state()
    executor = GameExecutor(state, "kernel-invalid-profile-contract")
    with pytest.raises(UnsupportedCapability, match="unsupported opponent mana profile"):
        executor.opponent_mana_profile = "unknown-profile"

    recorded_state, recorded_executor = _nondefault_profile_replay()
    body = transcript(recorded_state, seed=recorded_executor.seed)
    tampered = deepcopy(body)
    tampered["initial_state"]["execution_context"]["opponent_mana_profile"] = "unknown-profile"
    unsigned = dict(tampered)
    unsigned.pop("digest")
    tampered["digest"] = replay_module._digest(unsigned)

    with pytest.raises(ReplayError, match="unsupported opponent mana profile"):
        validate_replay(tampered)


def test_marked_child_mana_is_consumed_once_and_not_propagated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marked_source = _mana_source(
        "marked-source",
        "Marked Source",
        {"kind": "ADD_COMMANDER_COLOR_AND_MARK"},
        marked=True,
    )
    filter_source = _mana_source(
        "generic-filter",
        "Generic Filter",
        {"kind": "ADD_MANA", "mana": {"U": 1, "R": 1}},
        activation_cost="{1}",
    )
    state = _minimal_state(
        marked_source,
        filter_source,
        commander_colors=("U", "R"),
    )
    marker_payments: list[tuple[dict[str, int], set[str]]] = []
    original_consume = resource_execution._consume_marked_payment

    def record_marker_payment(
        executor: object,
        player_id: str,
        payment: dict[str, int],
        selected_marker_ids: set[str],
    ) -> None:
        marker_payments.append((dict(payment), set(selected_marker_ids)))
        original_consume(executor, player_id, payment, selected_marker_ids)

    monkeypatch.setattr(resource_execution, "_consume_marked_payment", record_marker_payment)
    result, payment = _round_trip(state, "{U}{R}")

    child = [
        allocation
        for allocation in result.canonical_allocation
        if allocation.step_label.endswith(":source:Generic Filter:mana-source")
    ]
    assert payment == {"U": 1, "R": 1}
    assert len(child) == 1
    assert child[0].source_semantic_id == "Marked Source:mana-source"
    assert child[0].requirement == "GENERIC:0"
    selected = [entry for entry in marker_payments if entry[1]]
    assert len(selected) == 1
    assert selected[0][0] == {child[0].color: 1}
    assert marker_payments[-1][1] == set()
    assert not any(
        record.get("kind") == MARKED_COMMANDER_MANA_KIND for record in state.continuous_effects
    )
