from __future__ import annotations

import pytest

from mtg_sim.engine import (
    GameState,
    Permanent,
    Phase,
    RulesError,
    activate_glint_horn,
    cast_commander,
    cast_dualcaster_mage,
    cast_split_card,
    cast_twinflame,
    cleanup_step,
    curiosity_trigger,
    deal_pirate_combat_damage,
    flashback_electroduplicate,
    long_term_plans,
    play_land,
    shuffled_library,
    tap_for_mana,
    transmute,
    use_single_tutor_for_combo_halves,
    wizardcycle,
)


def pirate(name="Pirate"):
    return Permanent(name, {"Creature"}, {"Pirate"}, attacking=True)


def test_malcolm_one_pirate_damages_three_opponents_creates_three_treasures():
    s = GameState()
    assert deal_pirate_combat_damage(s, [pirate(), pirate(), pirate()], [0, 1, 2]) == 3
    assert s.treasures == 3


def test_two_pirates_same_opponent_simultaneously_create_one_treasure():
    s = GameState()
    assert deal_pirate_combat_damage(s, [pirate(), pirate()], [0, 0]) == 1


def test_prevented_damage_creates_no_treasure():
    s = GameState()
    p = pirate()
    p.damage_prevented = True
    assert deal_pirate_combat_damage(s, [p], [0]) == 0


def test_glint_horn_cannot_activate_unless_attacking():
    s = GameState(hand=["discard"], mana_pool={"C": 1, "U": 0, "R": 1, "W": 0, "B": 0, "G": 0})
    with pytest.raises(RulesError):
        activate_glint_horn(s, Permanent("Glint-Horn Buccaneer", {"Creature"}, {"Pirate"}))


def test_glint_horn_need_not_deal_combat_damage():
    s = GameState(hand=["discard"], mana_pool={"C": 1, "U": 0, "R": 1, "W": 0, "B": 0, "G": 0})
    activate_glint_horn(
        s, Permanent("Glint-Horn Buccaneer", {"Creature"}, {"Pirate"}, attacking=True)
    )
    assert [o.name for o in s.stack] == [
        "Glint-Horn draw ability",
        "Glint-Horn discard damage trigger",
    ]


def test_glint_horn_damage_trigger_resolves_before_draw_ability():
    s = GameState(
        library=["card"],
        hand=["discard"],
        mana_pool={"C": 1, "U": 0, "R": 1, "W": 0, "B": 0, "G": 0},
    )
    activate_glint_horn(s, pirate("Glint-Horn Buccaneer"))
    s.resolve_top()
    assert "glint_horn_discard_damage" in s.event_log and s.cards_drawn == 0


def test_lethal_glint_horn_damage_ends_before_final_mandatory_draw():
    s = GameState(
        library=[],
        hand=["discard"],
        opponent_life=[1, 1, 1],
        mana_pool={"C": 1, "U": 0, "R": 1, "W": 0, "B": 0, "G": 0},
    )
    activate_glint_horn(s, pirate("Glint-Horn Buccaneer"))
    s.resolve_all()
    assert s.won and not s.lost and s.cards_drawn == 0 and not s.stack


def test_nonlethal_mandatory_draw_from_empty_library_causes_loss():
    s = GameState(
        library=[], hand=["discard"], mana_pool={"C": 1, "U": 0, "R": 1, "W": 0, "B": 0, "G": 0}
    )
    activate_glint_horn(s, pirate("Glint-Horn Buccaneer"))
    s.resolve_all()
    assert s.lost


def test_optional_curiosity_draws_may_be_declined():
    s = GameState(library=[])
    curiosity_trigger(s, decline=True)
    s.resolve_all()
    assert not s.lost and s.cards_drawn == 0


def test_curiosity_cleanup_step_triggers_create_another_cleanup_step():
    s = GameState(battlefield=[Permanent("Niv", {"Creature"}, enchanted_by_curiosity=True)])
    cleanup_step(s)
    assert s.cleanup_steps == 2


