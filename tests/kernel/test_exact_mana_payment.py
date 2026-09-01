"""Fast card-independent contracts for explicitly selected mana payments."""

from __future__ import annotations

import pytest

from mtg_kernel.errors import IllegalAction
from mtg_kernel.mana import COLORS, parse_mana_cost, pay_exact_mana


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
