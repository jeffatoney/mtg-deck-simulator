from __future__ import annotations

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import Zone
from mtg_measure import bind_combo_access_tracker
from mtg_policy import ActionBroker, load_evaluator_config


def scenario(turn: int, *, mana: dict[str, int]):
    state, executor = new_game(("P0", "P1", "P2", "P3"), seed=f"combo-access-{turn}")
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    state.turn.number = turn
    state.turn.phase = "PRECOMBAT_MAIN"
    state.turn.step = "PRECOMBAT_MAIN"
    state.turn.active_player_id = "P0"
    state.turn.priority_holder_id = "P0"
    state.players["P0"].mana_pool.update({symbol: 0 for symbol in ("W", "U", "B", "R", "G", "C")})
    state.players["P0"].mana_pool.update(mana)
    add_card(executor, specs["Dualcaster Mage"], Zone.HAND)
    add_card(executor, specs["Twinflame"], Zone.HAND)
    add_card(executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD)
    tracker = bind_combo_access_tracker(executor, "P0", load_evaluator_config().combo_packages)
    return state, executor, tracker


def test_turn_three_combo_is_detected_before_turn_five_checkpoint() -> None:
    _state, executor, tracker = scenario(3, mana={"R": 3, "C": 2})
    ActionBroker(executor, "P0").refresh()
    assert tracker.earliest_legal_turn("dualcaster_twinflame") == 3
    assert tracker.cumulative_checkpoint_access("dualcaster_twinflame") == {
        5: True,
        6: True,
        8: True,
        10: True,
    }


def test_turn_four_access_is_recorded_when_turn_three_mana_was_short() -> None:
    state, executor, tracker = scenario(3, mana={"R": 2, "C": 2})
    ActionBroker(executor, "P0").refresh()
    assert tracker.earliest_legal_turn("dualcaster_twinflame") is None
    state.turn.number = 4
    state.players["P0"].mana_pool["R"] = 3
    state.players["P0"].mana_pool["C"] = 2
    ActionBroker(executor, "P0").refresh()
    assert tracker.earliest_legal_turn("dualcaster_twinflame") == 4
    assert tracker.cumulative_checkpoint_access("dualcaster_twinflame")[5] is True


def test_detector_fails_closed_for_packages_without_execution_logic() -> None:
    _state, executor, tracker = scenario(3, mana={"R": 3, "C": 2})
    records = tracker.observe(executor)
    unsupported = next(record for record in records if record.package == "malcolm_glint_horn")
    assert unsupported.legally_executable is False
    assert unsupported.blockers == ("PACKAGE_EXECUTION_DETECTOR_UNIMPLEMENTED",)
