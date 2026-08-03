"""Executable coverage for the first exact-deck Phase B runtime batch."""

from __future__ import annotations

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import TargetRef, Zone


def funded_game(seed: str, players: tuple[str, ...] = ("P0", "P1")):
    state, executor = new_game(players, seed)
    for player in state.players.values():
        for symbol in ("W", "U", "B", "R", "G", "C"):
            player.mana_pool[symbol] = 30
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    return state, executor, specs


def pass_all(executor) -> None:
    players = [player.player_id for player in executor.state.players.values() if player.in_game]
    for _ in players:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def test_aetherize_returns_each_attacking_creature_and_not_nonattacker() -> None:
    state, executor, specs = funded_game("aetherize")
    attacker_a = add_card(executor, specs["Wily Goblin"], Zone.BATTLEFIELD, owner="P1")
    attacker_b = add_card(
        executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD, owner="P1"
    )
    nonattacker = add_card(executor, specs["Storm Fleet Sprinter"], Zone.BATTLEFIELD, owner="P1")
    attacker_a.current_characteristics["attacking"] = True
    attacker_b.current_characteristics["attacking"] = True
    spell = add_card(executor, specs["Aetherize"], Zone.HAND)

    executor.cast("P0", spell.object_id)
    pass_all(executor)

    returned_names = {
        obj.current_characteristics.get("name")
        for obj in state.objects.values()
        if not obj.retired and obj.zone is Zone.HAND and obj.owner == "P1"
    }
    assert returned_names == {"Wily Goblin", "Malcolm, Keen-Eyed Navigator"}
    assert not nonattacker.retired and nonattacker.zone is Zone.BATTLEFIELD


def test_fiery_cannonade_uses_umbra_armor_replacement() -> None:
    state, executor, specs = funded_game("umbra-armor")
    creature = add_card(executor, specs["Dualcaster Mage"], Zone.BATTLEFIELD)
    pirate = add_card(executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD)
    aura = add_card(executor, specs["Crab Umbra"], Zone.HAND)
    executor.cast("P0", aura.object_id, (TargetRef(creature.object_id),))
    pass_all(executor)
    attached = next(
        obj
        for obj in state.objects.values()
        if not obj.retired and obj.current_characteristics.get("name") == "Crab Umbra"
    )

    cannonade = add_card(executor, specs["Fiery Cannonade"], Zone.HAND)
    executor.cast("P0", cannonade.object_id)
    pass_all(executor)

    assert (
        not creature.retired and creature.zone is Zone.BATTLEFIELD and creature.marked_damage == 0
    )
    assert not pirate.retired and pirate.zone is Zone.BATTLEFIELD and pirate.marked_damage == 0
    assert attached.retired
    assert any(
        not obj.retired
        and obj.zone is Zone.GRAVEYARD
        and obj.current_characteristics.get("name") == "Crab Umbra"
        for obj in state.objects.values()
    )


def test_dispel_counters_an_instant_on_the_shared_stack_path() -> None:
    state, executor, specs = funded_game("dispel")
    state.turn.active_player_id = "P1"
    state.turn.priority_holder_id = "P1"
    opt = add_card(executor, specs["Opt"], Zone.HAND, owner="P1")
    opt_spell = executor.cast("P1", opt.object_id, choices={"scry_to_bottom": False})
    executor.pass_priority("P1")
    dispel = add_card(executor, specs["Dispel"], Zone.HAND)
    executor.cast("P0", dispel.object_id, (TargetRef(opt_spell.object_id),))
    pass_all(executor)

    assert opt_spell.retired
    assert not any(not obj.retired and obj.zone is Zone.STACK for obj in state.objects.values())


def test_psychosis_crawler_tracks_hand_size_and_draw_trigger() -> None:
    state, executor, specs = funded_game("crawler")
    crawler = add_card(executor, specs["Psychosis Crawler"], Zone.BATTLEFIELD)
    for name in ("Island", "Mountain", "Opt"):
        add_card(executor, specs[name], Zone.HAND)
    executor.check_state_based_actions()
    assert crawler.current_characteristics["power"] == 3
    assert crawler.current_characteristics["toughness"] == 3

    add_card(executor, specs["Island"], Zone.LIBRARY)
    before = state.players["P1"].life
    executor.draw_card("P0")
    pass_all(executor)

    assert crawler.current_characteristics["power"] == 4
    assert crawler.current_characteristics["toughness"] == 4
    assert state.players["P1"].life == before - 1


def test_wily_goblin_and_lightning_rig_cast_triggers_execute() -> None:
    state, executor, specs = funded_game("cast-and-etb-triggers")
    crew = add_card(executor, specs["Lightning-Rig Crew"], Zone.BATTLEFIELD)
    assert crew.permanent_status is not None
    crew.permanent_status["tap"] = "TAPPED"
    wily = add_card(executor, specs["Wily Goblin"], Zone.HAND)

    executor.cast("P0", wily.object_id)
    pass_all(executor)
    assert crew.permanent_status["tap"] == "UNTAPPED"
    pass_all(executor)
    pass_all(executor)

    treasures = [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.zone is Zone.BATTLEFIELD
        and obj.current_characteristics.get("name") == "Treasure"
    ]
    assert len(treasures) == 1
