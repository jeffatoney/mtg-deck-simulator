from __future__ import annotations

import pytest

from mtg_sim.engine import (
    GameState,
    Permanent,
    Phase,
    RulesError,
    declare_attackers,
    deal_damage,
    move_commander_to_zone,
    retarget_stack_object,
    sacrifice_treasure_for_mana,
    solve_mana_payment,
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
    move_commander_to_zone(s, "Malcolm, Keen-Eyed Navigator", "graveyard", choose_command_zone=True)
    assert cast_commander("Malcolm, Keen-Eyed Navigator", 3, s) == 5
    move_commander_to_zone(s, "Malcolm, Keen-Eyed Navigator", "graveyard", choose_command_zone=True)
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


def test_phase4b_001_colored_mana_legality():
    assert solve_mana_payment({"U": 1}, {"U": 1})["U"] == 0
    with pytest.raises(RulesError):
        solve_mana_payment({"R": 1}, {"U": 1})


def test_phase4b_002_generic_mana_legality():
    assert solve_mana_payment({"R": 1, "U": 1}, {"generic": 2}) == {
        "C": 0,
        "W": 0,
        "U": 0,
        "B": 0,
        "R": 0,
        "G": 0,
    }
    with pytest.raises(RulesError):
        solve_mana_payment({"R": 1}, {"generic": 2})


def test_phase4b_003_tapped_lands_cannot_produce_mana():
    s = GameState()
    land = play_land(s, "Island")
    tap_for_mana(s, land)
    with pytest.raises(RulesError):
        tap_for_mana(s, land)


def test_phase4b_004_entry_tapped_sequencing_and_choice():
    s = GameState()
    gate = play_land(s, "Izzet Guildgate")
    assert gate.tapped
    with pytest.raises(RulesError):
        tap_for_mana(s, gate)
    s.advance_phase(Phase.BEGINNING)
    pathway = play_land(s, "Riverglide Pathway", enter_tapped=False)
    assert not pathway.tapped


def test_phase4b_005_treasure_colored_mana_use():
    s = GameState(treasures=1)
    sacrifice_treasure_for_mana(s, "G")
    assert s.treasures == 0 and s.mana_pool["G"] == 1


def test_phase4b_006_summoning_sickness():
    s = GameState(battlefield=[Permanent("Lightning-Rig Crew", {"Creature"}, {"Pirate"})])
    with pytest.raises(RulesError):
        declare_attackers(s, s.battlefield)


def test_phase4b_007_haste():
    p = Permanent("Hasty Pirate", {"Creature"}, {"Pirate"}, haste=True)
    s = GameState(battlefield=[p])
    declare_attackers(s, [p])
    assert p.attacking and p.tapped


def test_phase4b_008_attacking_status():
    p = Permanent("Pirate", {"Creature"}, {"Pirate"}, summoning_sick=False)
    s = GameState(battlefield=[p])
    declare_attackers(s, [p])
    assert p.attacking


def test_phase4b_009_damage_prevention():
    p = Permanent("Prevented Pirate", {"Creature"}, {"Pirate"}, damage_prevented=True)
    s = GameState(opponent_life=[3, 3, 3])
    deal_damage(s, p, [0], 3, combat=True)
    assert s.opponent_life == [3, 3, 3]


def test_phase4b_010_unequal_opponent_life_totals():
    s = GameState(opponent_life=[1, 5, 9])
    deal_damage(s, "Lightning Bolt", [1], 3, combat=False)
    assert s.opponent_life == [1, 2, 9] and not s.won


def test_phase4b_011_simultaneous_opponent_loss():
    s = GameState(opponent_life=[2, 2, 2])
    deal_damage(s, "Earthquake", [0, 1, 2], 2, combat=False)
    assert s.won and s.terminal


def test_phase4b_012_independent_commander_tax():
    s = GameState()
    assert cast_commander("Malcolm, Keen-Eyed Navigator", 3, s) == 3
    move_commander_to_zone(s, "Malcolm, Keen-Eyed Navigator", "graveyard", choose_command_zone=True)
    assert cast_commander("Breeches, Brazen Plunderer", 4, s) == 4
    assert cast_commander("Malcolm, Keen-Eyed Navigator", 3, s) == 5


def test_phase4b_013_command_zone_choices():
    s = GameState()
    move_commander_to_zone(
        s, "Malcolm, Keen-Eyed Navigator", "graveyard", choose_command_zone=False
    )
    assert "Malcolm, Keen-Eyed Navigator" in s.graveyard
    move_commander_to_zone(s, "Breeches, Brazen Plunderer", "exile", choose_command_zone=True)
    assert (
        "Breeches, Brazen Plunderer" in s.command_zone
        and "Breeches, Brazen Plunderer" not in s.exile
    )


def test_phase4b_014_copied_spell_is_not_cast():
    target = Permanent("Siren", {"Creature"})
    s = GameState(battlefield=[target])
    cast_twinflame(s, target)
    cast_dualcaster_mage(s)
    assert s.stack[-1].kind == "copy" and not s.stack[-1].cast


def test_phase4b_015_legal_and_illegal_retargeting():
    target = Permanent("Siren", {"Creature"})
    replacement = Permanent("Dualcaster Mage", {"Creature"})
    s = GameState(battlefield=[target, replacement])
    copy = cast_twinflame(s, target)
    retarget_stack_object(copy, [replacement], s.battlefield)
    assert copy.targets == [replacement]
    with pytest.raises(RulesError):
        retarget_stack_object(copy, [Permanent("Mountain", {"Land"})], s.battlefield)


def test_phase4b_016_additional_cleanup_steps():
    s = GameState(cleanup_trigger_pending=True)
    cleanup_step(s)
    assert s.cleanup_steps == 2


def test_phase4b_017_game_ends_before_another_activation_or_draw_when_all_opponents_lose():
    s = GameState(opponent_life=[1, 1, 1])
    deal_damage(s, "Glint-Horn Buccaneer", [0, 1, 2], 1, combat=False)
    with pytest.raises(RulesError):
        sacrifice_treasure_for_mana(s, "R")
    with pytest.raises(RulesError):
        s.draw()
