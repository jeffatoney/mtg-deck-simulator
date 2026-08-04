"""Direct production-path evidence for Demolition Field resolution."""

from __future__ import annotations

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import TargetRef, Zone
from mtg_kernel.strategic_choices import TutorChoiceRequest, TutorChoiceSelection

PLAYERS = ("P0", "P1")
MANA_SYMBOLS = ("W", "U", "B", "R", "G", "C")


class BasicLandProvider:
    def __init__(self, selections: dict[str, str]) -> None:
        self.selections = selections

    def choose_tutor(self, request: TutorChoiceRequest) -> TutorChoiceSelection:
        return TutorChoiceSelection(
            self.selections.get(request.actor_id, "FAIL_TO_FIND"),
            "runtime-batch-twenty-five-provider",
            "0" * 64,
            {"actor_id": request.actor_id},
        )


def game_with_exact_mana(seed: str):
    state, executor = new_game(PLAYERS, seed)
    for player in state.players.values():
        player.mana_pool.update({symbol: 0 for symbol in MANA_SYMBOLS})
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    return state, executor, specs


def pass_all(executor) -> None:
    for _ in PLAYERS:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def active_named(state, name: str, zone: Zone, owner: str):
    return [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and not obj.ceased_to_exist
        and obj.zone is zone
        and obj.owner == owner
        and obj.current_characteristics.get("name") == name
    ]


def test_demolition_field_destroys_target_and_resolves_both_basic_searches() -> None:
    state, executor, specs = game_with_exact_mana("runtime-twenty-five-searches")
    state.players["P0"].mana_pool["C"] = 2
    field = add_card(executor, specs["Demolition Field"], Zone.BATTLEFIELD, owner="P0")
    target = add_card(executor, specs["Thriving Isle"], Zone.BATTLEFIELD, owner="P1")
    add_card(executor, specs["Island"], Zone.LIBRARY, owner="P1")
    add_card(executor, specs["Mountain"], Zone.LIBRARY, owner="P0")
    executor.bind_strategic_choice_provider(
        BasicLandProvider({"P1": "Island", "P0": "Mountain"})
    )

    ability = executor.activate(
        "P0",
        field.object_id,
        "demolition-field:destroy",
        targets=(TargetRef(target.object_id),),
    )

    assert ability is not None
    assert field.retired
    assert active_named(state, "Demolition Field", Zone.GRAVEYARD, "P0")
    pass_all(executor)

    assert target.retired
    assert active_named(state, "Thriving Isle", Zone.GRAVEYARD, "P1")
    opponent_basic = active_named(state, "Island", Zone.BATTLEFIELD, "P1")
    controller_basic = active_named(state, "Mountain", Zone.BATTLEFIELD, "P0")
    assert len(opponent_basic) == 1
    assert len(controller_basic) == 1
    assert opponent_basic[0].permanent_status is not None
    assert controller_basic[0].permanent_status is not None
    assert opponent_basic[0].permanent_status["tap"] == "UNTAPPED"
    assert controller_basic[0].permanent_status["tap"] == "UNTAPPED"

    choices = [choice for choice in state.choices if choice.kind == "FETCH_BASIC"]
    assert [choice.player_id for choice in choices] == ["P1", "P0"]
    assert [choice.selected["identity"] for choice in choices] == ["Island", "Mountain"]
    assert [choice.selected["search_role"] for choice in choices] == [
        "DESTROYED_LAND_CONTROLLER",
        "ABILITY_CONTROLLER",
    ]
    assert sum(event.kind == "LIBRARY_SHUFFLED" for event in state.events) == 2


def test_demolition_field_allows_each_player_to_fail_to_find() -> None:
    state, executor, specs = game_with_exact_mana("runtime-twenty-five-fail-to-find")
    state.players["P0"].mana_pool["C"] = 2
    field = add_card(executor, specs["Demolition Field"], Zone.BATTLEFIELD, owner="P0")
    target = add_card(executor, specs["Temple of Epiphany"], Zone.BATTLEFIELD, owner="P1")
    add_card(executor, specs["Island"], Zone.LIBRARY, owner="P1")
    add_card(executor, specs["Mountain"], Zone.LIBRARY, owner="P0")
    executor.bind_strategic_choice_provider(
        BasicLandProvider({"P1": "FAIL_TO_FIND", "P0": "FAIL_TO_FIND"})
    )

    executor.activate(
        "P0",
        field.object_id,
        "demolition-field:destroy",
        targets=(TargetRef(target.object_id),),
    )
    pass_all(executor)

    assert target.retired
    assert active_named(state, "Island", Zone.LIBRARY, "P1")
    assert active_named(state, "Mountain", Zone.LIBRARY, "P0")
    choices = [choice for choice in state.choices if choice.kind == "FETCH_BASIC"]
    assert [choice.selected["identity"] for choice in choices] == [
        "FAIL_TO_FIND",
        "FAIL_TO_FIND",
    ]
    assert sum(event.kind == "LIBRARY_SHUFFLED" for event in state.events) == 2


def test_demolition_field_missing_provider_fails_closed_atomically() -> None:
    state, executor, specs = game_with_exact_mana("runtime-twenty-five-missing-provider")
    state.players["P0"].mana_pool["C"] = 2
    field = add_card(executor, specs["Demolition Field"], Zone.BATTLEFIELD, owner="P0")
    target = add_card(executor, specs["Thriving Isle"], Zone.BATTLEFIELD, owner="P1")
    add_card(executor, specs["Island"], Zone.LIBRARY, owner="P1")

    ability = executor.activate(
        "P0",
        field.object_id,
        "demolition-field:destroy",
        targets=(TargetRef(target.object_id),),
    )
    assert ability is not None
    assert field.retired
    executor.pass_priority("P0")

    with pytest.raises(
        IllegalAction,
        match="Demolition Field basic-land search resolution requires an injected",
    ):
        executor.pass_priority("P1")

    assert not target.retired
    assert active_named(state, "Thriving Isle", Zone.BATTLEFIELD, "P1")
    assert active_named(state, "Island", Zone.LIBRARY, "P1")
    assert active_named(state, "Demolition Field", Zone.GRAVEYARD, "P0")
    assert ability.object_id in state.stack
    assert not [choice for choice in state.choices if choice.kind == "FETCH_BASIC"]
