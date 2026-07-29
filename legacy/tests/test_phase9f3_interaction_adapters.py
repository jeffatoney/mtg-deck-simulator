from __future__ import annotations

import pytest

from mtg_sim.engine import (
    Action,
    ActionType,
    GameState,
    Permanent,
    RulesError,
    StackObject,
    execute_action,
    generate_legal_actions,
    validate_action,
)
from mtg_sim.executable_adapters import adapter_registry, validate_executable_coverage
from mtg_sim.protection import AnswerClass, evaluate_protection


def mana():
    return {"C": 20, "U": 20, "R": 20, "W": 0, "B": 0, "G": 0}


def hostile(name="Removal", *, targets=(), types=None, colors=None, mv=2, player=False, hand=True):
    return StackObject(
        name,
        "spell",
        lambda _s: None,
        list(targets),
        mana_value=mv,
        types=set(types or {"Instant"}),
        colors=set(colors or {"R"}),
        targets_player=player,
        cast_from_hand=hand,
    )


def names(state, card):
    return [a for a in generate_legal_actions(state) if a.source_name == card]


def test_stack_counter_actions_only_in_legal_stack_windows_and_recheck_resolution():
    bear = Permanent("Malcolm", {"Creature"})
    spell = hostile(targets=[bear], types={"Instant"}, mv=1)
    state = GameState(
        hand=[
            "Arcane Denial",
            "Dispel",
            "Negate",
            "Spell Pierce",
            "Syncopate",
            "Wash Away",
            "Change the Equation",
        ],
        battlefield=[bear],
        stack=[spell],
        mana_pool=mana(),
    )
    assert {a.source_name for a in generate_legal_actions(state)} >= {
        "Arcane Denial",
        "Dispel",
        "Negate",
        "Spell Pierce",
        "Syncopate",
        "Wash Away",
        "Change the Equation",
    }
    action = next(a for a in names(state, "Arcane Denial"))
    state.stack.remove(spell)
    with pytest.raises(RulesError):
        execute_action(state, action)


def test_permanent_target_actions_appear_and_disappear_by_target_class():
    artifact = Permanent("Clue", {"Artifact"}, controller=1)
    creature = Permanent("Bear", {"Creature"}, mana_value=2)
    land = Permanent("Island", {"Land"})
    state = GameState(
        hand=[
            "Abrade",
            "Echoing Truth",
            "Fading Hope",
            "Into the Roil",
            "Introduction to Annihilation",
            "Ravenform",
            "Reality Ripple",
            "Reality Shift",
            "Resculpt",
        ],
        battlefield=[artifact, creature, land],
        mana_pool=mana(),
    )
    for card in state.hand:
        assert names(state, card), card
    no_targets = GameState(hand=list(state.hand), battlefield=[land], mana_pool=mana())
    assert not [
        a
        for a in generate_legal_actions(no_targets)
        if a.source_name
        in {
            "Abrade",
            "Echoing Truth",
            "Fading Hope",
            "Into the Roil",
            "Introduction to Annihilation",
            "Ravenform",
            "Reality Shift",
            "Resculpt",
        }
    ]


def test_x_overload_kicker_cleave_variants_and_tokens():
    a = Permanent("A", {"Artifact", "Creature"}, controller=1)
    b = Permanent("B", {"Creature"}, controller=1)
    state = GameState(
        hand=["By Force", "Curse of the Swine", "Vandalblast", "Into the Roil", "Wash Away"],
        battlefield=[a, b],
        library=["Hidden"],
        mana_pool=mana(),
    )
    stack_state = GameState(
        hand=["Wash Away"],
        stack=[hostile("Commander", types={"Creature"}, hand=False)],
        mana_pool=mana(),
    )
    assert any(
        x.x_value == 1 and x.mana_cost == {"R": 1, "generic": 1} for x in names(state, "By Force")
    )
    assert any(
        x.x_value == 2 and x.mana_cost == {"U": 2, "generic": 2}
        for x in names(state, "Curse of the Swine")
    )
    assert any(
        "overload" in x.additional_costs and x.mana_cost == {"generic": 4, "R": 1}
        for x in names(state, "Vandalblast")
    )
    assert any(
        "kicker" in x.additional_costs and x.mana_cost == {"generic": 3, "U": 1}
        for x in names(state, "Into the Roil")
    )
    assert any(
        "cleave" in x.additional_costs and x.mana_cost == {"generic": 2, "U": 1}
        for x in names(stack_state, "Wash Away")
    )
    execute_action(state, next(x for x in names(state, "Curse of the Swine") if x.x_value == 2))
    execute_action(state, Action(ActionType.PASS_PRIORITY))
    assert [p.name for p in state.battlefield].count("Boar") == 2


