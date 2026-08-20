from __future__ import annotations

from dataclasses import replace

from mtg_kernel.resource_payment import (
    FloatingMana,
    ManaProduction,
    PaymentStep,
    PaymentWindow,
    ResourceSource,
    solve_resource_payment,
)

NOW = PaymentWindow(0, "precombat-main")
LATER = PaymentWindow(1, "post-boundary", clear_pool_before=True)
UNTAP_LATER = PaymentWindow(1, "next-turn-main", clear_pool_before=True, untap_before=True)


def production(**mana: int) -> ManaProduction:
    return ManaProduction(
        tuple(sorted((color, amount) for color, amount in mana.items() if amount))
    )


def fixed(
    semantic_id: str,
    color: str,
    *,
    count: int = 1,
    tapped: bool = False,
    enters_tapped: bool = False,
    available_from_window: int = 0,
    execution_refs: tuple[str, ...] = (),
) -> ResourceSource:
    return ResourceSource(
        semantic_id=semantic_id,
        productions=(production(**{color: 1}),),
        count=count,
        tap_to_activate=True,
        persistent=True,
        tapped=tapped,
        enters_tapped=enters_tapped,
        available_from_window=available_from_window,
        execution_refs=execution_refs,
    )


def flexible(
    semantic_id: str,
    colors: tuple[str, ...] = ("W", "U", "B", "R", "G"),
    *,
    count: int = 1,
    sacrifice: bool = False,
    tapped: bool = False,
    available_from_window: int = 0,
    execution_refs: tuple[str, ...] = (),
) -> ResourceSource:
    return ResourceSource(
        semantic_id=semantic_id,
        productions=tuple(production(**{color: 1}) for color in colors),
        count=count,
        tap_to_activate=True,
        sacrifice_to_activate=sacrifice,
        persistent=True,
        tapped=tapped,
        available_from_window=available_from_window,
        execution_refs=execution_refs,
    )


def pay(
    cost: str,
    *,
    window: PaymentWindow = NOW,
    label: str = "payment",
    tags: tuple[str, ...] = (),
) -> PaymentStep:
    return PaymentStep(label=label, mana_cost=cost, window=window, context_tags=tags)


def test_one_treasure_cannot_be_double_counted() -> None:
    result = solve_resource_payment(
        (flexible("treasure", sacrifice=True),),
        (pay("{R}", label="red"), pay("{U}", label="blue")),
    )
    assert result.feasible is False
    assert result.first_failed_step == "blue"
    assert result.colored_pip_deficits == (("U", 1),)
    assert "SOURCE_REUSED_ACROSS_COSTS" in result.reason_codes


def test_one_flexible_source_pays_one_color_or_one_generic_not_both() -> None:
    result = solve_resource_payment(
        (flexible("treasure", sacrifice=True),),
        (pay("{R}", label="colored"), pay("{1}", label="generic")),
    )
    assert result.feasible is False
    assert result.first_failed_step == "generic"
    assert result.generic_deficit == 1


def test_red_source_removes_red_deficit() -> None:
    without_red = solve_resource_payment((), (pay("{R}"),))
    with_red = solve_resource_payment((fixed("mountain", "R"),), (pay("{R}"),))
    assert without_red.feasible is False
    assert without_red.colored_pip_deficits == (("R", 1),)
    assert "RED_PIP_DEFICIT" in without_red.reason_codes
    assert with_red.feasible is True
    assert with_red.colored_pip_deficits == ()


def test_irrelevant_fixed_color_does_not_remove_red_deficit() -> None:
    result = solve_resource_payment((fixed("island", "U"),), (pay("{R}"),))
    assert result.feasible is False
    assert result.colored_pip_deficits == (("R", 1),)
    assert "RED_PIP_DEFICIT" in result.reason_codes


def test_generic_cost_accepts_any_legally_usable_mana() -> None:
    for source in (
        fixed("island", "U"),
        fixed("wastes", "C"),
        flexible("treasure", sacrifice=True),
    ):
        assert solve_resource_payment((source,), (pay("{1}"),)).feasible is True


def test_floating_mana_expires_at_boundary() -> None:
    floating = (FloatingMana("R", 1, semantic_id="floating:R"),)
    result = solve_resource_payment((), (pay("{R}", window=LATER),), floating_mana=floating)
    assert result.feasible is False
    assert result.first_failed_step == "payment"
    assert "RESOURCE_EXPIRES_BEFORE_STEP" in result.reason_codes


def test_treasure_persists_across_turns_until_used_or_removed() -> None:
    result = solve_resource_payment(
        (flexible("treasure", sacrifice=True),),
        (pay("{R}", window=UNTAP_LATER),),
    )
    assert result.feasible is True
    assert result.canonical_allocation[0].source_semantic_id == "treasure"


def test_tapped_treasure_untaps_at_explicit_untap_transition() -> None:
    tapped = flexible("treasure", colors=("R",), sacrifice=True, tapped=True)
    assert solve_resource_payment((tapped,), (pay("{R}", window=NOW),)).feasible is False
    later = solve_resource_payment((tapped,), (pay("{R}", window=UNTAP_LATER),))
    assert later.feasible is True
    assert later.canonical_allocation[0].source_semantic_id == "treasure"


def test_sacrificed_treasure_does_not_return_after_untap_transition() -> None:
    result = solve_resource_payment(
        (flexible("treasure", colors=("R",), sacrifice=True),),
        (
            pay("{R}", label="first"),
            pay("{R}", window=UNTAP_LATER, label="second"),
        ),
    )
    assert result.feasible is False
    assert result.first_failed_step == "second"
    capacity = next(
        value for value in result.remaining_source_capacity if value.source_semantic_id == "treasure"
    )
    assert capacity.remaining == 0


