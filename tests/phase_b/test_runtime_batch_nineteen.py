"""Direct production-path evidence for Into the Roil and kicker payment."""

from __future__ import annotations

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import TargetRef, Zone

PLAYERS = ("P0", "P1")


def game_with_exact_mana(seed: str, blue_mana: int):
    state, executor = new_game(PLAYERS, seed)
    for player in state.players.values():
        player.mana_pool.update({symbol: 0 for symbol in ("W", "U", "B", "R", "G", "C")})
    state.players["P0"].mana_pool["U"] = blue_mana
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    return state, executor, specs


def pass_all(executor) -> None:
    for _ in PLAYERS:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def active_objects(state, *, name: str, zone: Zone, owner: str):
    return [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and not obj.ceased_to_exist
        and obj.zone is zone
        and obj.owner == owner
        and obj.current_characteristics.get("name") == name
    ]


def test_into_the_roil_executes_normal_and_kicked_paths() -> None:
    for raw_kicked, expected_kicked, blue_mana, expected_total in (
        (False, False, 2, 2),
        (True, True, 4, 4),
        ("yes", True, 4, 4),
        ([], False, 2, 2),
    ):
        state, executor, specs = game_with_exact_mana(
            f"runtime-nineteen-into-roil-{raw_kicked!r}", blue_mana
        )
        target = add_card(executor, specs["Sol Ring"], Zone.BATTLEFIELD, owner="P1")
        draw_card = add_card(executor, specs["Island"], Zone.LIBRARY, owner="P0")
        into_the_roil = add_card(executor, specs["Into the Roil"], Zone.HAND, owner="P0")

        spell = executor.cast(
            "P0",
            into_the_roil.object_id,
            targets=(TargetRef(target.object_id),),
            choices={"kicked": raw_kicked},
        )
        action = executor._created_action(spell)
        assert spell.current_characteristics.get("kicked", False) is expected_kicked
        assert spell.current_characteristics["cast_choices"]["kicked"] == raw_kicked
        assert action.payments["cost"]["U"] == (2 if expected_kicked else 1)
        assert action.payments["cost"]["GENERIC"] == (2 if expected_kicked else 1)
        assert sum(action.payments["mana"].values()) == expected_total
        assert state.players["P0"].mana_pool["U"] == 0

        pass_all(executor)

        assert target.retired
        assert active_objects(state, name="Sol Ring", zone=Zone.HAND, owner="P1")
        if expected_kicked:
            assert draw_card.retired
            assert active_objects(state, name="Island", zone=Zone.HAND, owner="P0")
        else:
            assert not draw_card.retired
            assert active_objects(state, name="Island", zone=Zone.LIBRARY, owner="P0")


def test_into_the_roil_kicker_payment_failure_is_atomic() -> None:
    state, executor, specs = game_with_exact_mana("runtime-nineteen-kicker-atomic", 3)
    target = add_card(executor, specs["Sol Ring"], Zone.BATTLEFIELD, owner="P1")
    into_the_roil = add_card(executor, specs["Into the Roil"], Zone.HAND, owner="P0")
    before = state_hash(state)

    with pytest.raises(IllegalAction, match="insufficient mana"):
        executor.cast(
            "P0",
            into_the_roil.object_id,
            targets=(TargetRef(target.object_id),),
            choices={"kicked": True},
        )

    assert state_hash(state) == before
