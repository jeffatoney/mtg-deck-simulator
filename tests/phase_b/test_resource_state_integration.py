from __future__ import annotations

from copy import deepcopy

from mtg_kernel.engine import GameExecutor
from mtg_kernel.models import GameObject, GameState, ObjectKind, PlayerState, TurnState, Zone
from mtg_kernel.resource_payment import PaymentStep, PaymentWindow
from mtg_kernel.resource_sources import solve_state_payment
from mtg_measure.combo_access import ComboAccessTracker


def _permanent(
    object_id: str,
    name: str,
    *,
    kind: ObjectKind = ObjectKind.PERMANENT,
    card_types: tuple[str, ...] = (),
    subtypes: tuple[str, ...] = (),
    attacking: bool = False,
) -> GameObject:
    return GameObject(
        object_id=object_id,
        object_kind=kind,
        zone=Zone.BATTLEFIELD,
        owner="P0",
        controller="P0",
        current_characteristics={
            "name": name,
            "card_types": list(card_types),
            "subtypes": list(subtypes),
            "keywords": ["Haste"] if name == "Glint-Horn Buccaneer" else [],
            "attacking": attacking,
            "abilities": [],
        },
        permanent_status={"tap": "UNTAPPED", "controller_since_turn": "1"},
    )


def _malcolm_glint_fixture(*, treasure_object_id: str = "treasure-object") -> GameState:
    players = {
        "P0": PlayerState("P0", mana_pool={"W": 0, "U": 0, "B": 0, "R": 1, "G": 0, "C": 0}),
        "P1": PlayerState("P1", life=1),
        "P2": PlayerState("P2", life=1),
        "P3": PlayerState("P3", life=1),
    }
    state = GameState(
        game_id="stage2-malcolm-glint",
        players=players,
        turn=TurnState(
            active_player_id="P0",
            number=4,
            phase="PRECOMBAT_MAIN",
            step="PRECOMBAT_MAIN",
            priority_holder_id="P0",
        ),
    )
    malcolm = _permanent(
        "malcolm-object",
        "Malcolm, Keen-Eyed Navigator",
        card_types=("Creature",),
    )
    glint = _permanent(
        "glint-object",
        "Glint-Horn Buccaneer",
        card_types=("Creature",),
        attacking=True,
    )
    treasure = _permanent(
        treasure_object_id,
        "Treasure",
        kind=ObjectKind.TOKEN_OBJECT,
        card_types=("Artifact",),
        subtypes=("Treasure",),
    )
    discard = GameObject(
        object_id="discard-object",
        object_kind=ObjectKind.CARD_IN_ZONE,
        zone=Zone.HAND,
        owner="P0",
        controller=None,
        current_characteristics={"name": "Fixture Discard"},
    )
    state.objects = {
        malcolm.object_id: malcolm,
        glint.object_id: glint,
        treasure.object_id: treasure,
        discard.object_id: discard,
    }
    state.zones = {
        "BATTLEFIELD:shared": [malcolm.object_id, glint.object_id, treasure.object_id],
        "HAND:P0": [discard.object_id],
        "LIBRARY:P0": [],
    }
    return state


def _activation_step() -> PaymentStep:
    return PaymentStep(
        label="glint-horn-activation",
        mana_cost="{1}{R}",
        window=PaymentWindow(0, "current-main"),
        context_tags=("ACTIVATED_ABILITY",),
    )


def test_state_payment_uses_floating_red_and_one_treasure_once() -> None:
    state = _malcolm_glint_fixture()
    result = solve_state_payment(state, "P0", (_activation_step(),))
    assert result.feasible is True
    assert sum(item.amount for item in result.canonical_allocation) == 2
    assert {item.source_semantic_id for item in result.canonical_allocation} == {
        "floating:R",
        "Treasure:treasure-mana",
    }


def test_state_payment_public_result_ignores_hidden_object_identity_and_library_order() -> None:
    first = _malcolm_glint_fixture(treasure_object_id="opaque-treasure-a")
    second = _malcolm_glint_fixture(treasure_object_id="opaque-treasure-b")
    first.zones["LIBRARY:P0"] = ["hidden-a", "hidden-b"]
    second.zones["LIBRARY:P0"] = ["hidden-b", "hidden-a"]
    assert solve_state_payment(first, "P0", (_activation_step(),)) == solve_state_payment(
        second, "P0", (_activation_step(),)
    )


def test_malcolm_glint_horn_treasure_contradiction_is_eliminated() -> None:
    state = _malcolm_glint_fixture()
    payment = solve_state_payment(state, "P0", (_activation_step(),))
    executor = GameExecutor(deepcopy(state), seed="stage2-resource-fixture")
    tracker = ComboAccessTracker(
        "P0",
        {
            "malcolm_glint_horn": (
                "Malcolm, Keen-Eyed Navigator",
                "Glint-Horn Buccaneer",
            )
        },
    )
    snapshot = tracker.observe(executor)[0]
    assert payment.feasible is True
    assert snapshot.pieces_assembled is True
    assert snapshot.sufficient_mana is payment.feasible
    assert snapshot.legally_executable is payment.feasible
    assert snapshot.full_table_kill is True
    assert snapshot.blockers == ()