def test_source_arriving_after_window_cannot_pay_earlier_cost() -> None:
    source = fixed("late-mountain", "R", available_from_window=1)
    result = solve_resource_payment((source,), (pay("{R}", window=NOW),))
    assert result.feasible is False
    assert "RESOURCE_NOT_AVAILABLE_IN_WINDOW" in result.reason_codes


def test_ordered_cast_and_activation_cannot_reuse_tapped_or_sacrificed_source() -> None:
    tapped_source = fixed("mountain", "R")
    sacrificed_source = flexible("treasure", colors=("R",), sacrifice=True)
    for source in (tapped_source, sacrificed_source):
        result = solve_resource_payment(
            (source,),
            (pay("{R}", label="cast"), pay("{R}", label="activation")),
        )
        assert result.feasible is False
        assert result.first_failed_step == "activation"
        assert "SOURCE_REUSED_ACROSS_COSTS" in result.reason_codes


def test_restricted_mana_is_rejected_for_inapplicable_cost() -> None:
    restricted = ResourceSource(
        semantic_id="creature-only",
        productions=(ManaProduction((("R", 1),), spend_tags=("CREATURE_SPELL",)),),
        count=1,
        tap_to_activate=True,
        persistent=True,
    )
    result = solve_resource_payment(
        (restricted,),
        (pay("{R}", tags=("ACTIVATED_ABILITY",)),),
    )
    assert result.feasible is False
    assert "RESTRICTED_MANA_NOT_APPLICABLE" in result.reason_codes


def test_legal_execution_and_measurement_can_share_exact_same_result() -> None:
    sources = (fixed("mountain", "R"), flexible("treasure", sacrifice=True))
    steps = (pay("{1}{R}", label="activate"),)
    measurement = solve_resource_payment(sources, steps)
    legality_preview = solve_resource_payment(sources, steps)
    assert measurement == legality_preview
    assert measurement.feasible is True


def test_hidden_object_identity_cannot_change_public_payment_result() -> None:
    a = fixed("mountain", "R", execution_refs=("opaque-object-1",))
    b = fixed("mountain", "R", execution_refs=("different-hidden-object",))
    assert solve_resource_payment((a,), (pay("{R}"),)) == solve_resource_payment(
        (b,), (pay("{R}"),)
    )


def test_hidden_library_order_cannot_change_public_payment_result() -> None:
    sources = (fixed("mountain", "R"),)
    steps = (pay("{R}"),)
    first = solve_resource_payment(sources, steps, assumptions=("library-order:A,B,C",))
    second = solve_resource_payment(sources, steps, assumptions=("library-order:C,B,A",))
    assert replace(first, assumptions=()) == replace(second, assumptions=())


def test_equivalent_source_enumeration_order_cannot_change_public_result() -> None:
    sources_a = (fixed("mountain", "R"), fixed("island", "U"))
    sources_b = tuple(reversed(sources_a))
    steps = (pay("{R}", label="red"), pay("{U}", label="blue"))
    assert solve_resource_payment(sources_a, steps) == solve_resource_payment(sources_b, steps)


def test_fixed_red_plus_flexible_any_satisfies_ordered_red_then_blue() -> None:
    result = solve_resource_payment(
        (fixed("mountain", "R"), flexible("treasure", sacrifice=True)),
        (pay("{R}", label="red"), pay("{U}", label="blue")),
    )
    assert result.feasible is True
    assert tuple(
        (item.step_label, item.source_semantic_id, item.color)
        for item in result.canonical_allocation
    ) == (
        ("red", "mountain", "R"),
        ("blue", "treasure", "U"),
    )


def test_solver_does_not_allocate_one_flexible_source_to_two_colored_requirements() -> None:
    result = solve_resource_payment(
        (flexible("treasure", sacrifice=True),),
        (pay("{R}{U}"),),
    )
    assert result.feasible is False
    assert "INSUFFICIENT_TOTAL_CAPACITY" in result.reason_codes


def test_colorless_only_source_pays_generic_but_not_colored() -> None:
    colorless = fixed("wastes", "C")
    assert solve_resource_payment((colorless,), (pay("{1}"),)).feasible is True
    red = solve_resource_payment((colorless,), (pay("{R}"),))
    assert red.feasible is False
    assert "RED_PIP_DEFICIT" in red.reason_codes


def test_explicit_colorless_requirement_requires_actual_colorless_mana() -> None:
    colored = fixed("mountain", "R")
    result = solve_resource_payment((colored,), (pay("{C}"),))
    assert result.feasible is False
    assert result.colorless_deficit == 1
    assert "COLORLESS_REQUIREMENT_DEFICIT" in result.reason_codes
    assert solve_resource_payment((fixed("wastes", "C"),), (pay("{C}"),)).feasible is True


def test_tapped_resource_unavailable_until_explicit_untap_transition() -> None:
    tapped = fixed("mountain", "R", tapped=True)
    assert solve_resource_payment((tapped,), (pay("{R}", window=NOW),)).feasible is False
    assert solve_resource_payment((tapped,), (pay("{R}", window=UNTAP_LATER),)).feasible is True


def test_enters_tapped_source_not_immediately_available_without_untap() -> None:
    entered_tapped = fixed("swiftwater-cliffs", "R", enters_tapped=True)
    now = solve_resource_payment((entered_tapped,), (pay("{R}", window=NOW),))
    later = solve_resource_payment((entered_tapped,), (pay("{R}", window=UNTAP_LATER),))
    assert now.feasible is False
    assert later.feasible is True
