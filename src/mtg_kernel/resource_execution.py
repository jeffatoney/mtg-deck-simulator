"""Rules-private execution binding for an already-proven resource allocation.

This module is deliberately *not* a feasibility model.  Feasibility, source
capacity, payment windows, deficits, reason codes, and the canonical semantic
allocation belong exclusively to :mod:`mtg_kernel.resource_payment` and
:mod:`mtg_kernel.resource_sources`.

Only after policy has selected an outcome that requires payment may this adapter
bind the canonical semantic source allocation to current execution objects.  It
never exposes object IDs or ability IDs to policy and never probes or deep-copies
the executor to decide whether payment is possible.  A stale or unbindable
allocation fails closed.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from typing import Any, Mapping

from mtg_kernel.errors import IllegalAction, UnsupportedCapability
from mtg_kernel.mana import parse_mana_cost, pay_mana
from mtg_kernel.models import GameObject
from mtg_kernel.phase_b_marked_mana import (
    MARKED_COMMANDER_MANA_KIND,
    _consume_markers,
    is_marked_floating_semantic_id,
    marked_floating_mana_inventory,
)
from mtg_kernel.resource_payment import (
    ManaProduction,
    PaymentAllocation,
    PaymentStep,
    ResourcePaymentResult,
    _reqs,
)
from mtg_kernel.resource_sources import (
    _effect_productions,
    resource_inventory_from_state,
    solve_state_payment,
)


@dataclass(frozen=True)
class _ExecutionVariant:
    source_object_id: str
    source_semantic_id: str
    ability_id: str
    production: ManaProduction
    choices: Mapping[str, Any]


def _cost_units(cost: str) -> int:
    return sum(int(value) for value in parse_mana_cost(cost).values())


def _single_produced_color(production: ManaProduction) -> str:
    if len(production.mana) != 1 or production.mana[0][1] != 1:
        raise UnsupportedCapability("chosen-mana execution requires one produced mana unit")
    return production.mana[0][0]


def _execution_choices(
    effect: Mapping[str, Any],
    productions: tuple[ManaProduction, ...],
    *,
    opponent_mana_profile: str,
) -> tuple[Mapping[str, Any], ...]:
    """Bind declarative production variants to the executor's explicit choices.

    The production set itself comes from ``resource_sources._effect_productions``
    so this function does not independently decide which mana an ability can make.
    """

    kind = str(effect.get("kind", ""))
    if kind == "ADD_MANA":
        if len(productions) != 1:
            raise UnsupportedCapability("fixed mana effect has an unexpected production count")
        return ({},)
    if kind == "FILTER_MANA_OPTIONS":
        options = effect.get("options", ())
        if not isinstance(options, (list, tuple)) or len(options) != len(productions):
            raise UnsupportedCapability("filter-mana execution options differ from resource model")
        choices: list[Mapping[str, Any]] = []
        for option in options:
            if not isinstance(option, Mapping):
                raise UnsupportedCapability("filter-mana execution option is malformed")
            choices.append({"mana_option": dict(option)})
        return tuple(choices)
    if kind in {
        "ADD_CHOSEN_MANA",
        "ADD_COMMANDER_COLOR",
        "ADD_COMMANDER_COLOR_AND_MARK",
        "ADD_OPPONENT_PROFILE_COLOR",
        "ADD_CHOSEN_MANA_AND_DAMAGE_SELF",
        "ADD_BLUE_OR_FIXED_CHOSEN",
    }:
        choices = []
        for production in productions:
            value: dict[str, Any] = {"mana_color": _single_produced_color(production)}
            if kind == "ADD_OPPONENT_PROFILE_COLOR":
                value["opponent_mana_profile"] = opponent_mana_profile
            choices.append(value)
        return tuple(choices)
    raise UnsupportedCapability(f"unsupported resource execution effect: {kind}")


def _variants_for_object(
    executor: Any,
    player_id: str,
    obj: GameObject,
    source_semantic_id: str,
    *,
    opponent_mana_profile: str,
) -> tuple[_ExecutionVariant, ...]:
    variants: list[_ExecutionVariant] = []
    for raw_ability in obj.current_characteristics.get("abilities", ()):
        if not isinstance(raw_ability, Mapping):
            continue
        ability = dict(raw_ability)
        if ability.get("kind") != "ACTIVATED" or ability.get("mana_ability") is not True:
            continue
        productions = _effect_productions(
            executor.state,
            player_id,
            obj,
            ability,
            opponent_mana_profile=opponent_mana_profile,
        )
        choices = _execution_choices(
            dict(ability.get("effect", {})),
            productions,
            opponent_mana_profile=opponent_mana_profile,
        )
        if len(choices) != len(productions):
            raise UnsupportedCapability(
                "resource execution choices differ from semantic productions"
            )
        for production, choice in zip(productions, choices, strict=True):
            variants.append(
                _ExecutionVariant(
                    source_object_id=obj.object_id,
                    source_semantic_id=source_semantic_id,
                    ability_id=str(ability.get("ability_id", "")),
                    production=production,
                    choices=dict(choice),
                )
            )
    return tuple(
        sorted(
            variants,
            key=lambda item: (
                item.production,
                item.ability_id,
                json.dumps(dict(item.choices), sort_keys=True, separators=(",", ":")),
            ),
        )
    )


def _available_variants(
    executor: Any,
    player_id: str,
    source_semantic_id: str,
    *,
    opponent_mana_profile: str,
) -> tuple[_ExecutionVariant, ...]:
    inventory = resource_inventory_from_state(
        executor.state,
        player_id,
        opponent_mana_profile=opponent_mana_profile,
    )
    refs: set[str] = set()
    for source in inventory.sources:
        if source.semantic_id != source_semantic_id:
            continue
        if source.tapped or source.enters_tapped:
            continue
        if source.available_from_window > 0:
            continue
        if source.available_through_window is not None and source.available_through_window < 0:
            continue
        refs.update(str(value) for value in source.execution_refs)

    variants: list[_ExecutionVariant] = []
    for object_id in sorted(refs):
        obj = executor.state.objects.get(object_id)
        if obj is None or obj.retired or obj.ceased_to_exist:
            continue
        variants.extend(
            _variants_for_object(
                executor,
                player_id,
                obj,
                source_semantic_id,
                opponent_mana_profile=opponent_mana_profile,
            )
        )
    return tuple(variants)


def _marker_ids(executor: Any, player_id: str) -> set[str]:
    return {
        str(record.get("produced_event_id"))
        for record in executor.state.continuous_effects
        if record.get("kind") == MARKED_COMMANDER_MANA_KIND
        and record.get("player_id") == player_id
        and record.get("produced_event_id")
    }


def _activate_mana_ability_during_resolution(
    executor: Any,
    player_id: str,
    variant: _ExecutionVariant,
    *,
    mana_payment: Mapping[str, int] | None = None,
) -> tuple[dict[str, int], set[str]]:
    """Execute one selected mana ability without creating a priority window.

    ``GameExecutor.activate`` is retained as the sole cost/effect executor.  The
    temporary holder assignment only satisfies its normal priority precondition;
    no priority event or opportunity is created while a resolving effect asks for
    a mana payment (rules 117.2e, 118.2, and 608.2g).
    """

    if int(getattr(executor, "_resolution_depth", 0)) <= 0:
        raise IllegalAction("resolution-time resource binding requires a resolving object")
    before_markers = _marker_ids(executor, player_id)
    before_actions = len(executor.state.actions)
    previous_holder = executor.state.turn.priority_holder_id
    try:
        executor.state.turn.priority_holder_id = player_id
        executor.activate(
            player_id,
            variant.source_object_id,
            variant.ability_id,
            choices=dict(variant.choices),
            _record=False,
            mana_payment=mana_payment,
        )
    finally:
        executor.state.turn.priority_holder_id = previous_holder
    if len(executor.state.actions) != before_actions + 1:
        raise IllegalAction("mana-ability execution did not append exactly one rules action")
    action = executor.state.actions[-1]
    payment = {
        str(color): int(amount)
        for color, amount in dict(action.payments.get("mana", {})).items()
        if int(amount) > 0
    }
    return payment, _marker_ids(executor, player_id) - before_markers


def _add_payment(total: Counter[str], payment: Mapping[str, int]) -> None:
    for color, amount in payment.items():
        if int(amount) > 0:
            total[str(color)] += int(amount)


def _consume_marked_payment(
    executor: Any,
    player_id: str,
    payment: Mapping[str, int],
    selected_marker_ids: set[str],
) -> None:
    if not payment or not _marker_ids(executor, player_id):
        return
    # An explicit empty set means the canonical allocation spent zero marked
    # units. Omitting the key is reserved for callers that have no provenance.
    _consume_markers(
        executor,
        player_id,
        payment,
        {"marked_mana_event_ids": sorted(selected_marker_ids)},
    )


@dataclass
class _BindingContext:
    executor: Any
    player_id: str
    opponent_mana_profile: str
    by_label: dict[str, tuple[PaymentAllocation, ...]]
    available_mana: Counter[tuple[str, str]]
    remaining_marked_event_ids: dict[str, list[str]]
    executed: dict[str, set[str]]
    visiting: set[str]


def _coverage(remaining: Counter[str], production: ManaProduction) -> int:
    return sum(min(remaining[color], amount) for color, amount in production.mana)


def _excess(remaining: Counter[str], production: ManaProduction) -> int:
    return sum(amount for _, amount in production.mana) - _coverage(remaining, production)


def _allocation_units(
    allocations: tuple[PaymentAllocation, ...],
) -> Counter[tuple[str, str, str]]:
    units: Counter[tuple[str, str, str]] = Counter()
    for item in allocations:
        units[(item.requirement, item.source_semantic_id, item.color)] += int(item.amount)
    return units


def _bind_marked_floating_event_id(context: _BindingContext, color: str) -> str:
    remaining = context.remaining_marked_event_ids.get(color, [])
    if not remaining:
        raise IllegalAction(
            "canonical allocation selected marked floating mana that is not in the ledger"
        )
    return remaining.pop(0)


def _take_exact_allocation_payment(
    context: _BindingContext,
    unpaid: Counter[tuple[str, str, str]],
    mana_cost: str,
) -> tuple[dict[str, int], tuple[str, ...]]:
    """Bind each actual cost requirement to one solver-selected mana unit."""

    pool = context.executor.state.players[context.player_id].mana_pool
    payment: Counter[str] = Counter()
    spent_marked: list[str] = []
    for requirement in _reqs(mana_cost):
        selected: tuple[str, str, str] | None = None
        for key, amount in unpaid.items():
            allocated_requirement, source_semantic_id, color = key
            if (
                amount > 0
                and allocated_requirement == requirement.name
                and color in requirement.options
                and context.available_mana[(source_semantic_id, color)] > 0
                and int(pool.get(color, 0)) > payment[color]
            ):
                selected = key
                break
        if selected is None:
            raise IllegalAction(
                "canonical resource allocation cannot bind an actual mana-cost requirement"
            )
        _, source_semantic_id, color = selected
        unpaid[selected] -= 1
        context.available_mana[(source_semantic_id, color)] -= 1
        payment[color] += 1
        if is_marked_floating_semantic_id(source_semantic_id):
            spent_marked.append(_bind_marked_floating_event_id(context, color))
    return {color: amount for color, amount in payment.items() if amount}, tuple(spent_marked)


def _record_production(context: _BindingContext, variant: _ExecutionVariant) -> None:
    for color, amount in variant.production.mana:
        context.available_mana[(variant.source_semantic_id, color)] += int(amount)


def _activate_semantic_source(
    context: _BindingContext,
    label: str,
    source_semantic_id: str,
    allocations: tuple[PaymentAllocation, ...],
) -> set[str]:
    remaining: Counter[str] = Counter()
    for allocation in allocations:
        if allocation.step_label == label and allocation.source_semantic_id == source_semantic_id:
            remaining[allocation.color] += int(allocation.amount)
    if not remaining:
        return set()

    child_label = f"{label}:source:{source_semantic_id}"
    child_allocations = context.by_label.get(child_label, ())
    child_markers: set[str] = set()
    other_ids = sorted(
        {
            item.source_semantic_id
            for item in child_allocations
            if not item.source_semantic_id.startswith("floating:")
            and item.source_semantic_id != source_semantic_id
        }
    )
    for other_id in other_ids:
        child_markers.update(
            _activate_semantic_source(context, child_label, other_id, child_allocations)
        )
    unpaid_child = _allocation_units(child_allocations)
    expected_activation_payment = sum(unpaid_child.values())
    remaining_activation_payment = expected_activation_payment
    aggregate_activation_payment: Counter[str] = Counter()
    produced_markers: set[str] = set()
    spent_marked: set[str] = set(child_markers)

    while sum(remaining.values()) > 0:
        candidates = []
        for variant in _available_variants(
            context.executor,
            context.player_id,
            source_semantic_id,
            opponent_mana_profile=context.opponent_mana_profile,
        ):
            coverage = _coverage(remaining, variant.production)
            if coverage <= 0:
                continue
            cost_units = _cost_units(variant.production.activation_cost)
            if cost_units > remaining_activation_payment:
                continue
            candidates.append(
                (
                    -coverage,
                    abs(remaining_activation_payment - cost_units),
                    _excess(remaining, variant.production),
                    cost_units,
                    variant.production,
                    variant.ability_id,
                    variant.source_object_id,
                    json.dumps(dict(variant.choices), sort_keys=True, separators=(",", ":")),
                    variant,
                )
            )
        if not candidates:
            raise IllegalAction(
                "canonical resource allocation cannot bind to a current mana-source execution"
            )
        *_, variant = min(candidates)
        cost_units = _cost_units(variant.production.activation_cost)
        exact_payment, floating_marked = _take_exact_allocation_payment(
            context,
            unpaid_child,
            variant.production.activation_cost,
        )
        spent_marked.update(floating_marked)
        payment, new_markers = _activate_mana_ability_during_resolution(
            context.executor,
            context.player_id,
            variant,
            mana_payment=exact_payment,
        )
        _record_production(context, variant)
        _add_payment(aggregate_activation_payment, payment)
        produced_markers.update(new_markers)
        remaining_activation_payment -= cost_units
        for color, amount in variant.production.mana:
            remaining[color] = max(0, remaining[color] - int(amount))

    if remaining_activation_payment != 0 or sum(unpaid_child.values()) != 0:
        raise IllegalAction("canonical resource allocation activation-cost binding is incomplete")
    if sum(aggregate_activation_payment.values()) != expected_activation_payment:
        raise IllegalAction(
            "rules execution payment differs from canonical activation-cost allocation"
        )
    _consume_marked_payment(
        context.executor,
        context.player_id,
        aggregate_activation_payment,
        spent_marked,
    )
    return produced_markers


def _execute_allocation_label(context: _BindingContext, label: str) -> set[str]:
    if label in context.executed:
        return set(context.executed[label])
    if label in context.visiting:
        raise IllegalAction("canonical resource allocation contains an execution cycle")
    context.visiting.add(label)
    allocations = context.by_label.get(label, ())
    produced_markers: set[str] = set()
    source_ids = sorted(
        {
            item.source_semantic_id
            for item in allocations
            if not item.source_semantic_id.startswith("floating:")
        }
    )
    for source_semantic_id in source_ids:
        produced_markers.update(
            _activate_semantic_source(context, label, source_semantic_id, allocations)
        )
    context.visiting.remove(label)
    context.executed[label] = set(produced_markers)
    return produced_markers


def execute_resource_payment_during_resolution(
    executor: Any,
    player_id: str,
    step: PaymentStep,
    expected_result: ResourcePaymentResult,
    *,
    opponent_mana_profile: str = "blue_red_available",
) -> dict[str, int]:
    """Execute one already-selected payment using its canonical semantic allocation.

    The authoritative solver is rerun once immediately before binding to reject a
    stale policy request.  This is rules revalidation through the same shared
    solver, not executor probing or an independent feasibility calculation.
    """

    if int(getattr(executor, "_resolution_depth", 0)) <= 0:
        raise IllegalAction("resource payment may be bound here only during resolution")
    if not expected_result.feasible:
        raise IllegalAction("an infeasible resource result cannot be executed")

    current_result = solve_state_payment(
        executor.state,
        player_id,
        (step,),
        opponent_mana_profile=opponent_mana_profile,
    )
    if current_result != expected_result:
        raise IllegalAction("resource feasibility changed after semantic outcome selection")

    by_label: dict[str, list[PaymentAllocation]] = {}
    for allocation in current_result.canonical_allocation:
        by_label.setdefault(allocation.step_label, []).append(allocation)
    inventory = resource_inventory_from_state(
        executor.state,
        player_id,
        opponent_mana_profile=opponent_mana_profile,
    )
    available_mana: Counter[tuple[str, str]] = Counter()
    for item in inventory.floating_mana:
        available_mana[(item.semantic_id, item.color)] += int(item.amount)
    remaining_marked_event_ids = {
        record.color: list(record.produced_event_ids)
        for record in marked_floating_mana_inventory(executor.state, player_id)
    }
    context = _BindingContext(
        executor=executor,
        player_id=player_id,
        opponent_mana_profile=opponent_mana_profile,
        by_label={key: tuple(value) for key, value in by_label.items()},
        available_mana=available_mana,
        remaining_marked_event_ids=remaining_marked_event_ids,
        executed={},
        visiting=set(),
    )
    selected_markers = _execute_allocation_label(context, step.label)

    # Validate that the now-produced pool can pay the original rules cost, then
    # bind and spend each exact requirement/source/color allocation selected by
    # the shared solver.
    verification_pool = dict(executor.state.players[player_id].mana_pool)
    pay_mana(verification_pool, parse_mana_cost(step.mana_cost))
    unpaid_step = _allocation_units(context.by_label.get(step.label, ()))
    exact_color_cost, floating_marked = _take_exact_allocation_payment(
        context, unpaid_step, step.mana_cost
    )
    if sum(unpaid_step.values()) != 0:
        raise IllegalAction("canonical resource allocation payment binding is incomplete")
    payment = pay_mana(executor.state.players[player_id].mana_pool, exact_color_cost)
    _consume_marked_payment(
        executor,
        player_id,
        payment,
        set(selected_markers) | set(floating_marked),
    )
    return payment


__all__ = ["execute_resource_payment_during_resolution"]
