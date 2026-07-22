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
    commit,
    cycle,
    create_treasure,
    cast_twinflame,
    cleanup_step,
    curiosity_trigger,
    deal_noncombat_damage,
    deal_pirate_combat_damage,
    declare_attackers,
    flashback_electroduplicate,
    invent,
    invert,
    long_term_plans,
    mana_value,
    memory,
    move_to_graveyard_or_command_zone,
    play_land,
    rebuild,
    retarget_copy,
    shuffled_library,
    sacrifice_treasure_for_mana,
    StackObject,
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
    s = GameState(
        hand=[card], library=[target], mana_pool={"C": 1, "U": 2, "R": 0, "W": 0, "B": 0, "G": 0}
    )
    assert transmute(s, card, target) == target
    assert card in s.graveyard and target in s.hand and target not in s.library


def test_transmute_is_sorcery_speed():
    with pytest.raises(RulesError):
        transmute(
            GameState(
                phase=Phase.COMBAT,
                hand=["Muddle the Mixture"],
                library=["Twinflame"],
                mana_pool={"C": 1, "U": 2, "R": 0, "W": 0, "B": 0, "G": 0},
            ),
            "Muddle the Mixture",
            "Twinflame",
        )


def test_wizardcycling_finds_only_wizards():
    s = GameState(
        hand=["Step Through"],
        library=["Dualcaster Mage"],
        mana_pool={"C": 2, "U": 0, "R": 0, "W": 0, "B": 0, "G": 0},
    )
    assert wizardcycle(s, "Dualcaster Mage", "Step Through") == "Dualcaster Mage"
    assert "Step Through" in s.graveyard and "Dualcaster Mage" in s.hand
    with pytest.raises(RulesError):
        wizardcycle(
            GameState(
                hand=["Vedalken Aethermage"],
                library=["Twinflame"],
                mana_pool={"C": 3, "U": 0, "R": 0, "W": 0, "B": 0, "G": 0},
            ),
            "Twinflame",
            "Vedalken Aethermage",
        )


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
    assert mana_value("Invert // Invent", zone="library") == 7
    assert mana_value("Commit // Memory", zone="graveyard") == 10
    assert mana_value("Commit // Memory", zone="stack", face="Commit") == 4
    assert mana_value("Commit // Memory", zone="stack", face="Memory") == 6


def test_transmute_rejects_wrong_mana_value_and_nonempty_stack():
    s = GameState(
        hand=["Drift of Phantasms"],
        library=["Twinflame"],
        mana_pool={"C": 1, "U": 2, "R": 0, "W": 0, "B": 0, "G": 0},
    )
    with pytest.raises(RulesError):
        transmute(s, "Drift of Phantasms", "Twinflame")
    s = GameState(
        hand=["Dizzy Spell"],
        library=["Curiosity"],
        stack=[StackObject("x", "spell", lambda _s: None)],
        mana_pool={"C": 1, "U": 2, "R": 0, "W": 0, "B": 0, "G": 0},
    )
    with pytest.raises(RulesError):
        transmute(s, "Dizzy Spell", "Curiosity")


def test_rebuild_cycling_pays_discards_and_draws():
    s = GameState(
        hand=["Rebuild"],
        library=["drawn"],
        mana_pool={"C": 2, "U": 0, "R": 0, "W": 0, "B": 0, "G": 0},
    )
    cycle(s, "Rebuild")
    assert s.hand == ["drawn"] and s.graveyard == ["Rebuild"] and s.cards_drawn == 1


def test_invert_and_invent_legal_modes_are_separate_branches():
    creature = Permanent("Wizard", {"Creature"}, power=1, toughness=3)
    invert(GameState(), [creature])
    assert (creature.power, creature.toughness) == (3, 1)
    s = GameState(library=["Long-Term Plans", "Twinflame"])
    assert invent(s, instant="Long-Term Plans") == ("Long-Term Plans",)
    assert invent(s, sorcery="Twinflame") == ("Twinflame",)


