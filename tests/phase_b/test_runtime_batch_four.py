"""Executable coverage for exact-deck mana permanents and entry choices."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.land_actions import play_land
from mtg_kernel.models import GameObject, Zone


def funded_game(seed: str):
    state, executor = new_game(("P0", "P1"), seed)
    for symbol in ("W", "U", "B", "R", "G", "C"):
        state.players["P0"].mana_pool[symbol] = 30
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    return state, executor, specs


def pass_all(executor) -> None:
    for _ in range(2):
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def reset_pool(state, **mana: int) -> None:
    for symbol in ("W", "U", "B", "R", "G", "C"):
        state.players["P0"].mana_pool[symbol] = int(mana.get(symbol, 0))


def active_permanent(state, name: str) -> GameObject:
    return next(
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.zone is Zone.BATTLEFIELD
        and obj.current_characteristics.get("name") == name
    )


def put_permanent_into_play(executor, specs: dict[str, Any], name: str) -> GameObject:
    card = add_card(executor, specs[name], Zone.HAND)
    if "Land" in card.current_characteristics.get("card_types", ()):
        return play_land(executor, "P0", card.object_id)
    executor.cast("P0", card.object_id)
    pass_all(executor)
    return active_permanent(executor.state, name)


@pytest.mark.parametrize(
    ("name", "ability_id", "choices", "symbol", "amount"),
    (
        ("Island", "island:u", {}, "U", 1),
        ("Mountain", "mountain:r", {}, "R", 1),
        ("Sol Ring", "sol-ring:cc", {}, "C", 2),
        ("Arcane Signet", "arcane-signet:mana", {"mana_color": "U"}, "U", 1),
        ("Command Tower", "command-tower:mana", {"mana_color": "R"}, "R", 1),
        (
            "Exotic Orchard",
            "exotic-orchard:mana",
            {"mana_color": "U", "opponent_mana_profile": "blue_red_available"},
            "U",
            1,
        ),
        (
            "Fellwar Stone",
            "fellwar-stone:mana",
            {"mana_color": "R", "opponent_mana_profile": "blue_red_available"},
            "R",
            1,
        ),
    ),
)
def test_simple_exact_deck_mana_permanents(
    name: str,
    ability_id: str,
    choices: dict[str, str],
    symbol: str,
    amount: int,
) -> None:
    state, executor, specs = funded_game(f"mana-{name}")
    permanent = put_permanent_into_play(executor, specs, name)
    reset_pool(state)

    executor.activate("P0", permanent.object_id, ability_id, choices=choices)

    assert state.players["P0"].mana_pool[symbol] == amount
    assert state.stack == []
    assert permanent.permanent_status is not None
    assert permanent.permanent_status["tap"] == "TAPPED"


def test_izzet_signet_spends_one_mana_and_produces_blue_red() -> None:
    state, executor, specs = funded_game("izzet-signet")
    signet = put_permanent_into_play(executor, specs, "Izzet Signet")
    reset_pool(state, C=1)

    executor.activate("P0", signet.object_id, "izzet-signet:filter")

    assert state.players["P0"].mana_pool["C"] == 0
    assert state.players["P0"].mana_pool["U"] == 1
    assert state.players["P0"].mana_pool["R"] == 1


@pytest.mark.parametrize(
    ("ability_id", "starting", "choices", "expected"),
    (
        ("lens:c", {}, {}, {"C": 1}),
        ("lens:filter", {"C": 1}, {"mana_color": "U"}, {"C": 0, "U": 1}),
    ),
)
def test_prismatic_lens_mana_modes(
    ability_id: str,
    starting: dict[str, int],
    choices: dict[str, str],
    expected: dict[str, int],
) -> None:
    state, executor, specs = funded_game(f"lens-{ability_id}")
    lens = put_permanent_into_play(executor, specs, "Prismatic Lens")
    reset_pool(state, **starting)

    executor.activate("P0", lens.object_id, ability_id, choices=choices)

    for symbol, amount in expected.items():
        assert state.players["P0"].mana_pool[symbol] == amount


@pytest.mark.parametrize(
    ("ability_id", "choices", "symbol", "amount", "life"),
    (
        ("reef:c", {}, "C", 1, 40),
        ("reef:colored", {"mana_color": "R"}, "R", 1, 39),
    ),
)
def test_shivan_reef_mana_modes(
    ability_id: str,
    choices: dict[str, str],
    symbol: str,
    amount: int,
    life: int,
) -> None:
    state, executor, specs = funded_game(f"reef-{ability_id}")
    reef = put_permanent_into_play(executor, specs, "Shivan Reef")
    reset_pool(state)

    executor.activate("P0", reef.object_id, ability_id, choices=choices)

    assert state.players["P0"].mana_pool[symbol] == amount
    assert state.players["P0"].life == life


def test_mind_stone_mana_and_sacrifice_draw_paths() -> None:
    mana_state, mana_executor, mana_specs = funded_game("mind-stone-mana")
    mana_stone = put_permanent_into_play(mana_executor, mana_specs, "Mind Stone")
    reset_pool(mana_state)
    mana_executor.activate("P0", mana_stone.object_id, "mind-stone:c")
    assert mana_state.players["P0"].mana_pool["C"] == 1

    state, executor, specs = funded_game("mind-stone-draw")
    stone = put_permanent_into_play(executor, specs, "Mind Stone")
    add_card(executor, specs["Island"], Zone.LIBRARY)
    reset_pool(state, C=1)
    executor.activate("P0", stone.object_id, "mind-stone:draw")
    assert stone.retired
    pass_all(executor)
    assert any(
        not obj.retired
        and obj.zone is Zone.HAND
        and obj.current_characteristics.get("name") == "Island"
        for obj in state.objects.values()
    )


@pytest.mark.parametrize("mana_color", ("U", "R"))
def test_thriving_isle_entry_choice_and_mana(mana_color: str) -> None:
    state, executor, specs = funded_game(f"thriving-{mana_color}")
    card = add_card(executor, specs["Thriving Isle"], Zone.HAND)
    isle = play_land(executor, "P0", card.object_id, {"chosen_color": "R"})
    assert isle.permanent_status is not None
    assert isle.permanent_status["tap"] == "TAPPED"
    assert isle.current_characteristics["chosen_color"] == "R"
    isle.permanent_status["tap"] = "UNTAPPED"
    reset_pool(state)

    executor.activate("P0", isle.object_id, "thriving:mana", choices={"mana_color": mana_color})

    assert state.players["P0"].mana_pool[mana_color] == 1


def test_frostboil_snarl_reveal_decline_and_mana_paths() -> None:
    state, executor, specs = funded_game("frostboil-snarl-reveal")
    reveal = add_card(executor, specs["Island"], Zone.HAND)
    card = add_card(executor, specs["Frostboil Snarl"], Zone.HAND)
    snarl = play_land(
        executor,
        "P0",
        card.object_id,
        {"reveal_object_id": reveal.object_id},
    )
    assert snarl.permanent_status is not None
    assert snarl.permanent_status["tap"] == "UNTAPPED"
    reset_pool(state)

    executor.activate("P0", snarl.object_id, "snarl:mana", choices={"mana_color": "U"})

    assert state.players["P0"].mana_pool["U"] == 1
    assert any(choice.kind == "REVEAL_FOR_LAND_ENTRY" for choice in state.choices)

    decline_state, decline_executor, decline_specs = funded_game("frostboil-snarl-decline")
    decline_card = add_card(decline_executor, decline_specs["Frostboil Snarl"], Zone.HAND)
    declined = play_land(decline_executor, "P0", decline_card.object_id)
    assert declined.permanent_status is not None
    assert declined.permanent_status["tap"] == "TAPPED"
    assert any(
        choice.kind == "REVEAL_FOR_LAND_ENTRY" and choice.selected == "DECLINE"
        for choice in decline_state.choices
    )