def test_sweepers_graveyards_lands_and_activated_dispatch():
    totem = Permanent("Sentinel Totem", {"Artifact"})
    lantern = Permanent("Soul-Guide Lantern", {"Artifact"})
    grounds = Permanent("Scavenger Grounds", {"Land"})
    field = Permanent("Demolition Field", {"Land"})
    state = GameState(
        battlefield=[
            totem,
            lantern,
            grounds,
            field,
            Permanent("Goblin", {"Creature"}, attacking=True),
            Permanent("Rock", {"Artifact"}),
        ],
        hand=["Aetherize", "Brotherhood's End", "Fiery Cannonade"],
        graveyard=["Dead"],
        library=["Island"],
        mana_pool=mana(),
    )
    for card in ["Aetherize", "Brotherhood's End", "Fiery Cannonade"]:
        assert names(state, card)
    for source, ability in [
        ("Sentinel Totem", "exile_all_graveyards"),
        ("Soul-Guide Lantern", "draw"),
        ("Scavenger Grounds", "exile_graveyards"),
        ("Demolition Field", "destroy_nonbasic"),
    ]:
        assert validate_action(
            state,
            Action(
                ActionType.ACTIVATE_ABILITY,
                source,
                mana_cost={"generic": 2}
                if source in {"Scavenger Grounds", "Demolition Field"}
                else ({"generic": 1} if ability == "draw" else {}),
                ability_id=ability,
                choice="Island",
            ),
        ).accepted


def test_protection_evaluator_reserved_mana_and_siren_dispatch():
    creature = Permanent("Malcolm", {"Creature"})
    siren = Permanent(
        "Siren Stormtamer", {"Creature"}, {"Siren", "Pirate", "Wizard"}, summoning_sick=False
    )
    threat = hostile(targets=[creature])
    state = GameState(
        hand=["Lazotep Plating"],
        battlefield=[creature, siren],
        stack=[threat],
        mana_pool={"U": 2, "R": 0, "C": 1, "W": 0, "B": 0, "G": 0},
    )
    ev = evaluate_protection(
        state, combo_mana_cost={"U": 1}, protected_object=creature, threat=threat
    )
    assert (
        ev.available
        and ev.sufficient_mana_after_combo
        and ev.independent_of_unspecified_opponent_choice
    )
    assert (
        AnswerClass.REMOVAL_TARGETING_CREATURE in ev.answers
        or AnswerClass.SPELL_OR_ABILITY_TARGETING_US in ev.answers
    )
    siren_action = next(
        a for a in generate_legal_actions(state) if a.source_name == "Siren Stormtamer"
    )
    execute_action(state, siren_action)
    assert "Siren Stormtamer" in state.graveyard and "Removal" in state.graveyard


def test_executable_registry_has_phase9f3_cards():
    required = {
        "Abrade",
        "Aetherize",
        "Arcane Denial",
        "Brotherhood's End",
        "By Force",
        "Change the Equation",
        "Curse of the Swine",
        "Dispel",
        "Echoing Truth",
        "Fading Hope",
        "Fiery Cannonade",
        "Into the Roil",
        "Introduction to Annihilation",
        "Lazotep Plating",
        "Negate",
        "Prismari Command",
        "Ravenform",
        "Reality Ripple",
        "Reality Shift",
        "Rebuild",
        "Resculpt",
        "Sentinel Totem",
        "Siren Stormtamer",
        "Soul-Guide Lantern",
        "Spell Pierce",
        "Syncopate",
        "Vandalblast",
        "Wash Away",
        "Scavenger Grounds",
        "Demolition Field",
        "Commit // Memory",
    }
    reg = adapter_registry()
    assert not validate_executable_coverage(reg)
    assert all(reg[name].status == "EXECUTABLE" for name in required)
