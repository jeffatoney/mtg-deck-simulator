"""Exact-deck Cascade Bluffs witnesses for costed multi-mode resource search."""

from __future__ import annotations

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import Zone
from mtg_kernel.resource_payment import PaymentStep, PaymentWindow
from mtg_kernel.resource_sources import solve_state_payment

PLAYERS = ("P0", "P1")
MANA_SYMBOLS = ("W", "U", "B", "R", "G", "C")


def _bluffs_state(seed: str, floating: str) -> object:
    state, executor = new_game(PLAYERS, seed)
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    add_card(executor, specs["Cascade Bluffs"], Zone.BATTLEFIELD, owner="P0")
    for symbol in MANA_SYMBOLS:
        state.players["P0"].mana_pool[symbol] = 0
    state.players["P0"].mana_pool[floating] = 1
    return state


@pytest.mark.parametrize(
    ("floating", "cost"),
    (
        ("U", "{U}{U}"),
        ("R", "{U}{U}"),
        ("U", "{U}{R}"),
        ("U", "{R}{R}"),
        ("U", "{2}"),
    ),
)
def test_cascade_bluffs_plus_one_floating_pays_each_filter_output(floating: str, cost: str) -> None:
    state = _bluffs_state(f"cascade-bluffs-{floating}-{cost}", floating)
    result = solve_state_payment(
        state,
        "P0",
        (PaymentStep("filter", cost, PaymentWindow(0, "current")),),
    )
    assert result.feasible is True
