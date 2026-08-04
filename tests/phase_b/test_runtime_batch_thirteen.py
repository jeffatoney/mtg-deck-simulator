"""Direct exact-deck evidence for Cascade Bluffs filter-mana choices."""

from __future__ import annotations

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import Zone


def game_with_bluffs(seed: str):
    state, executor = new_game(("P0", "P1"), seed)
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    bluffs = add_card(executor, specs["Cascade Bluffs"], Zone.BATTLEFIELD)
    for symbol in ("W", "U", "B", "R", "G", "C"):
        state.players["P0"].mana_pool[symbol] = 0
    state.players["P0"].mana_pool["U"] = 1
    return state, executor, bluffs


@pytest.mark.parametrize(
    ("selected", "expected_blue", "expected_red"),
    [
        ({"U": 2}, 2, 0),
        ({"U": 1, "R": 1}, 1, 1),
        ({"R": 2}, 0, 2),
    ],
)
def test_cascade_bluffs_executes_each_declared_filter_option(
    selected: dict[str, int],
    expected_blue: int,
    expected_red: int,
) -> None:
    state, executor, bluffs = game_with_bluffs(
        f"runtime-thirteen-bluffs-{expected_blue}-{expected_red}"
    )

    executor.activate(
        "P0",
        bluffs.object_id,
        "cascade-bluffs:filter",
        choices={"mana_option": selected},
    )

    assert state.players["P0"].mana_pool["U"] == expected_blue
    assert state.players["P0"].mana_pool["R"] == expected_red
    assert bluffs.permanent_status is not None
    assert bluffs.permanent_status["tap"] == "TAPPED"
    assert state.stack == []


def test_cascade_bluffs_rejects_an_unlisted_option_atomically() -> None:
    state, executor, bluffs = game_with_bluffs("runtime-thirteen-bluffs-invalid")
    before_pool = dict(state.players["P0"].mana_pool)

    with pytest.raises(IllegalAction, match="selected filter-mana option is unavailable"):
        executor.activate(
            "P0",
            bluffs.object_id,
            "cascade-bluffs:filter",
            choices={"mana_option": {"U": 3}},
        )

    current = state.objects[bluffs.object_id]
    assert current.permanent_status is not None
    assert current.permanent_status["tap"] == "UNTAPPED"
    assert state.players["P0"].mana_pool == before_pool
    assert state.stack == []
