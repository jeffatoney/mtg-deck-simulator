"""Fast card-independent contracts for explicitly selected mana payments."""

from __future__ import annotations

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.mana import COLORS, parse_mana_cost, pay_exact_mana
from mtg_kernel.models import TargetRef, Zone


@pytest.mark.parametrize(
    ("cost_text", "proposed", "legal"),
    [
        pytest.param("{U}", {"U": 1}, True, id="colored-exact"),
        pytest.param("{U}", {"R": 1}, False, id="colored-off-color"),
        pytest.param("{1}", {"C": 1}, True, id="generic-colorless"),
        pytest.param("{2}", {"U": 1, "R": 1}, True, id="generic-colored-units"),
        pytest.param("{U/R}", {"U": 1}, True, id="hybrid-blue"),
        pytest.param("{U/R}", {"R": 1}, True, id="hybrid-red"),
        pytest.param("{U/R}", {"C": 1}, False, id="hybrid-colorless"),
        pytest.param("{U/R}", {"W": 1}, False, id="hybrid-white"),
        pytest.param("{U/R}", {"B": 1}, False, id="hybrid-black"),
        pytest.param("{U/R}", {"G": 1}, False, id="hybrid-green"),
        pytest.param("{1}{U}", {"U": 1, "R": 1}, True, id="mixed-two-colors"),
        pytest.param("{1}{U}", {"U": 2}, True, id="mixed-same-color"),
        pytest.param("{1}{U}", {"R": 2}, False, id="mixed-missing-colored-pip"),
        pytest.param("{2}", {"U": 1}, False, id="insufficient-generic"),
        pytest.param("{U}", {}, False, id="insufficient-colored"),
        pytest.param("{1}", {"U": 2}, False, id="excess-generic"),
        pytest.param("{U/R}", {"U": 1, "R": 1}, False, id="excess-hybrid"),
    ],
)
def test_exact_payment_is_accepted_iff_proposed_units_pay_actual_cost(
    cost_text: str,
    proposed: dict[str, int],
    legal: bool,
) -> None:
    pool = {color: 0 for color in COLORS}
    pool.update(proposed)
    before = dict(pool)
    cost = parse_mana_cost(cost_text)

    if not legal:
        with pytest.raises(IllegalAction):
            pay_exact_mana(pool, cost, proposed)
        assert pool == before
        return

    assert pay_exact_mana(pool, cost, proposed) == proposed
    assert pool == {color: 0 for color in COLORS}


def test_exact_payment_consumes_only_requested_units_from_a_surplus_pool() -> None:
    pool = {color: 0 for color in COLORS}
    pool.update({"U": 2, "R": 1})

    assert pay_exact_mana(pool, parse_mana_cost("{U}"), {"U": 1}) == {"U": 1}
    assert pool == {**{color: 0 for color in COLORS}, "U": 1, "R": 1}


def test_exact_payment_consumes_the_selected_unit_when_multiple_are_legal() -> None:
    pool = {color: 0 for color in COLORS}
    pool.update({"U": 1, "R": 1})

    assert pay_exact_mana(pool, parse_mana_cost("{1}"), {"R": 1}) == {"R": 1}
    assert pool["U"] == 1
    assert pool["R"] == 0
    assert pool["C"] == 0


@pytest.mark.parametrize(
    ("proposed", "message"),
    [
        pytest.param({"S": 1}, "unsupported colors", id="unsupported-key"),
        pytest.param({"U": -1}, "negative amount", id="negative-amount"),
    ],
)
def test_malformed_exact_payment_fails_without_mutating_pool(
    proposed: dict[str, int],
    message: str,
) -> None:
    pool = {color: 1 for color in COLORS}
    before = dict(pool)

    with pytest.raises(IllegalAction, match=message):
        pay_exact_mana(pool, parse_mana_cost("{U}"), proposed)

    assert pool == before


def test_activate_exact_generic_payment_consumes_selected_units() -> None:
    state, executor = new_game(("P0", "P1"), "exact-generic-activate")
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    for symbol in COLORS:
        state.players["P0"].mana_pool[symbol] = 0
    state.players["P0"].mana_pool["U"] = 2
    state.players["P0"].mana_pool["R"] = 1
    field = add_card(executor, specs["Demolition Field"], Zone.BATTLEFIELD, owner="P0")
    target = add_card(executor, specs["Thriving Isle"], Zone.BATTLEFIELD, owner="P1")

    executor.activate(
        "P0",
        field.object_id,
        "demolition-field:destroy",
        targets=(TargetRef(target.object_id),),
        choices={"library_search": {"P0": "FAIL_TO_FIND"}},
        mana_payment={"U": 1, "R": 1},
    )

    assert state.players["P0"].mana_pool["U"] == 1
    assert state.players["P0"].mana_pool["R"] == 0
