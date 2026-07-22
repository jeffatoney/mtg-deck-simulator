from __future__ import annotations

import pytest

from mtg_sim.engine import (
    GameState,
    Permanent,
    RulesError,
    StackObject,
    abrade,
    aetherize,
    arcane_denial,
    brotherhoods_end,
    by_force,
    change_the_equation,
    curse_of_the_swine,
    dispel,
    echoing_truth,
    fading_hope,
    fiery_cannonade,
    into_the_roil,
    introduction_to_annihilation,
    lazotep_plating,
    negate,
    prismari_command,
    ravenform,
    reality_ripple,
    reality_shift,
    rebuild,
    resculpt,
    sentinel_totem_exile_all_graveyards,
    sentinel_totem_etb,
    siren_stormtamer_counter,
    soul_guide_lantern_draw,
    soul_guide_lantern_etb,
    soul_guide_lantern_exile_opponents,
    spell_pierce,
    syncopate,
    vandalblast,
    wash_away,
)


def spell(
    name="Lightning Bolt",
    types=None,
    colors=None,
    mv=1,
    from_hand=True,
    targets=(),
    targets_player=False,
):
    return StackObject(
        name,
        "spell",
        lambda _s: None,
        list(targets),
        mana_value=mv,
        types=set(types or {"Instant"}),
        colors=set(colors or {"R"}),
        cast_from_hand=from_hand,
        targets_player=targets_player,
    )


def test_counterspells_enforce_target_restrictions_and_conditional_payment():
    instant = spell(types={"Instant"})
    creature = spell("Bear", types={"Creature"}, mv=2)
    big_green = spell("Titan", types={"Creature"}, colors={"G"}, mv=6)
    s = GameState(stack=[instant, creature, big_green])
    dispel(s, instant)
    assert "Lightning Bolt" in s.graveyard
    with pytest.raises(RulesError):
        negate(s, creature)
    change_the_equation(s, big_green, "red_green")
    assert "Titan" in s.graveyard

    noncreature = spell("Wrath", types={"Sorcery"}, colors={"W"}, mv=4)
    s.stack.append(noncreature)
    assert spell_pierce(s, noncreature, pays=True) is False
    assert noncreature in s.stack
    assert syncopate(s, noncreature, 3, pays=False) is True
    assert "Wrath" in s.exile


def test_arcane_denial_and_wash_away_cast_from_hand_restriction():
    hand_spell = spell("Commander", types={"Creature"}, from_hand=True)
    command_spell = spell("Commander", types={"Creature"}, from_hand=False)
    s = GameState(stack=[hand_spell, command_spell])
    with pytest.raises(RulesError):
        wash_away(s, hand_spell)
    wash_away(s, command_spell)
    assert "Commander" in s.graveyard
    s.stack.append(hand_spell)
    arcane_denial(s, hand_spell, target_controller_draws=2)
    assert any(e == "delayed_draw:Arcane Denial:self:1:target_controller:2" for e in s.event_log)


def test_bounce_and_phasing_modes_require_legal_targets():
    attacker = Permanent("Goblin", {"Creature"}, attacking=True)
    nonattacker = Permanent("Siren", {"Creature"})
    rock = Permanent("Rock", {"Artifact"})
    s = GameState(battlefield=[attacker, nonattacker, rock], library=["draw"])
    aetherize(s)
    assert "Goblin" in s.hand and nonattacker in s.battlefield
    fading_hope(s, nonattacker)
    assert "Siren" in s.hand
    into_the_roil(s, rock, kicked=True)
    assert "Rock" in s.hand and s.hand[-1] == "draw"
    land = Permanent("Island", {"Land"})
    s.battlefield.append(land)
    reality_ripple(s, land)
    assert land.phased_out
    with pytest.raises(RulesError):
        echoing_truth(s, land)


