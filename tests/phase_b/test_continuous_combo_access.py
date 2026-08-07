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


def test_every_frozen_combo_package_has_an_execution_detector() -> None:
    _state, executor, tracker = scenario(3, mana={"R": 3, "C": 2})
    records = tracker.observe(executor)
    assert {record.package for record in records} == set(load_evaluator_config().combo_packages)
    assert all("PACKAGE_EXECUTION_DETECTOR_UNIMPLEMENTED" not in record.blockers for record in records)


def test_dualcaster_access_requires_main_phase_and_leaves_real_protection_mana() -> None:
    state, executor, tracker = scenario(3, mana={"R": 3, "C": 3, "U": 1})
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    add_card(executor, specs["Arcane Denial"], Zone.HAND)

    snapshot = next(
        record for record in tracker.observe(executor) if record.package == "dualcaster_twinflame"
    )
    assert snapshot.legally_executable is True
    assert snapshot.usable_protection is True

    state.turn.phase = "COMBAT"
    state.turn.step = "DECLARE_ATTACKERS"
    snapshot = next(
        record for record in tracker.observe(executor) if record.package == "dualcaster_twinflame"
    )
    assert snapshot.legally_executable is False
    assert "SORCERY_TIMING_UNAVAILABLE" in snapshot.blockers


def test_malcolm_glint_horn_access_respects_attack_window_and_discard_requirement() -> None:
    state, executor = new_game(("P0", "P1", "P2", "P3"), seed="glint-access")
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    state.turn.number = 3
    state.turn.phase = "PRECOMBAT_MAIN"
    state.turn.step = "PRECOMBAT_MAIN"
    state.turn.active_player_id = "P0"
    state.turn.priority_holder_id = "P0"
    state.players["P0"].mana_pool.update({"R": 1, "C": 1})
    add_card(executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD)
    add_card(executor, specs["Glint-Horn Buccaneer"], Zone.BATTLEFIELD)
    add_card(executor, specs["Island"], Zone.HAND)
    tracker = bind_combo_access_tracker(executor, "P0", load_evaluator_config().combo_packages)

    precombat = next(
        record for record in tracker.observe(executor) if record.package == "malcolm_glint_horn"
    )
    assert precombat.legally_executable is True

    state.turn.phase = "POSTCOMBAT_MAIN"
    state.turn.step = "POSTCOMBAT_MAIN"
    postcombat = next(
        record for record in tracker.observe(executor) if record.package == "malcolm_glint_horn"
    )
    assert postcombat.legally_executable is False
    assert "GLINT_HORN_CANNOT_ATTACK_OR_IS_NOT_ATTACKING" in postcombat.blockers


def test_lightning_rig_combo_requires_exact_aura_attachment_and_ready_crew() -> None:
    from mtg_kernel.models import TargetRef

    state, executor = new_game(("P0", "P1", "P2", "P3"), seed="crew-access")
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    state.turn.number = 3
    state.turn.phase = "PRECOMBAT_MAIN"
    state.turn.step = "PRECOMBAT_MAIN"
    state.turn.active_player_id = "P0"
    state.turn.priority_holder_id = "P0"
    add_card(executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD)
    crew = add_card(executor, specs["Lightning-Rig Crew"], Zone.BATTLEFIELD)
    aura = add_card(executor, specs["Crab Umbra"], Zone.BATTLEFIELD)
    assert crew.permanent_status is not None
    crew.permanent_status["controller_since_turn"] = "3"
    tracker = bind_combo_access_tracker(executor, "P0", load_evaluator_config().combo_packages)

    sick = next(
        record
        for record in tracker.observe(executor)
        if record.package == "lightning_rig_crab_umbra_malcolm"
    )
    assert sick.legally_executable is False
    assert "LIGHTNING_RIG_CREW_CANNOT_TAP" in sick.blockers
    assert "CRAB_UMBRA_NOT_ATTACHED_TO_CREW" in sick.blockers

    aura.attached_to_ref = TargetRef(crew.object_id)
    crew.permanent_status["controller_since_turn"] = "2"
    ready = next(
        record
        for record in tracker.observe(executor)
        if record.package == "lightning_rig_crab_umbra_malcolm"
    )
    assert ready.legally_executable is True


def test_niv_curiosity_requires_ready_niv_and_castable_or_attached_curiosity() -> None:
    state, executor = new_game(("P0", "P1", "P2", "P3"), seed="niv-access")
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    state.turn.number = 4
    state.turn.phase = "PRECOMBAT_MAIN"
    state.turn.step = "PRECOMBAT_MAIN"
    state.turn.active_player_id = "P0"
    state.turn.priority_holder_id = "P0"
    state.players["P0"].mana_pool["U"] = 1
    niv = add_card(executor, specs["Niv-Mizzet, the Firemind"], Zone.BATTLEFIELD)
    add_card(executor, specs["Curiosity"], Zone.HAND)
    assert niv.permanent_status is not None
    niv.permanent_status["controller_since_turn"] = "4"
    tracker = bind_combo_access_tracker(executor, "P0", load_evaluator_config().combo_packages)

    sick = next(
        record for record in tracker.observe(executor) if record.package == "niv_mizzet_curiosity"
    )
    assert sick.legally_executable is False
    assert "NIV_MIZZET_CANNOT_TAP" in sick.blockers

    niv.permanent_status["controller_since_turn"] = "3"
    ready = next(
        record for record in tracker.observe(executor) if record.package == "niv_mizzet_curiosity"
    )
    assert ready.legally_executable is True
