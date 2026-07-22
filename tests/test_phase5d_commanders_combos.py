from __future__ import annotations

import pytest

from mtg_sim.engine import (
    GameState,
    Permanent,
    RulesError,
    activate_crab_umbra_untap,
    activate_glint_horn,
    activate_lightning_rig_crew,
    activate_niv_mizzet_draw,
    cast_dualcaster_mage,
    cast_twinflame,
    curiosity_trigger,
    pirate_damage_event,
    psychosis_crawler_draw_trigger,
    run_glint_horn_iterations,
)


def pool(c=0, u=0, r=0):
    return {"C": c, "U": u, "R": r, "W": 0, "B": 0, "G": 0}


def pirate(name="Pirate", **kw):
    return Permanent(name, {"Creature"}, {"Pirate"}, **kw)


def test_malcolm_recalculates_unique_actual_opponents_per_event_and_breeches_is_not_resource():
    s = GameState(opponent_life=[40, 0, 40])
    p1, p2 = pirate(), pirate()
    assert pirate_damage_event(s, [(p1, 0, 1), (p2, 0, 1), (p1, 1, 1), (p2, 2, 1)]) == 2
    assert s.treasures == 2
    assert s.opponent_life == [38, 0, 39]
    assert "breeches_trigger:unknown_opponent_cards_exiled:2:not_deterministic" in s.event_log
    assert not s.hand
    assert pirate_damage_event(s, [(p1, 2, 1)], prevented_opponents={2}) == 0
    assert s.treasures == 2


def test_glint_horn_finishes_without_final_draw_and_stops_finite_resources():
    s = GameState(library=[], hand=["discard"], opponent_life=[1, 1, 1], mana_pool=pool(c=1, r=1))
    assert run_glint_horn_iterations(s, pirate("Glint-Horn Buccaneer", attacking=True), 10) == 1
    assert s.won and not s.lost and "resolve:Glint-Horn draw ability" not in s.event_log
    s2 = GameState(hand=[], mana_pool=pool(c=1, r=1))
    assert run_glint_horn_iterations(s2, pirate("Glint-Horn Buccaneer", attacking=True), 10) == 0


def test_glint_horn_opponent_dependent_treasure_rates():
    for lives, expected in [([40, 40, 40], 1), ([40, 40, 0], 0), ([40, 0, 0], -1)]:
        gh = pirate("Glint-Horn Buccaneer", attacking=True)
        s = GameState(
            library=["draw"],
            hand=["discard"],
            opponent_life=lives,
            mana_pool=pool(c=1, r=1),
            battlefield=[gh],
        )
        before = s.treasures + sum(s.mana_pool.values())
        activate_glint_horn(s, gh)
        s.resolve_all()
        assert s.treasures + sum(s.mana_pool.values()) - before == expected


def test_dualcaster_requires_copy_spell_first_and_copied_spell_not_cast():
    target = Permanent("Siren", {"Creature"})
    s = GameState(battlefield=[target])
    with pytest.raises(RulesError):
        cast_dualcaster_mage(GameState(battlefield=[target]))
    cast_twinflame(s, target)
    dualcaster = cast_dualcaster_mage(s)
    assert s.stack[-1].targets == [dualcaster]
    assert s.stack[-1].cast is False


def test_curiosity_optional_empty_library_and_psychosis_is_life_loss_not_damage():
    s = GameState(library=[])
    curiosity_trigger(s, decline=True)
    s.resolve_all()
    assert not s.lost
    s2 = GameState(opponent_life=[2, 2, 2])
    psychosis_crawler_draw_trigger(s2)
    s2.resolve_all()
    assert s2.opponent_life == [1, 1, 1]
    assert s2.treasures == 0
    assert not any(e.startswith("noncombat_damage") for e in s2.event_log)


def test_niv_mizzet_tap_draw_respects_summoning_sickness():
    niv = Permanent("Niv-Mizzet, the Firemind", {"Creature"}, {"Dragon", "Wizard"})
    with pytest.raises(RulesError):
        activate_niv_mizzet_draw(GameState(battlefield=[niv]), niv)
    niv.summoning_sick = False
    s = GameState(library=["card"], battlefield=[niv])
    activate_niv_mizzet_draw(s, niv)
    s.resolve_all()
    assert s.hand == ["card"] and niv.tapped


def test_lightning_rig_crew_crab_umbra_tracks_untap_cost_treasures_and_life_totals():
    crew = Permanent("Lightning-Rig Crew", {"Creature"}, {"Goblin", "Pirate"}, summoning_sick=False)
    s = GameState(opponent_life=[2, 2, 1], battlefield=[crew], mana_pool=pool(c=2, u=1))
    activate_lightning_rig_crew(s, crew)
    s.resolve_all()
    assert s.opponent_life == [1, 1, 0] and s.treasures == 3 and crew.tapped
    activate_crab_umbra_untap(s, crew)
    s.resolve_all()
    assert not crew.tapped and sum(s.mana_pool.values()) == 0


def test_cleanup_step_multiple_glint_horn_discards_create_additional_cleanup_steps():
    s = GameState(library=["a", "b"], hand=["x", "y"], mana_pool=pool(c=2, r=2))
    gh = pirate("Glint-Horn Buccaneer", attacking=True)
    activate_glint_horn(s, gh)
    activate_glint_horn(s, gh)
    s.resolve_all()
    assert s.cleanup_steps == 0
    assert s.cards_drawn == 2
