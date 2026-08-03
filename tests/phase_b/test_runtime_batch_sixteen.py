"""Direct exact-deck evidence for type and third-from-top library tutors."""

from __future__ import annotations

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import TargetRef, Zone
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
            "runtime-batch-sixteen-provider",
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


def active_names(state, zone: Zone, owner: str = "P0") -> set[str]:
    return {
        str(obj.current_characteristics.get("name", ""))
        for obj in state.objects.values()
        if not obj.retired and not obj.ceased_to_exist and obj.zone is zone and obj.owner == owner
    }


def test_invert_invent_executes_both_faces_and_type_tutor() -> None:
    invert_state, invert_executor, invert_specs = funded_game("runtime-sixteen-invert")
    creature = add_card(invert_executor, invert_specs["Spectral Sailor"], Zone.BATTLEFIELD)
    creature.current_characteristics["power"] = 2
    creature.current_characteristics["toughness"] = 5
    invert = add_card(invert_executor, invert_specs["Invert // Invent"], Zone.HAND)

    invert_executor.cast("P0", invert.object_id, (TargetRef(creature.object_id),), face=0)
    pass_all(invert_executor)

    current_creature = next(
        obj
        for obj in invert_state.objects.values()
        if not obj.retired
        and obj.zone is Zone.BATTLEFIELD
        and obj.current_characteristics.get("name") == "Spectral Sailor"
    )
    assert current_creature.current_characteristics["power"] == 5
    assert current_creature.current_characteristics["toughness"] == 2

    state, executor, specs = funded_game("runtime-sixteen-invent")
    add_card(executor, specs["Island"], Zone.LIBRARY)
    add_card(executor, specs["Opt"], Zone.LIBRARY)
    add_card(executor, specs["Twinflame"], Zone.LIBRARY)
    add_card(executor, specs["Sol Ring"], Zone.LIBRARY)
    invent = add_card(executor, specs["Invert // Invent"], Zone.HAND)
    executor.bind_strategic_choice_provider(
        NamedSelectionProvider(
            {
                "TUTOR_INSTANT": ("Opt",),
                "TUTOR_SORCERY": ("Twinflame",),
            }
        )
    )

    executor.cast("P0", invent.object_id, face=1)
    pass_all(executor)

    hand_names = active_names(state, Zone.HAND)
    assert {"Opt", "Twinflame"} <= hand_names
    assert active_names(state, Zone.LIBRARY) == {"Island", "Sol Ring"}
    selections = [choice for choice in state.choices if choice.kind == "CARD_SELECTION"]
    assert [choice.selected["purpose"] for choice in selections] == [
        "TUTOR_INSTANT",
        "TUTOR_SORCERY",
    ]
    assert all(choice.selected["chosen_at"] == "RESOLUTION" for choice in selections)
    assert any(event.kind == "LIBRARY_SHUFFLED" for event in state.events)


def test_long_term_plans_places_selected_card_third_from_top() -> None:
    state, executor, specs = funded_game("runtime-sixteen-long-term-plans")
    for name in ("Mountain", "Island", "Opt", "Sol Ring", "Twinflame"):
        add_card(executor, specs[name], Zone.LIBRARY)
    selected = next(
        obj
        for obj in state.objects.values()
        if obj.zone is Zone.LIBRARY and obj.current_characteristics.get("name") == "Opt"
    )
    spell = add_card(executor, specs["Long-Term Plans"], Zone.HAND)
    executor.bind_strategic_choice_provider(
        NamedSelectionProvider({"TUTOR_THIRD_FROM_TOP": ("Opt",)})
    )

    executor.cast("P0", spell.object_id)
    pass_all(executor)

    library_key = executor.zones.zone_key(Zone.LIBRARY, "P0")
    library = state.zones[library_key]
    assert library[-3] == selected.object_id
    assert state.objects[selected.object_id].zone is Zone.LIBRARY
    selection = next(
        choice
        for choice in state.choices
        if choice.kind == "CARD_SELECTION" and choice.selected["purpose"] == "TUTOR_THIRD_FROM_TOP"
    )
    assert len(selection.selected["selected_handles"]) == 1
    assert selection.selected["chosen_at"] == "RESOLUTION"
    assert any(event.kind == "LIBRARY_SHUFFLED" for event in state.events)
    assert any(event.kind == "SEARCH_CARD_PUT_THIRD_FROM_TOP" for event in state.events)
