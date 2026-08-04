"""Direct production-path evidence for Chart a Course conditional discard."""

from __future__ import annotations

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import Zone
from mtg_kernel.strategic_choices import CardSelection, CardSelectionRequest

PLAYERS = ("P0", "P1")
MANA_SYMBOLS = ("W", "U", "B", "R", "G", "C")


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
            "runtime-batch-twenty-four-provider",
            "0" * 64,
            {"purpose": request.purpose},
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


def active_zone_names(state, zone: Zone, owner: str = "P0") -> list[str]:
    return sorted(
        str(obj.current_characteristics.get("name", ""))
        for obj in state.objects.values()
        if not obj.retired
        and not obj.ceased_to_exist
        and obj.zone is zone
        and obj.owner == owner
    )


def test_chart_a_course_draws_two_then_discards_when_controller_did_not_attack() -> None:
    state, executor, specs = game_with_exact_mana("runtime-twenty-four-no-attack")
    state.players["P0"].mana_pool.update({"U": 1, "C": 1})
    add_card(executor, specs["Island"], Zone.LIBRARY)
    add_card(executor, specs["Mountain"], Zone.LIBRARY)
    discard = add_card(executor, specs["Opt"], Zone.HAND)
    chart = add_card(executor, specs["Chart a Course"], Zone.HAND)
    executor.bind_strategic_choice_provider(NamedSelectionProvider({"DISCARD": ("Opt",)}))

    executor.cast("P0", chart.object_id)
    pass_all(executor)

    assert active_zone_names(state, Zone.HAND) == ["Island", "Mountain"]
    assert discard.retired
    assert active_zone_names(state, Zone.GRAVEYARD) == ["Chart a Course", "Opt"]
    selections = [choice for choice in state.choices if choice.kind == "CARD_SELECTION"]
    assert len(selections) == 1
    assert selections[0].selected["purpose"] == "DISCARD"
    assert len(selections[0].selected["selected_handles"]) == 1
    assert sum(event.kind == "CARD_DRAWN" for event in state.events) == 2
    assert sum(event.kind == "CARD_DISCARDED" for event in state.events) == 1


def test_chart_a_course_draws_two_without_discard_after_attack_marker() -> None:
    state, executor, specs = game_with_exact_mana("runtime-twenty-four-attacked")
    state.players["P0"].mana_pool.update({"U": 1, "C": 1})
    attacker = add_card(executor, specs["Glint-Horn Buccaneer"], Zone.BATTLEFIELD)
    attacker.current_characteristics["attacking"] = True
    add_card(executor, specs["Island"], Zone.LIBRARY)
    add_card(executor, specs["Mountain"], Zone.LIBRARY)
    chart = add_card(executor, specs["Chart a Course"], Zone.HAND)
    executor.bind_strategic_choice_provider(NamedSelectionProvider({"DISCARD": ()}))

    executor.cast("P0", chart.object_id)
    pass_all(executor)

    assert active_zone_names(state, Zone.HAND) == ["Island", "Mountain"]
    assert active_zone_names(state, Zone.GRAVEYARD) == ["Chart a Course"]
    selections = [choice for choice in state.choices if choice.kind == "CARD_SELECTION"]
    assert len(selections) == 1
    assert selections[0].selected["purpose"] == "DISCARD"
    assert selections[0].selected["selected_handles"] == []
    assert sum(event.kind == "CARD_DRAWN" for event in state.events) == 2
    assert not any(event.kind == "CARD_DISCARDED" for event in state.events)


def test_chart_a_course_missing_discard_provider_fails_closed_atomically() -> None:
    state, executor, specs = game_with_exact_mana("runtime-twenty-four-missing-provider")
    state.players["P0"].mana_pool.update({"U": 1, "C": 1})
    add_card(executor, specs["Island"], Zone.LIBRARY)
    add_card(executor, specs["Mountain"], Zone.LIBRARY)
    add_card(executor, specs["Opt"], Zone.HAND)
    chart = add_card(executor, specs["Chart a Course"], Zone.HAND)

    spell = executor.cast("P0", chart.object_id)
    library_key = executor.zones.zone_key(Zone.LIBRARY, "P0")
    hand_key = executor.zones.zone_key(Zone.HAND, "P0")
    before_library = tuple(state.zones[library_key])
    before_hand = tuple(state.zones[hand_key])
    executor.pass_priority("P0")

    with pytest.raises(IllegalAction, match="discard selection requires an injected"):
        executor.pass_priority("P1")

    assert tuple(state.zones[library_key]) == before_library
    assert tuple(state.zones[hand_key]) == before_hand
    assert spell.object_id in state.stack
    assert not [choice for choice in state.choices if choice.kind == "CARD_SELECTION"]