def test_twinflame_must_have_legal_original_creature_target():
    with pytest.raises(RulesError):
        cast_twinflame(GameState(), None)


def test_dualcaster_must_be_cast_while_copy_spell_is_on_stack():
    with pytest.raises(RulesError):
        cast_dualcaster_mage(GameState())


def test_dualcaster_copies_may_target_dualcaster():
    target = Permanent("Siren", {"Creature"})
    s = GameState(battlefield=[target])
    cast_twinflame(s, target)
    d = cast_dualcaster_mage(s)
    assert s.stack[-1].targets == [d]


def test_copied_spells_are_not_cast():
    target = Permanent("Siren", {"Creature"})
    s = GameState(battlefield=[target])
    cast_twinflame(s, target)
    cast_dualcaster_mage(s)
    assert s.stack[-1].kind == "copy" and s.stack[-1].cast is False


def test_removed_twinflame_target_does_not_prevent_dualcaster_copy():
    target = Permanent("Siren", {"Creature"})
    s = GameState(battlefield=[target])
    cast_twinflame(s, target)
    s.battlefield.remove(target)
    d = cast_dualcaster_mage(s)
    assert s.stack[-1].targets == [d]


def test_electroduplicate_flashback_works_correctly():
    t = Permanent("Siren", {"Creature"})
    s = GameState(graveyard=["Electroduplicate"], battlefield=[t])
    flashback_electroduplicate(s, t)
    assert "Electroduplicate" in s.exile and s.stack[-1].name == "Electroduplicate"


def test_lightning_rig_crew_crab_umbra_uses_opponent_dependent_treasures():
    s = GameState(treasures=1)
    crew = Permanent("Lightning-Rig Crew", {"Creature"}, {"Pirate"})
    assert deal_pirate_combat_damage(s, [crew, crew, crew], [0, 1, 2]) == 3
    assert s.treasures == 4


@pytest.mark.parametrize(
    ("card,target"),
    [
        ("Drift of Phantasms", "Electroduplicate"),
        ("Muddle the Mixture", "Twinflame"),
        ("Dizzy Spell", "Curiosity"),
    ],
)
def test_transmute_finds_only_matching_mana_value(card, target):
    assert transmute(GameState(), card, target) == target


def test_transmute_is_sorcery_speed():
    with pytest.raises(RulesError):
        transmute(GameState(phase=Phase.COMBAT), "Muddle the Mixture", "Twinflame")


def test_wizardcycling_finds_only_wizards():
    assert wizardcycle(GameState(), "Dualcaster Mage") == "Dualcaster Mage"
    with pytest.raises(RulesError):
        wizardcycle(GameState(), "Twinflame")


def test_long_term_plans_places_card_third_from_top():
    s = GameState(library=["a", "b", "Niv-Mizzet, the Firemind", "c"])
    long_term_plans(s, "Niv-Mizzet, the Firemind")
    assert s.library[2] == "Niv-Mizzet, the Firemind"


def test_one_tutor_cannot_provide_both_halves_of_combo():
    with pytest.raises(RulesError):
        use_single_tutor_for_combo_halves()


def test_commander_tax_increases_after_each_command_zone_casting():
    s = GameState()
    assert cast_commander("Malcolm, Keen-Eyed Navigator", 3, s) == 3
    assert cast_commander("Malcolm, Keen-Eyed Navigator", 3, s) == 5
    assert cast_commander("Malcolm, Keen-Eyed Navigator", 3, s) == 7


def test_split_card_casting_and_mana_values_handled_correctly():
    assert cast_split_card("Invert") == 1 and cast_split_card("Invent") == 6


def test_tapped_lands_and_colored_mana_are_sequenced_legally():
    s = GameState()
    land = play_land(s, "Island")
    tap_for_mana(s, land)
    assert s.mana_pool["U"] == 1 and land.tapped
    with pytest.raises(RulesError):
        tap_for_mana(s, land)


def test_same_seed_reproduces_same_shuffle_and_result():
    cards = [str(i) for i in range(10)]
    assert shuffled_library(cards, 8675309) == shuffled_library(cards, 8675309)
