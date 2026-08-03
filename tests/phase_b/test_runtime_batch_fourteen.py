"""Direct exact-deck evidence for resolution-time draw/discard choices."""

from __future__ import annotations

from collections.abc import Iterable

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import GameObject, Zone
from mtg_kernel.strategic_choices import CardSelection, CardSelectionRequest

PLAYERS = ("P0", "P1")


class NamedSelectionProvider:
    def __init__(self, selections: dict[str, tuple[str, ...]]) -> None:
        self.selections = selections

    def choose_cards(self, request: CardSelectionRequest) -> CardSelection:
        requested = list(self.selections.get(request.purpose, ()))
        selected: list[str] = []
        for identity in requested:
            match = next(
                (
                    card
                    for card in request.candidates
                    if card.identity == identity and card.handle not in selected
                ),
                None,
            )
            if match is None:
                raise AssertionError(f"test provider could not find {identity}")
            selected.append(match.handle)
        return CardSelection(
            tuple(selected),
            "runtime-batch-fourteen-provider",
            "0" * 64,
            {"purpose": request.purpose},
        )


class IllegalSelectionProvider:
    def choose_cards(self, request: CardSelectionRequest) -> CardSelection:
        return CardSelection(
            ("not-a-legal-handle",),
            "runtime-batch-fourteen-invalid-provider",
            "0" * 64,
            {"purpose": request.purpose},
        )


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
    names: Iterable[str] | None = None,
    zone: Zone | None = None,
) -> list[GameObject]:
    values = [obj for obj in state.objects.values() if not obj.retired and not obj.ceased_to_exist]
    if names is not None:
        accepted = set(names)
        values = [obj for obj in values if obj.current_characteristics.get("name") in accepted]
    if zone is not None:
        values = [obj for obj in values if obj.zone is zone]
    return values


def test_faithless_looting_selects_discards_after_drawing_and_supports_flashback() -> None:
    for zone, expected_destination in (
        (Zone.HAND, Zone.GRAVEYARD),
        (Zone.GRAVEYARD, Zone.EXILE),
    ):
        state, executor, specs = funded_game(f"runtime-fourteen-looting-{zone.value}")
        add_card(executor, specs["Mountain"], Zone.HAND)
        add_card(executor, specs["Island"], Zone.HAND)
        add_card(executor, specs["Opt"], Zone.LIBRARY)
        add_card(executor, specs["Sol Ring"], Zone.LIBRARY)
        looting = add_card(executor, specs["Faithless Looting"], zone)
        executor.bind_strategic_choice_provider(
            NamedSelectionProvider({"DISCARD": ("Mountain", "Island")})
        )

        executor.cast(
            "P0",
            looting.object_id,
            mode="flashback" if zone is Zone.GRAVEYARD else "default",
        )
        pass_all(executor)

        assert {
            obj.current_characteristics["name"] for obj in active_objects(state, zone=Zone.HAND)
        } >= {"Opt", "Sol Ring"}
        assert {
            obj.current_characteristics["name"]
            for obj in active_objects(state, zone=Zone.GRAVEYARD)
        } >= {"Mountain", "Island"}
        assert active_objects(
            state,
            names=("Faithless Looting",),
            zone=expected_destination,
        )
        records = [choice for choice in state.choices if choice.kind == "CARD_SELECTION"]
        assert len(records) == 1
        assert records[0].selected["purpose"] == "DISCARD"
        assert records[0].selected["chosen_at"] == "RESOLUTION"
        assert len(records[0].selected["selected_handles"]) == 2


def test_frantic_search_draws_discards_then_untaps_three_selected_lands() -> None:
    state, executor, specs = funded_game("runtime-fourteen-frantic-search")
    add_card(executor, specs["Mountain"], Zone.HAND)
    add_card(executor, specs["Island"], Zone.HAND)
    add_card(executor, specs["Opt"], Zone.LIBRARY)
    add_card(executor, specs["Sol Ring"], Zone.LIBRARY)
    lands = [
        add_card(executor, specs[name], Zone.BATTLEFIELD)
        for name in ("Command Tower", "Island", "Mountain")
    ]
    for land in lands:
        assert land.permanent_status is not None
        land.permanent_status["tap"] = "TAPPED"
    search = add_card(executor, specs["Frantic Search"], Zone.HAND)
    executor.bind_strategic_choice_provider(
        NamedSelectionProvider(
            {
                "DISCARD": ("Mountain", "Island"),
                "UNTAP_LANDS": ("Command Tower", "Island", "Mountain"),
            }
        )
    )

    executor.cast("P0", search.object_id)
    pass_all(executor)

    assert all(
        land.permanent_status is not None and land.permanent_status["tap"] == "UNTAPPED"
        for land in lands
    )
    assert active_objects(state, names=("Frantic Search",), zone=Zone.GRAVEYARD)
    records = [choice for choice in state.choices if choice.kind == "CARD_SELECTION"]
    assert [record.selected["purpose"] for record in records] == [
        "DISCARD",
        "UNTAP_LANDS",
    ]
    assert [len(record.selected["selected_handles"]) for record in records] == [2, 3]


def test_resolution_time_card_selection_rejects_illegal_handles_atomically() -> None:
    state, executor, specs = funded_game("runtime-fourteen-invalid-selection")
    add_card(executor, specs["Mountain"], Zone.HAND)
    add_card(executor, specs["Island"], Zone.HAND)
    add_card(executor, specs["Opt"], Zone.LIBRARY)
    add_card(executor, specs["Sol Ring"], Zone.LIBRARY)
    looting = add_card(executor, specs["Faithless Looting"], Zone.HAND)
    executor.bind_strategic_choice_provider(IllegalSelectionProvider())

    spell = executor.cast("P0", looting.object_id)
    before_library = tuple(state.zones[executor.zones.zone_key(Zone.LIBRARY, "P0")])
    before_hand = tuple(state.zones[executor.zones.zone_key(Zone.HAND, "P0")])
    executor.pass_priority("P0")

    with pytest.raises(IllegalAction, match="selected an unavailable card"):
        executor.pass_priority("P1")

    assert tuple(state.zones[executor.zones.zone_key(Zone.LIBRARY, "P0")]) == before_library
    assert tuple(state.zones[executor.zones.zone_key(Zone.HAND, "P0")]) == before_hand
    assert spell.object_id in state.stack
    assert not [choice for choice in state.choices if choice.kind == "CARD_SELECTION"]
