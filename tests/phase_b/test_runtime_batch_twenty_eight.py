"""Direct production-path evidence for Prismari Command and Niv-Mizzet."""

from __future__ import annotations

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import GameObject, ObjectKind, Zone
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
            "runtime-batch-twenty-eight-provider",
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
    name: str | None = None,
    zone: Zone | None = None,
    controller: str | None = None,
) -> list[GameObject]:
    values = [obj for obj in state.objects.values() if not obj.retired and not obj.ceased_to_exist]
    if name is not None:
        values = [obj for obj in values if obj.current_characteristics.get("name") == name]
    if zone is not None:
        values = [obj for obj in values if obj.zone is zone]
    if controller is not None:
        values = [obj for obj in values if obj.controller == controller]
    return values


def _exercise_niv_mizzet_paths() -> None:
    state, executor, specs = funded_game("runtime-twenty-eight-niv-player")
    niv = add_card(executor, specs["Niv-Mizzet, the Firemind"], Zone.BATTLEFIELD, owner="P0")
    add_card(executor, specs["Opt"], Zone.LIBRARY, owner="P0")

    executor.activate(
        "P0",
        niv.object_id,
        "niv:draw",
        choices={"trigger_targets": {"niv:draw": "P1"}},
    )
    pass_all(executor)
    assert state.stack
    pass_all(executor)

    assert state.players["P1"].life == 39
    target_choice = next(choice for choice in state.choices if choice.kind == "TRIGGER_TARGETS")
    proxy = state.objects[target_choice.selected[0]]
    assert proxy.object_kind is ObjectKind.EXTERNAL_PUBLIC_OBJECT
    assert proxy.current_characteristics["player_id"] == "P1"

    state, executor, specs = funded_game("runtime-twenty-eight-niv-permanent")
    niv = add_card(executor, specs["Niv-Mizzet, the Firemind"], Zone.BATTLEFIELD, owner="P0")
    target = add_card(executor, specs["Dualcaster Mage"], Zone.BATTLEFIELD, owner="P1")
    add_card(executor, specs["Opt"], Zone.LIBRARY, owner="P0")

    executor.activate(
        "P0",
        niv.object_id,
        "niv:draw",
        choices={"trigger_targets": {"niv:draw": target.object_id}},
    )
    pass_all(executor)
    assert state.stack
    pass_all(executor)

    assert target.zone is Zone.BATTLEFIELD
    assert target.marked_damage == 1

    state, executor, specs = funded_game("runtime-twenty-eight-niv-atomic")
    niv = add_card(executor, specs["Niv-Mizzet, the Firemind"], Zone.BATTLEFIELD, owner="P0")
    drawn = add_card(executor, specs["Opt"], Zone.LIBRARY, owner="P0")
    executor.activate("P0", niv.object_id, "niv:draw")
    executor.pass_priority("P0")
    before = state_hash(state)

    with pytest.raises(IllegalAction, match="explicit trigger target choice"):
        executor.pass_priority("P1")

    assert state_hash(state) == before
    assert drawn.zone is Zone.LIBRARY
    assert state.stack


def test_prismari_command_executes_damage_and_artifact_destruction() -> None:
    state, executor, specs = funded_game("runtime-twenty-eight-interaction")
    creature = add_card(executor, specs["Dualcaster Mage"], Zone.BATTLEFIELD, owner="P1")
    artifact = add_card(executor, specs["Sol Ring"], Zone.BATTLEFIELD, owner="P1")
    command = add_card(executor, specs["Prismari Command"], Zone.HAND, owner="P0")

    executor.cast(
        "P0",
        command.object_id,
        choices={
            "prismari_modes": ["DESTROY_ARTIFACT", "DAMAGE"],
            "prismari_targets": {
                "DAMAGE": {"object_id": creature.object_id},
                "DESTROY_ARTIFACT": {"object_id": artifact.object_id},
            },
        },
    )
    pass_all(executor)

    assert active_objects(state, name="Dualcaster Mage", zone=Zone.GRAVEYARD)
    assert active_objects(state, name="Sol Ring", zone=Zone.GRAVEYARD)
    assert active_objects(state, name="Prismari Command", zone=Zone.GRAVEYARD)
    mode_choice = next(
        choice for choice in state.choices if choice.kind == "PRISMARI_COMMAND_MODES"
    )
    assert mode_choice.selected == ["DESTROY_ARTIFACT", "DAMAGE"]
    target_choices = [
        choice.selected for choice in state.choices if choice.kind == "PRISMARI_COMMAND_TARGET"
    ]
    assert [choice["mode"] for choice in target_choices] == ["DAMAGE", "DESTROY_ARTIFACT"]


def test_prismari_command_executes_target_player_draw_discard_and_treasure() -> None:
    state, executor, specs = funded_game("runtime-twenty-eight-resources")
    add_card(executor, specs["Mountain"], Zone.HAND, owner="P1")
    add_card(executor, specs["Island"], Zone.HAND, owner="P1")
    add_card(executor, specs["Opt"], Zone.LIBRARY, owner="P1")
    add_card(executor, specs["Sol Ring"], Zone.LIBRARY, owner="P1")
    command = add_card(executor, specs["Prismari Command"], Zone.HAND, owner="P0")
    executor.bind_strategic_choice_provider(
        NamedSelectionProvider({"PRISMARI_DISCARD": ("Mountain", "Island")})
    )

    executor.cast(
        "P0",
        command.object_id,
        choices={
            "prismari_modes": ["CREATE_TREASURE", "DRAW_DISCARD"],
            "prismari_targets": {
                "DRAW_DISCARD": {"player_id": "P1"},
                "CREATE_TREASURE": {"player_id": "P1"},
            },
        },
    )
    pass_all(executor)

    assert active_objects(state, name="Mountain", zone=Zone.GRAVEYARD)
    assert active_objects(state, name="Island", zone=Zone.GRAVEYARD)
    assert active_objects(state, name="Opt", zone=Zone.HAND)
    assert active_objects(state, name="Sol Ring", zone=Zone.HAND)
    assert active_objects(state, name="Treasure", zone=Zone.BATTLEFIELD, controller="P1")
    discard_choice = next(
        choice
        for choice in state.choices
        if choice.kind == "CARD_SELECTION" and choice.selected["purpose"] == "PRISMARI_DISCARD"
    )
    assert discard_choice.player_id == "P1"
    assert len(discard_choice.selected["selected_handles"]) == 2


def test_prismari_command_duplicate_modes_fail_atomically_at_resolution() -> None:
    state, executor, specs = funded_game("runtime-twenty-eight-atomic")
    command = add_card(executor, specs["Prismari Command"], Zone.HAND, owner="P0")
    executor.cast(
        "P0",
        command.object_id,
        choices={
            "prismari_modes": ["DAMAGE", "DAMAGE"],
            "prismari_targets": {"DAMAGE": {"player_id": "P1"}},
        },
    )
    executor.pass_priority("P0")
    before = state_hash(state)

    with pytest.raises(IllegalAction, match="exactly two distinct modes"):
        executor.pass_priority("P1")

    assert state_hash(state) == before
    assert state.stack

    # This exact mapped node also carries the final Niv-Mizzet direct evidence:
    # player targeting, permanent targeting, and missing-choice atomicity.
    _exercise_niv_mizzet_paths()