def test_commit_memory_zones_and_rebuild_spell_effect():
    spell = StackObject("Twinflame", "spell", lambda _s: None)
    artifact = Permanent("Sol Ring", {"Artifact"})
    land = Permanent("Island", {"Land"})
    s = GameState(library=["a", "b"], stack=[spell], battlefield=[artifact, land])
    commit(s, spell)
    assert s.library[1] == "Twinflame" and spell not in s.stack
    rebuild(s)
    assert "Sol Ring" in s.hand and land in s.battlefield
    s = GameState(
        library=[str(i) for i in range(7)], hand=["x"], graveyard=["Commit // Memory", "y"]
    )
    memory(s)
    assert "Commit // Memory" in s.exile and len(s.hand) == 7 and "x" in s.library


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


def test_generic_cost_can_be_paid_with_colorless_or_colored_mana():
    s = GameState(mana_pool={"C": 1, "U": 0, "R": 1, "W": 0, "B": 0, "G": 0})
    s.pay_mana({"generic": 1, "R": 1})
    assert s.mana_pool == {"C": 0, "U": 0, "R": 0, "W": 0, "B": 0, "G": 0}


def test_colorless_cost_cannot_be_paid_with_generic_symbol_confusion():
    s = GameState(mana_pool={"C": 0, "U": 1, "R": 1, "W": 0, "B": 0, "G": 0})
    s.pay_mana({"generic": 1, "R": 1})
    with pytest.raises(RulesError):
        s.pay_mana({"C": 1})


def test_mana_pool_empties_on_phase_transition():
    s = GameState(mana_pool={"C": 0, "U": 1, "R": 1, "W": 0, "B": 0, "G": 0})
    s.advance_phase(Phase.COMBAT)
    assert all(amount == 0 for amount in s.mana_pool.values())


def test_treasure_sacrifices_for_any_legal_mana_type():
    s = GameState()
    create_treasure(s)
    sacrifice_treasure_for_mana(s, "G")
    assert s.treasures == 0 and s.mana_pool["G"] == 1


def test_lands_with_tapped_entry_rules_cannot_immediately_tap():
    s = GameState()
    land = play_land(s, "Izzet Boilerworks")
    assert land.tapped
    with pytest.raises(RulesError):
        tap_for_mana(s, land, "U")


def test_declare_attackers_enforces_summoning_sickness_and_haste():
    sick = Permanent("New Pirate", {"Creature"}, {"Pirate"})
    hasty = Permanent("Hasty Pirate", {"Creature"}, {"Pirate"}, haste=True)
    s = GameState(phase=Phase.COMBAT, battlefield=[sick, hasty])
    with pytest.raises(RulesError):
        declare_attackers(s, [sick])
    declare_attackers(s, [hasty])
    assert hasty.attacking and hasty.tapped


def test_noncombat_damage_during_resolution_defers_state_based_actions():
    s = GameState(opponent_life=[1, 1, 1])

    def effect(state: GameState) -> None:
        deal_noncombat_damage(state, [0, 1, 2], 1)
        assert not state.won

    s.stack.append(StackObject("lethal damage", "ability", effect, cast=False))
    s.resolve_top()
    assert s.won


def test_simultaneous_opponent_elimination_marks_table_win():
    s = GameState(opponent_life=[1, 1, 1])
    deal_noncombat_damage(s, [0, 1, 2], 1)
    assert s.won and s.terminal


def test_independent_commander_taxes_are_tracked_separately():
    s = GameState()
    assert cast_commander("Malcolm, Keen-Eyed Navigator", 3, s) == 3
    assert cast_commander("Breeches, Brazen Plunderer", 4, s) == 4
    assert cast_commander("Malcolm, Keen-Eyed Navigator", 3, s) == 5


def test_command_zone_replacement_is_choice_scoped_to_commander():
    malcolm = Permanent("Malcolm, Keen-Eyed Navigator", {"Creature"})
    token = Permanent("Treasure", {"Artifact"}, {"Treasure"}, is_token=True)
    s = GameState(battlefield=[malcolm, token])
    move_to_graveyard_or_command_zone(s, malcolm, use_command_zone=True)
    move_to_graveyard_or_command_zone(s, token, use_command_zone=True)
    assert s.command_zone_replacements["Malcolm, Keen-Eyed Navigator"] is True
    assert token.name not in s.graveyard


def test_copy_retargeting_rejects_illegal_targets():
    creature = Permanent("Siren", {"Creature"})
    artifact = Permanent("Sol Ring", {"Artifact"})
    s = GameState(battlefield=[creature, artifact])
    original = cast_twinflame(s, creature)
    with pytest.raises(RulesError):
        retarget_copy(s, original, [artifact])
