from __future__ import annotations

import json

import pytest

from mtg_sim.engine import (
    Action,
    ActionType,
    GameState,
    Permanent,
    Phase,
    StackObject,
    execute_action,
    generate_legal_actions,
    validate_action,
)
from mtg_sim.executable_adapters import (
    expected_card_names,
    validate_executable_coverage,
    write_report,
)


def pool():
    return {"C": 20, "U": 20, "R": 20, "W": 0, "B": 0, "G": 0}


CREATURE_COMBO_CARDS = [
    "Malcolm, Keen-Eyed Navigator",
    "Breeches, Brazen Plunderer",
    "Glint-Horn Buccaneer",
    "Dualcaster Mage",
    "Electroduplicate",
    "Twinflame",
    "Curiosity",
    "Niv-Mizzet, the Firemind",
    "Psychosis Crawler",
    "Lightning-Rig Crew",
    "Crab Umbra",
    "Siren Stormtamer",
    "Spectral Sailor",
    "Storm Fleet Sprinter",
    "Wily Goblin",
    "Drift of Phantasms",
    "Vedalken Aethermage",
]


@pytest.mark.parametrize("card", sorted(expected_card_names()))
def test_every_unique_card_generates_validated_executable_replayable_event(card):
    battlefield = [
        Permanent(
            "Target Pirate", {"Creature"}, {"Pirate"}, summoning_sick=False, power=1, toughness=1
        ),
        Permanent("Opponent Rock", {"Artifact"}, controller=1),
        Permanent("Opponent Bear", {"Creature"}, controller=1, power=2, toughness=2),
    ]
    stack = []
    if card in {
        "Arcane Denial",
        "Change the Equation",
        "Dispel",
        "Negate",
        "Spell Pierce",
        "Syncopate",
        "Wash Away",
        "Commit // Memory",
    }:
        stack = [
            StackObject(
                "Hostile Instant",
                "spell",
                lambda _s: None,
                mana_value=1,
                types={"Instant"},
                colors={"R"},
                cast_from_hand=False,
            )
        ]
    state = GameState(
        hand=[card, "Island", "Mountain", "Twinflame", "Dualcaster Mage"],
        library=[
            "Island",
            "Mountain",
            "Opt",
            "Niv-Mizzet, the Firemind",
            "Dualcaster Mage",
            "Twinflame",
        ],
        graveyard=["Electroduplicate"] if card == "Electroduplicate" else [],
        battlefield=battlefield,
        command_zone=["Malcolm, Keen-Eyed Navigator", "Breeches, Brazen Plunderer"],
        stack=stack,
        mana_pool=pool(),
    )
    if card == "Aetherize":
        battlefield[2].attacking = True
    if card in {
        "Arcane Denial",
        "Change the Equation",
        "Dispel",
        "Negate",
        "Spell Pierce",
        "Syncopate",
        "Wash Away",
    }:
        state.phase = Phase.COMBAT

    if card == "Dualcaster Mage":
        execute_action(
            state,
            Action(
                ActionType.CAST_SPELL,
                "Twinflame",
                (battlefield[0],),
                {"generic": 1, "R": 1},
                timing="sorcery",
                origin_zone="hand",
            ),
        )
    actions = [a for a in generate_legal_actions(state) if a.source_name == card]
    assert actions, card
    action = actions[0]
    if card == "Commit // Memory":
        action = Action(
            ActionType.CAST_SPELL,
            card,
            mana_cost={"generic": 3, "U": 1},
            timing="instant",
            origin_zone="hand",
            stack_target=stack[0],
            choice="Commit",
        )
    assert validate_action(state, action).accepted
    before = len(state.event_log)
    execute_action(state, action)
    if state.stack:
        execute_action(state, Action(ActionType.PASS_PRIORITY))
    assert state.event_log[before:], card
    assert any(
        card in e or (action.ability_id and action.ability_id in e) or action.action_type.value in e
        for e in state.event_log[before:]
    )


def test_commanders_cast_from_command_zone_track_tax_independently():
    state = GameState(mana_pool=pool())
    malcolm = next(
        a for a in generate_legal_actions(state) if a.source_name == "Malcolm, Keen-Eyed Navigator"
    )
    execute_action(state, malcolm)
    assert state.commander_casts["Malcolm, Keen-Eyed Navigator"] == 1
    state.command_zone.append("Malcolm, Keen-Eyed Navigator")
    second = next(
        a for a in generate_legal_actions(state) if a.source_name == "Malcolm, Keen-Eyed Navigator"
    )
    assert second.mana_cost == {"generic": 4, "U": 1}
    breeches = next(
        a for a in generate_legal_actions(state) if a.source_name == "Breeches, Brazen Plunderer"
    )
    assert breeches.mana_cost == {"generic": 3, "R": 1}


def test_pirate_combat_damage_creates_malcolm_and_breeches_resources():
    malcolm = Permanent(
        "Malcolm, Keen-Eyed Navigator", {"Creature"}, {"Pirate"}, summoning_sick=False
    )
    breeches = Permanent(
        "Breeches, Brazen Plunderer", {"Creature"}, {"Pirate"}, summoning_sick=False
    )
    state = GameState(battlefield=[malcolm, breeches], mana_pool=pool())
    state.phase = state.phase.COMBAT
    execute_action(state, Action(ActionType.DECLARE_ATTACKERS, "attack", (malcolm, breeches)))
    execute_action(state, Action(ActionType.COMBAT_DAMAGE, "combat_damage"))
    assert state.treasures >= 2
    assert state.breeches_unknown_exiled
    assert any(e.startswith("breeches_unknown_exiled") for e in state.event_log)


def test_combo_piece_handlers_are_separate_and_rules_relevant():
    target = Permanent("Spectral Sailor", {"Creature"}, {"Pirate"}, summoning_sick=False)
    state = GameState(
        hand=["Twinflame", "Electroduplicate", "Curiosity"], battlefield=[target], mana_pool=pool()
    )
    for card in ["Twinflame", "Electroduplicate", "Curiosity"]:
        action = next(a for a in generate_legal_actions(state) if a.source_name == card)
        execute_action(state, action)
        execute_action(state, Action(ActionType.PASS_PRIORITY))
    assert any(e == "token_created:copy:Spectral Sailor" for e in state.event_log)
    assert target.enchanted_by_curiosity


def test_niv_summoning_sickness_psychosis_life_loss_and_full_report(tmp_path):
    sick_niv = Permanent(
        "Niv-Mizzet, the Firemind", {"Creature"}, {"Dragon", "Wizard"}, summoning_sick=True
    )
    assert not validate_action(
        GameState(battlefield=[sick_niv], mana_pool=pool()),
        Action(
            ActionType.ACTIVATE_ABILITY,
            "Niv-Mizzet, the Firemind",
            mana_cost={},
            ability_id="tap_draw",
        ),
    ).accepted
    crawler = Permanent("Psychosis Crawler", {"Artifact", "Creature"}, power=0, toughness=0)
    state = GameState(library=["Opt"], battlefield=[crawler])
    state.draw(1)
    assert state.opponent_life == [39, 39, 39]
    report = write_report(tmp_path / "full-executable-coverage.json")
    assert report["expected_unique_card_count"] == 80
    assert report["executable_adapter_count"] == 80
    assert report["blocked_adapter_count"] == 0
    assert validate_executable_coverage() == []
    assert json.loads((tmp_path / "full-executable-coverage.json").read_text())["errors"] == []
