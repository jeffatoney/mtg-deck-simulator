"""Pain-land availability is rules legality, not survival preference."""

from __future__ import annotations

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import Zone
from mtg_kernel.resource_payment import PaymentStep, PaymentWindow
from mtg_kernel.resource_sources import solve_state_payment

PLAYERS = ("P0", "P1")
MANA_SYMBOLS = ("W", "U", "B", "R", "G", "C")


def _reef_game(seed: str, *, life: int) -> tuple[object, object, object]:
    state, executor = new_game(PLAYERS, seed)
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    reef = add_card(executor, specs["Shivan Reef"], Zone.BATTLEFIELD, owner="P0")
    for symbol in MANA_SYMBOLS:
        state.players["P0"].mana_pool[symbol] = 0
    state.players["P0"].life = life
    return state, executor, reef


def _blue_step() -> PaymentStep:
    return PaymentStep("blue", "{U}", PaymentWindow(0, "current"))


def test_pain_land_available_when_life_exceeds_damage() -> None:
    state, _executor, _reef = _reef_game("pain-land-above", life=2)
    assert solve_state_payment(state, "P0", (_blue_step(),)).feasible is True


def test_pain_land_available_when_life_equals_damage() -> None:
    state, _executor, _reef = _reef_game("pain-land-equal", life=1)
    result = solve_state_payment(state, "P0", (_blue_step(),))
    assert result.feasible is True
    assert result.colored_pip_deficits == ()


def test_pain_land_generic_colorless_mode_remains_independent() -> None:
    state, _executor, _reef = _reef_game("pain-land-colorless", life=1)
    colorless = solve_state_payment(
        state,
        "P0",
        (PaymentStep("colorless", "{C}", PaymentWindow(0, "current")),),
    )
    assert colorless.feasible is True


def test_pain_land_resolution_at_equal_life_is_legal_and_sba_follows() -> None:
    state, executor, reef = _reef_game("pain-land-sba", life=1)
    executor.activate("P0", reef.object_id, "reef:colored", choices={"mana_color": "U"})
    assert state.players["P0"].mana_pool["U"] == 1
    mana_index = next(
        index
        for index, event in enumerate(state.events)
        if event.kind == "MANA_ADDED_AND_PLAYER_DAMAGED"
    )
    terminal = [event for event in state.events if event.kind == "GAME_TERMINATED"]
    assert terminal
    terminal_index = next(
        index for index, event in enumerate(state.events) if event.kind == "GAME_TERMINATED"
    )
    assert mana_index < terminal_index
    assert state.players["P0"].life <= 0
    assert state.terminal.status == "TERMINAL"
