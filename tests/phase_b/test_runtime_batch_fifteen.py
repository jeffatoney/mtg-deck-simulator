"""Direct exact-deck evidence for look/select/rest-on-bottom effects."""

from __future__ import annotations

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import Zone
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
            "runtime-batch-fifteen-provider",
            "0" * 64,
            {"purpose": request.purpose},
        )


class IllegalSelectionProvider:
    def choose_cards(self, request: CardSelectionRequest) -> CardSelection:
        return CardSelection(
            ("not-a-legal-handle",),
            "runtime-batch-fifteen-invalid-provider",
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


def library_names(state, executor) -> list[str]:
    key = executor.zones.zone_key(Zone.LIBRARY, "P0")
    return [
        str(state.objects[object_id].current_characteristics["name"])
        for object_id in state.zones[key]
    ]


@pytest.mark.parametrize(
    ("card_name", "selected_name", "bottom_order", "expected_library"),
    (
        (
            "Impulse",
            "Twinflame",
            ("Opt", "Island", "Sol Ring"),
            ["Opt", "Island", "Sol Ring", "Mountain"],
        ),
        (
            "Sleight of Hand",
            "Twinflame",
            ("Sol Ring",),
            ["Sol Ring", "Mountain", "Island", "Opt"],
        ),
    ),
)
def test_look_select_rest_bottom_executes_exact_deck_cards(
    card_name: str,
    selected_name: str,
    bottom_order: tuple[str, ...],
    expected_library: list[str],
) -> None:
    state, executor, specs = funded_game(f"runtime-fifteen-{card_name}")
    for name in ("Mountain", "Island", "Opt", "Sol Ring", "Twinflame"):
        add_card(executor, specs[name], Zone.LIBRARY)
    spell = add_card(executor, specs[card_name], Zone.HAND)
    executor.bind_strategic_choice_provider(
        NamedSelectionProvider(
            {
                "LOOK_SELECT": (selected_name,),
                "ORDER_LIBRARY_BOTTOM": bottom_order,
            }
        )
    )

    executor.cast("P0", spell.object_id)
    pass_all(executor)

    hand_key = executor.zones.zone_key(Zone.HAND, "P0")
    hand_names = {
        state.objects[object_id].current_characteristics["name"]
        for object_id in state.zones[hand_key]
    }
    assert selected_name in hand_names
    assert library_names(state, executor) == expected_library
    records = [choice for choice in state.choices if choice.kind == "CARD_SELECTION"]
    assert [record.selected["purpose"] for record in records] == [
        "LOOK_SELECT",
        "ORDER_LIBRARY_BOTTOM",
    ]
    assert all(record.selected["chosen_at"] == "RESOLUTION" for record in records)
    assert [len(record.selected["selected_handles"]) for record in records] == [
        1,
        len(bottom_order),
    ]


def test_look_select_rejects_illegal_provider_output_atomically() -> None:
    state, executor, specs = funded_game("runtime-fifteen-invalid-selection")
    for name in ("Mountain", "Island", "Opt", "Sol Ring", "Twinflame"):
        add_card(executor, specs[name], Zone.LIBRARY)
    impulse = add_card(executor, specs["Impulse"], Zone.HAND)
    executor.bind_strategic_choice_provider(IllegalSelectionProvider())

    spell = executor.cast("P0", impulse.object_id)
    library_key = executor.zones.zone_key(Zone.LIBRARY, "P0")
    hand_key = executor.zones.zone_key(Zone.HAND, "P0")
    before_library = tuple(state.zones[library_key])
    before_hand = tuple(state.zones[hand_key])
    executor.pass_priority("P0")

    with pytest.raises(IllegalAction, match="selected an unavailable card"):
        executor.pass_priority("P1")

    assert tuple(state.zones[library_key]) == before_library
    assert tuple(state.zones[hand_key]) == before_hand
    assert spell.object_id in state.stack
    assert not [choice for choice in state.choices if choice.kind == "CARD_SELECTION"]
