"""Direct evidence for choice-bearing entry triggers and exact-deck utility cards."""

from __future__ import annotations

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import Zone
from mtg_kernel.phase_b_actions import activate_hand_ability
from mtg_kernel.phase_b_runtime_support import object_automatic_execution_supported
from mtg_policy import (
    ContextualEvaluator,
    PolicyStrategicChoiceProvider,
    load_evaluator_config,
    load_policy_matrix,
)

PLAYERS = ("P0", "P1")


def funded_game(seed: str):
    state, executor = new_game(PLAYERS, seed)
    for player in state.players.values():
        for symbol in ("W", "U", "B", "R", "G", "C"):
            player.mana_pool[symbol] = 30
    executor.bind_strategic_choice_provider(
        PolicyStrategicChoiceProvider(
            load_policy_matrix()[0],
            ContextualEvaluator(load_evaluator_config()),
        )
    )
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
    owner: str | None = None,
):
    values = [obj for obj in state.objects.values() if not obj.retired and not obj.ceased_to_exist]
    if name is not None:
        values = [obj for obj in values if obj.current_characteristics.get("name") == name]
    if zone is not None:
        values = [obj for obj in values if obj.zone is zone]
    if owner is not None:
        values = [obj for obj in values if obj.owner == owner]
    return values


def test_choice_bearing_etb_shapes_are_registered_for_automatic_execution() -> None:
    _state, executor, specs = funded_game("runtime-seventeen-support")

    for name in (
        "Izzet Boilerworks",
        "Sentinel Totem",
        "Soul-Guide Lantern",
        "Temple of Epiphany",
        "Vedalken Aethermage",
    ):
        card = add_card(executor, specs[name], Zone.HAND)
        assert object_automatic_execution_supported(card, entering=True)


def test_soul_guide_lantern_executes_entry_and_both_activated_modes() -> None:
    state, executor, specs = funded_game("runtime-seventeen-lantern")
    etb_target = add_card(executor, specs["Opt"], Zone.GRAVEYARD, owner="P1")
    card = add_card(executor, specs["Soul-Guide Lantern"], Zone.HAND)

    executor.cast(
        "P0",
        card.object_id,
        choices={"trigger_targets": {"lantern:etb": etb_target.object_id}},
    )
    pass_all(executor)
    assert state.stack
    pass_all(executor)

    lantern = active_objects(state, name="Soul-Guide Lantern", zone=Zone.BATTLEFIELD)[0]
    assert active_objects(state, name="Opt", zone=Zone.EXILE, owner="P1")

    opponent_grave = add_card(executor, specs["Mountain"], Zone.GRAVEYARD, owner="P1")
    own_grave = add_card(executor, specs["Island"], Zone.GRAVEYARD, owner="P0")
    executor.activate("P0", lantern.object_id, "lantern:opponent-graves")
    pass_all(executor)

    assert opponent_grave.retired
    assert active_objects(state, name="Mountain", zone=Zone.EXILE, owner="P1")
    assert not own_grave.retired
    assert active_objects(state, name="Island", zone=Zone.GRAVEYARD, owner="P0")

    draw_state, draw_executor, draw_specs = funded_game("runtime-seventeen-lantern-draw")
    top = add_card(draw_executor, draw_specs["Opt"], Zone.LIBRARY)
    draw_lantern = add_card(draw_executor, draw_specs["Soul-Guide Lantern"], Zone.BATTLEFIELD)

    draw_executor.activate("P0", draw_lantern.object_id, "lantern:draw")
    pass_all(draw_executor)

    assert top.retired
    assert active_objects(draw_state, name="Opt", zone=Zone.HAND, owner="P0")
    assert active_objects(
        draw_state,
        name="Soul-Guide Lantern",
        zone=Zone.GRAVEYARD,
        owner="P0",
    )


def test_vedalken_aethermage_executes_entry_bounce_and_wizardcycling() -> None:
    state, executor, specs = funded_game("runtime-seventeen-aethermage")
    sliver = add_card(
        executor,
        specs["Malcolm, Keen-Eyed Navigator"],
        Zone.BATTLEFIELD,
        owner="P1",
    )
    sliver.current_characteristics["subtypes"] = ["Siren", "Pirate", "Sliver"]
    card = add_card(executor, specs["Vedalken Aethermage"], Zone.HAND)

    executor.cast(
        "P0",
        card.object_id,
        choices={"trigger_targets": {"aethermage:etb": sliver.object_id}},
    )
    pass_all(executor)
    assert state.stack
    pass_all(executor)

    assert sliver.retired
    assert active_objects(
        state,
        name="Malcolm, Keen-Eyed Navigator",
        zone=Zone.HAND,
        owner="P1",
    )
    assert active_objects(state, name="Vedalken Aethermage", zone=Zone.BATTLEFIELD)

    cycle_state, cycle_executor, cycle_specs = funded_game("runtime-seventeen-wizardcycling")
    source = add_card(cycle_executor, cycle_specs["Vedalken Aethermage"], Zone.HAND)
    add_card(cycle_executor, cycle_specs["Dualcaster Mage"], Zone.LIBRARY)
    cycle_state.turn.phase = "COMBAT"

    activate_hand_ability(cycle_executor, "P0", source.object_id, "aethermage:wizardcycling")
    pass_all(cycle_executor)

    assert active_objects(
        cycle_state,
        name="Vedalken Aethermage",
        zone=Zone.GRAVEYARD,
        owner="P0",
    )
    assert active_objects(
        cycle_state,
        name="Dualcaster Mage",
        zone=Zone.HAND,
        owner="P0",
    )
    assert any(event.kind == "LIBRARY_SHUFFLED" for event in cycle_state.events)


def test_vedalken_aethermage_mandatory_trigger_is_removed_without_legal_sliver() -> None:
    state, executor, specs = funded_game("runtime-seventeen-aethermage-no-sliver")
    card = add_card(executor, specs["Vedalken Aethermage"], Zone.HAND)

    executor.cast("P0", card.object_id)
    pass_all(executor)

    assert not state.stack
    assert active_objects(state, name="Vedalken Aethermage", zone=Zone.BATTLEFIELD)
    assert any(event.kind == "TRIGGER_REMOVED_NO_LEGAL_TARGETS" for event in state.events)
