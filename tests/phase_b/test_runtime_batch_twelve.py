"""Direct exact-deck evidence for Electroduplicate and Scavenger Grounds."""

from __future__ import annotations

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import CopyKind, GameObject, TargetRef, Zone

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


def active_objects(
    state,
    *,
    name: str | None = None,
    zone: Zone | None = None,
) -> list[GameObject]:
    values = [obj for obj in state.objects.values() if not obj.retired and not obj.ceased_to_exist]
    if name is not None:
        values = [obj for obj in values if obj.current_characteristics.get("name") == name]
    if zone is not None:
        values = [obj for obj in values if obj.zone is zone]
    return values


def token_copies(state) -> list[GameObject]:
    return [obj for obj in active_objects(state) if obj.copy_kind is CopyKind.TOKEN_COPY]


def test_electroduplicate_normal_mode_creates_hasty_copy_then_sacrifices_it() -> None:
    state, executor, specs = funded_game("runtime-twelve-electroduplicate-normal")
    target = add_card(executor, specs["Wily Goblin"], Zone.BATTLEFIELD)
    spell = add_card(executor, specs["Electroduplicate"], Zone.HAND)

    executor.cast(
        "P0",
        spell.object_id,
        (TargetRef(target.object_id),),
        mode="normal",
    )
    pass_all(executor)

    tokens = token_copies(state)
    assert len(tokens) == 1
    assert tokens[0].current_characteristics["name"] == "Wily Goblin"
    assert "Haste" in tokens[0].current_characteristics.get("keywords", ())
    assert len(state.delayed_triggers) == 1
    assert active_objects(state, name="Electroduplicate", zone=Zone.GRAVEYARD)

    pass_all(executor)
    assert active_objects(state, name="Treasure", zone=Zone.BATTLEFIELD)

    executor.begin_step("END")
    pass_all(executor)
    assert tokens[0].retired
    assert not token_copies(state)


def test_electroduplicate_flashback_mode_exiles_the_card_after_resolution() -> None:
    state, executor, specs = funded_game("runtime-twelve-electroduplicate-flashback")
    target = add_card(executor, specs["Spectral Sailor"], Zone.BATTLEFIELD)
    spell = add_card(executor, specs["Electroduplicate"], Zone.GRAVEYARD)

    executor.cast(
        "P0",
        spell.object_id,
        (TargetRef(target.object_id),),
        mode="flashback",
    )
    pass_all(executor)

    tokens = token_copies(state)
    assert len(tokens) == 1
    assert tokens[0].current_characteristics["name"] == "Spectral Sailor"
    assert "Haste" in tokens[0].current_characteristics.get("keywords", ())
    assert active_objects(state, name="Electroduplicate", zone=Zone.EXILE)

    executor.begin_step("END")
    pass_all(executor)
    assert tokens[0].retired
    assert not token_copies(state)


def test_scavenger_grounds_executes_mana_and_graveyard_exile_modes() -> None:
    mana_state, mana_executor, mana_specs = funded_game("runtime-twelve-grounds-mana")
    grounds = add_card(mana_executor, mana_specs["Scavenger Grounds"], Zone.BATTLEFIELD)
    for symbol in ("W", "U", "B", "R", "G", "C"):
        mana_state.players["P0"].mana_pool[symbol] = 0

    mana_executor.activate("P0", grounds.object_id, "grounds:c")

    assert mana_state.players["P0"].mana_pool["C"] == 1
    assert mana_state.stack == []

    state, executor, specs = funded_game("runtime-twelve-grounds-exile")
    grounds = add_card(executor, specs["Scavenger Grounds"], Zone.BATTLEFIELD)
    add_card(executor, specs["Opt"], Zone.GRAVEYARD)
    add_card(executor, specs["Mountain"], Zone.GRAVEYARD, owner="P1")

    executor.activate(
        "P0",
        grounds.object_id,
        "grounds:exile",
        choices={"additional_sacrifice_object_id": grounds.object_id},
    )
    assert grounds.retired
    pass_all(executor)

    assert not active_objects(state, zone=Zone.GRAVEYARD)
    assert active_objects(state, name="Scavenger Grounds", zone=Zone.EXILE)
    assert active_objects(state, name="Opt", zone=Zone.EXILE)
    assert active_objects(state, name="Mountain", zone=Zone.EXILE)