def test_exile_replacement_tokens_and_x_targets_are_exact():
    bird_target = Permanent("Ornithopter", {"Artifact", "Creature"})
    shift_target = Permanent("Bear", {"Creature"})
    sculpt_target = Permanent("Map", {"Artifact"})
    swine_a = Permanent("A", {"Creature"})
    swine_b = Permanent("B", {"Creature"})
    s = GameState(
        battlefield=[bird_target, shift_target, sculpt_target, swine_a, swine_b], library=["Hidden"]
    )
    ravenform(s, bird_target)
    reality_shift(s, shift_target)
    resculpt(s, sculpt_target)
    curse_of_the_swine(s, [swine_a, swine_b], 2)
    assert {"Ornithopter", "Bear", "Map", "A", "B"}.issubset(set(s.exile))
    assert [p.name for p in s.battlefield].count("Bird") == 1
    assert [p.name for p in s.battlefield].count("Manifest") == 1
    assert [p.name for p in s.battlefield].count("Elemental") == 1
    assert [p.name for p in s.battlefield].count("Boar") == 2
    with pytest.raises(RulesError):
        curse_of_the_swine(s, [], 1)


def test_destruction_damage_modal_and_overload_effects_do_not_invent_opponents():
    creature = Permanent("Bear", {"Creature"}, toughness=3)
    artifact = Permanent("Clue", {"Artifact"}, mana_value=0, controller=1)
    own_artifact = Permanent("Mind Stone", {"Artifact"}, mana_value=2, controller=0)
    pirate = Permanent("Malcolm", {"Creature"}, {"Pirate"})
    s = GameState(battlefield=[creature, artifact, own_artifact, pirate])
    abrade(s, "damage_creature", creature)
    abrade(s, "destroy_artifact", artifact)
    assert creature.damage == 3 and "Clue" in s.graveyard
    by_force(s, [own_artifact], 1)
    assert "Mind Stone" in s.graveyard
    s.battlefield.extend(
        [Permanent("A", {"Artifact"}, controller=1), Permanent("O", {"Artifact"}, controller=0)]
    )
    vandalblast(s, overload=True)
    assert "A" in s.graveyard and any(p.name == "O" for p in s.battlefield)
    fiery_cannonade(s)
    assert creature.damage == 5 and pirate.damage == 0
    brotherhoods_end(s, "damage")
    assert creature.damage == 8


def test_graveyard_exile_artifacts_and_siren_stormtamer_and_existing_zone_modes():
    totem = Permanent("Sentinel Totem", {"Artifact"})
    lantern = Permanent("Soul-Guide Lantern", {"Artifact"})
    stormtamer = Permanent("Siren Stormtamer", {"Creature"}, {"Siren", "Pirate", "Wizard"})
    own_creature = Permanent("Malcolm", {"Creature"})
    hostile = spell("Removal", targets=[own_creature])
    s = GameState(
        battlefield=[
            totem,
            lantern,
            stormtamer,
            own_creature,
            Permanent("Treasure", {"Artifact"}, is_token=True),
        ],
        graveyard=["Card A", "Card B"],
        library=["drawn"],
        stack=[hostile],
    )
    sentinel_totem_etb(s)
    soul_guide_lantern_etb(s, "Card A")
    assert "Card A" in s.exile
    soul_guide_lantern_draw(s, lantern)
    assert "drawn" in s.hand and "Soul-Guide Lantern" in s.graveyard
    siren_stormtamer_counter(s, stormtamer, hostile)
    assert "Removal" in s.graveyard and "Siren Stormtamer" in s.graveyard
    sentinel_totem_exile_all_graveyards(s, totem)
    assert not s.graveyard and "Sentinel Totem" in s.exile


def test_prismari_lazotep_introduction_rebuild_existing_artifact_mode():
    artifact = Permanent("Map", {"Artifact"})
    target = Permanent("Thing", {"Creature"})
    s = GameState(battlefield=[artifact, target], library=["a", "b"])
    prismari_command(
        s, ("damage", "destroy_artifact"), damage_target=target, artifact_target=artifact
    )
    assert target.damage == 2 and "Map" in s.graveyard
    army = lazotep_plating(s)
    assert army.name == "Zombie Army" and army.power == 1 and army.hexproof_until_eot
    introduction_to_annihilation(s, target)
    assert "Thing" in s.exile
    rock = Permanent("Mind Stone", {"Artifact"})
    s.battlefield.append(rock)
    rebuild(s)
    assert "Mind Stone" in s.hand


def test_no_legal_target_interaction_is_rejected():
    s = GameState(battlefield=[Permanent("Island", {"Land"})])
    with pytest.raises(RulesError):
        abrade(s, "destroy_artifact", s.battlefield[0])
    with pytest.raises(RulesError):
        by_force(s, [], 1)
    with pytest.raises(RulesError):
        soul_guide_lantern_exile_opponents(s, Permanent("Soul-Guide Lantern", {"Artifact"}))
