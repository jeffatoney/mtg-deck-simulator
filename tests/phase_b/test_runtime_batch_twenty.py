"""Direct production-path evidence for Reality Ripple and phasing."""

from __future__ import annotations

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import TargetRef, Zone

PLAYERS = ("P0", "P1")


def game_with_exact_mana(seed: str):
    state, executor = new_game(PLAYERS, seed)
    for player in state.players.values():
        player.mana_pool.update({symbol: 0 for symbol in ("W", "U", "B", "R", "G", "C")})
    state.players["P0"].mana_pool["U"] = 3
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    return state, executor, specs


def pass_all(executor) -> None:
    for _ in PLAYERS:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def test_reality_ripple_phases_target_and_attachments_without_changing_zones() -> None:
    state, executor, specs = game_with_exact_mana("runtime-twenty-reality-ripple")
    target = add_card(executor, specs["Wily Goblin"], Zone.BATTLEFIELD, owner="P1")
    aura = add_card(executor, specs["Crab Umbra"], Zone.BATTLEFIELD, owner="P0")
    aura.attached_to_ref = TargetRef(target.object_id)
    ripple = add_card(executor, specs["Reality Ripple"], Zone.HAND, owner="P0")

    executor.cast("P0", ripple.object_id, targets=(TargetRef(target.object_id),))
    pass_all(executor)

    assert state.objects[target.object_id] is target
    assert state.objects[aura.object_id] is aura
    assert target.zone is Zone.BATTLEFIELD and not target.retired
    assert aura.zone is Zone.BATTLEFIELD and not aura.retired
    assert target.permanent_status is not None
    assert aura.permanent_status is not None
    assert target.permanent_status["phase"] == "PHASED_OUT"
    assert aura.permanent_status["phase"] == "PHASED_OUT"
    assert aura.current_characteristics["phased_out_with"] == target.object_id
    assert not executor._target_matches("P0", target, "CREATURE")
    assert not executor._target_matches("P0", aura, "PERMANENT")

    phase_events = [event for event in state.events if event.kind == "PERMANENT_PHASED_OUT"]
    assert [(event.payload["object_id"], event.payload["indirect"]) for event in phase_events] == [
        (target.object_id, False),
        (aura.object_id, True),
    ]


def test_indirectly_phased_attachment_returns_with_target_not_its_controller() -> None:
    state, executor, specs = game_with_exact_mana("runtime-twenty-indirect-phasing")
    target = add_card(executor, specs["Wily Goblin"], Zone.BATTLEFIELD, owner="P1")
    aura = add_card(executor, specs["Crab Umbra"], Zone.BATTLEFIELD, owner="P0")
    aura.attached_to_ref = TargetRef(target.object_id)
    ripple = add_card(executor, specs["Reality Ripple"], Zone.HAND, owner="P0")

    executor.cast("P0", ripple.object_id, targets=(TargetRef(target.object_id),))
    pass_all(executor)

    executor.begin_step("UNTAP")
    assert target.permanent_status is not None
    assert aura.permanent_status is not None
    assert target.permanent_status["phase"] == "PHASED_OUT"
    assert aura.permanent_status["phase"] == "PHASED_OUT"

    state.turn.active_player_id = "P1"
    state.turn.priority_holder_id = "P1"
    executor.begin_step("UNTAP")
    assert target.permanent_status["phase"] == "PHASED_IN"
    assert aura.permanent_status["phase"] == "PHASED_IN"
    assert "phased_out_with" not in aura.current_characteristics
    assert executor._target_matches("P0", target, "CREATURE")
    assert executor._target_matches("P0", aura, "PERMANENT")
