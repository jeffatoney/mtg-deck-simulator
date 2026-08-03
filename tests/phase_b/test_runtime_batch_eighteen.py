"""Direct evidence for Curiosity's explicit optional trigger path."""

from __future__ import annotations

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import TargetRef, Zone
from mtg_kernel.phase_b_runtime_support import object_automatic_execution_supported

PLAYERS = ("P0", "P1")


def funded_game(seed: str):
    state, executor = new_game(PLAYERS, seed)
    for player in state.players.values():
        for symbol in ("W", "U", "B", "R", "G", "C"):
            player.mana_pool[symbol] = 30
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    return state, executor, specs


def pass_all(executor) -> None:
    for _ in PLAYERS:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def active_objects(state, *, name: str, zone: Zone):
    return [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and not obj.ceased_to_exist
        and obj.zone is zone
        and obj.current_characteristics.get("name") == name
    ]


def test_curiosity_requires_and_executes_each_explicit_optional_choice() -> None:
    state, executor, specs = funded_game("runtime-eighteen-curiosity")
    creature = add_card(executor, specs["Dualcaster Mage"], Zone.BATTLEFIELD)
    curiosity = add_card(executor, specs["Curiosity"], Zone.HAND)
    first_draw = add_card(executor, specs["Island"], Zone.LIBRARY)
    second_draw = add_card(executor, specs["Mountain"], Zone.LIBRARY)

    assert object_automatic_execution_supported(curiosity, entering=True)

    executor.cast("P0", curiosity.object_id, targets=(TargetRef(creature.object_id),))
    pass_all(executor)

    aura = active_objects(state, name="Curiosity", zone=Zone.BATTLEFIELD)[0]
    assert aura.attached_to_ref is not None
    assert aura.attached_to_ref.object_id == creature.object_id

    executor.deal_damage_to_player(
        creature.object_id,
        "P1",
        1,
        combat=True,
        choices={"optional": {"curiosity:damage": False}},
    )
    pass_all(executor)

    assert not second_draw.retired
    assert active_objects(state, name="Mountain", zone=Zone.LIBRARY)

    executor.deal_damage_to_player(
        creature.object_id,
        "P1",
        1,
        combat=True,
        choices={"optional": {"curiosity:damage": True}},
    )
    pass_all(executor)

    assert second_draw.retired
    assert active_objects(state, name="Mountain", zone=Zone.HAND)
    assert not first_draw.retired
    optional_choices = [choice for choice in state.choices if choice.kind == "OPTIONAL_TRIGGER"]
    assert [choice.selected for choice in optional_choices] == [False, True]
