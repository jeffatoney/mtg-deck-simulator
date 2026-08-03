"""Executable coverage for shared exact-deck land-search effects."""

from __future__ import annotations

from typing import Any

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import Zone
from mtg_kernel.replay import transcript, validate_replay
from mtg_kernel.strategic_choices import TutorChoiceRequest, TutorChoiceSelection


class FirstBasicProvider:
    def choose_tutor(self, request: TutorChoiceRequest) -> TutorChoiceSelection:
        selected = request.eligible_identities[0] if request.eligible_identities else "FAIL_TO_FIND"
        return TutorChoiceSelection(selected, "test-basic-v1", "a" * 64, {})

    def choose_fact_or_fiction(self, request: Any) -> Any:
        raise AssertionError(f"unexpected Fact or Fiction request: {request}")

    def choose_spell_copy_targets(self, request: Any) -> Any:
        raise AssertionError(f"unexpected spell-copy request: {request}")


def pass_all(executor) -> None:
    for _ in range(2):
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


@pytest.mark.parametrize(
    ("land_name", "ability_id"),
    (
        ("Evolving Wilds", "evolving-wilds:fetch"),
        ("Terramorphic Expanse", "terramorphic:fetch"),
    ),
)
def test_fetch_lands_sacrifice_then_find_basic_land_tapped(land_name: str, ability_id: str) -> None:
    seed = f"fetch-{land_name}"
    state, executor = new_game(("P0", "P1"), seed)
    executor.bind_strategic_choice_provider(FirstBasicProvider())
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    source = add_card(executor, specs[land_name], Zone.BATTLEFIELD)
    add_card(executor, specs["Mountain"], Zone.LIBRARY)
    add_card(executor, specs["Island"], Zone.LIBRARY)
    add_card(executor, specs["Izzet Boilerworks"], Zone.LIBRARY)

    executor.activate("P0", source.object_id, ability_id)

    assert source.retired
    assert any(
        not obj.retired
        and obj.zone is Zone.GRAVEYARD
        and obj.current_characteristics.get("name") == land_name
        for obj in state.objects.values()
    )

    pass_all(executor)

    fetched = [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.zone is Zone.BATTLEFIELD
        and "Basic" in obj.current_characteristics.get("supertypes", ())
    ]
    assert len(fetched) == 1
    assert fetched[0].permanent_status is not None
    assert fetched[0].permanent_status["tap"] == "TAPPED"
    assert any(
        choice.kind == "FETCH_BASIC" and choice.selected["identity"] in {"Island", "Mountain"}
        for choice in state.choices
    )
    assert any(event.kind == "LIBRARY_SHUFFLED" for event in state.events)
    assert all(
        obj.current_characteristics.get("name") != "Izzet Boilerworks" or obj.zone is Zone.LIBRARY
        for obj in state.objects.values()
        if not obj.retired
    )

    replayed = validate_replay(transcript(state, seed=seed))
    assert state_hash(replayed) == state_hash(state)
