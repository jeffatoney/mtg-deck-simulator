"""Direct production evidence for canonical Dualcaster/Twinflame loop adjudication."""

from __future__ import annotations

import pytest

from mtg_deck import build_exact_game
from mtg_kernel.errors import UnsupportedCapability
from mtg_kernel.models import CopyKind, TargetRef, Zone
from mtg_kernel.strategic_choices import PublicCard, SpellCopyTargetRequest
from mtg_policy import (
    ContextualEvaluator,
    PolicyStrategicChoiceProvider,
    load_evaluator_config,
    load_policy_matrix,
)

PLAYERS = ("P0", "P1")


def pass_round(executor) -> None:
    for _ in PLAYERS:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def move_named(executor, objects, name: str, zone: Zone):
    original = next(
        obj
        for obj in objects
        if not obj.retired and obj.current_characteristics.get("name") == name
    )
    moved = executor.zones.move(
        original.object_id,
        zone,
        "TEST_SETUP",
        executor._event("TEST_SETUP", object_id=original.object_id),
        controller=original.owner if zone is Zone.BATTLEFIELD else None,
    )
    assert moved is not None
    return moved


def provider() -> PolicyStrategicChoiceProvider:
    return PolicyStrategicChoiceProvider(
        load_policy_matrix()[0], ContextualEvaluator(load_evaluator_config())
    )


def test_canonical_policy_executes_finite_visible_lethal_reserve() -> None:
    state, executor, created = build_exact_game("canonical-dualcaster", PLAYERS)
    library = list(created["library"])
    executor.bind_strategic_choice_provider(provider())
    state.turn.phase = "PRECOMBAT_MAIN"
    state.players["P1"].life = 4
    dualcaster = move_named(executor, library, "Dualcaster Mage", Zone.HAND)
    library = [obj for obj in library if not obj.retired]
    twinflame = move_named(executor, library, "Twinflame", Zone.HAND)
    malcolm = move_named(
        executor,
        list(created["command"]),
        "Malcolm, Keen-Eyed Navigator",
        Zone.BATTLEFIELD,
    )
    state.players["P0"].mana_pool.update({symbol: 0 for symbol in state.players["P0"].mana_pool})
    state.players["P0"].mana_pool["R"] = 3
    state.players["P0"].mana_pool["C"] = 3

    original = executor.cast("P0", twinflame.object_id, (TargetRef(malcolm.object_id),))
    executor.cast(
        "P0",
        dualcaster.object_id,
        choices={"trigger_targets": {"dualcaster:etb": original.object_id}},
    )
    for _ in range(30):
        if not state.stack and not state.waiting_triggers:
            break
        pass_round(executor)
    else:
        raise AssertionError("canonical bounded Dualcaster line did not terminate")

    tokens = [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.copy_kind is CopyKind.TOKEN_COPY
        and obj.current_characteristics.get("name") == "Dualcaster Mage"
    ]
    assert len(tokens) == 2
    choices = [
        choice.selected
        for choice in state.choices
        if choice.kind == "COPY_TARGETS" and isinstance(choice.selected, dict)
    ]
    strategies = [choice["diagnostics"]["strategy"] for choice in choices]
    assert strategies == [
        "CONTINUE_BOUNDED_DUALCASTER_LOOP",
        "CONTINUE_BOUNDED_DUALCASTER_LOOP",
        "STOP_BOUNDED_DUALCASTER_LOOP",
    ]
    assert all(
        choice["evaluator_id"] == "contextual_combo_v1"
        and choice["diagnostics"]["adjudicator"] == "VISIBLE_LIFE_AND_BLOCKER_RESERVE_V1"
        and choice["diagnostics"]["required_tokens"] == 2
        and choice["diagnostics"]["maximum_tokens"] == 512
        for choice in choices
    )


def test_canonical_policy_fails_closed_above_bounded_reserve() -> None:
    policy = provider()
    dualcaster = PublicCard("dual", "Dualcaster Mage", 3, ("Creature",), ("CREATE_SPELL_COPY",))
    other = PublicCard("other", "Malcolm", 3, ("Creature",), ())
    request = SpellCopyTargetRequest(
        "bounded-loop",
        "P0",
        "Dualcaster Mage",
        "Twinflame",
        3,
        {
            "player": "P0",
            "life": {"P0": 40, "P1": 1026},
            "objects": [
                {
                    "handle": "dual",
                    "zone": "BATTLEFIELD",
                    "owner": "P0",
                    "controller": "P0",
                    "identity": "Dualcaster Mage",
                    "face_down": False,
                    "card_types": ["Creature"],
                },
                {
                    "handle": "other",
                    "zone": "BATTLEFIELD",
                    "owner": "P0",
                    "controller": "P0",
                    "identity": "Malcolm",
                    "face_down": False,
                    "card_types": ["Creature"],
                },
            ],
            "turn": {"number": 3},
        },
        ("other",),
        (dualcaster, other),
        (("dual",), ("other",)),
    )
    with pytest.raises(UnsupportedCapability, match="exceeds the bounded policy limit"):
        policy.choose_spell_copy_targets(request)
