import hashlib
import json

import pytest

from mtg_sim.engine import (
    Action,
    ActionType,
    GameState,
    Permanent,
    Phase,
    RulesError,
    execute_action,
    generate_legal_actions,
    validate_action,
)
from mtg_sim.game_executor import dualcaster_twinflame_fixture, replay_events, verify_replay_events


def test_pr22_ability_dispatch_uses_registered_card_handlers_only() -> None:
    state = GameState(
        library=["Drawn"],
        hand=["discard"],
        mana_pool={"C": 3, "U": 0, "R": 3, "W": 0, "B": 0, "G": 0},
    )
    gh = Permanent("Glint-Horn Buccaneer", {"Creature"}, {"Pirate"}, attacking=True)
    crew = Permanent("Lightning-Rig Crew", {"Creature"}, {"Pirate"}, summoning_sick=False)
    mind = Permanent("Mind Stone", {"Artifact"})
    totem = Permanent("Sentinel Totem", {"Artifact"})
    lantern = Permanent("Soul-Guide Lantern", {"Artifact"})
    state.battlefield.extend([gh, crew, mind, totem, lantern])

    execute_action(
        state,
        Action(
            ActionType.ACTIVATE_ABILITY,
            "Lightning-Rig Crew",
            mana_cost={},
            ability_id="tap_damage_each_opponent",
        ),
    )
    assert crew.tapped
    assert any(obj.name == "Lightning-Rig Crew damage ability" for obj in state.stack)
    assert not any(obj.name == "Glint-Horn draw ability" for obj in state.stack)

    execute_action(
        state,
        Action(
            ActionType.ACTIVATE_ABILITY, "Mind Stone", mana_cost={"generic": 1}, ability_id="draw"
        ),
    )
    assert "Mind Stone" in state.graveyard and "Drawn" in state.hand

    execute_action(
        state,
        Action(
            ActionType.ACTIVATE_ABILITY,
            "Sentinel Totem",
            mana_cost={},
            ability_id="exile_all_graveyards",
        ),
    )
    assert "Sentinel Totem" in state.exile

    execute_action(
        state,
        Action(
            ActionType.ACTIVATE_ABILITY,
            "Soul-Guide Lantern",
            mana_cost={},
            ability_id="exile_opponents_graveyards",
        ),
    )
    assert "Soul-Guide Lantern" in state.graveyard

    assert not validate_action(
        state,
        Action(ActionType.ACTIVATE_ABILITY, "Mind Stone", mana_cost={}, ability_id="glint_horn"),
    ).accepted


def test_pr22_command_zone_actions_and_tax_validation() -> None:
    state = GameState(hand=[], mana_pool={"C": 10, "U": 2, "R": 2, "W": 0, "B": 0, "G": 0})
    actions = generate_legal_actions(state)
    malcolm = next(a for a in actions if a.source_name == "Malcolm, Keen-Eyed Navigator")
    breeches = next(a for a in actions if a.source_name == "Breeches, Brazen Plunderer")
    assert malcolm.origin_zone == "command_zone" and malcolm.mana_cost == {"generic": 2, "U": 1}
    assert breeches.origin_zone == "command_zone" and breeches.mana_cost == {"generic": 3, "R": 1}
    assert "Malcolm, Keen-Eyed Navigator" not in state.hand

    execute_action(state, malcolm)
    assert state.commander_casts["Malcolm, Keen-Eyed Navigator"] == 1
    state.battlefield = [p for p in state.battlefield if p.name != "Malcolm, Keen-Eyed Navigator"]
    state.command_zone.append("Malcolm, Keen-Eyed Navigator")
    assert not validate_action(
        state,
        Action(
            ActionType.CAST_SPELL,
            "Malcolm, Keen-Eyed Navigator",
            mana_cost={"generic": 2, "U": 1},
            timing="sorcery",
            origin_zone="command_zone",
        ),
    ).accepted
    recast = Action(
        ActionType.CAST_SPELL,
        "Malcolm, Keen-Eyed Navigator",
        mana_cost={"generic": 4, "U": 1},
        timing="sorcery",
        origin_zone="command_zone",
    )
    assert validate_action(state, recast).accepted
    assert state.commander_casts.get("Breeches, Brazen Plunderer", 0) == 0

    poor = GameState(mana_pool={"C": 0, "U": 1, "R": 0, "W": 0, "B": 0, "G": 0})
    assert not validate_action(
        poor,
        Action(
            ActionType.CAST_SPELL,
            "Malcolm, Keen-Eyed Navigator",
            mana_cost={"generic": 2, "U": 1},
            timing="sorcery",
            origin_zone="command_zone",
        ),
    ).accepted


def test_pr22_fetch_lands_have_no_mana_ability_and_fetch_existing_basic_tapped() -> None:
    state = GameState(library=["Opt", "Mountain", "Island"], hand=["Evolving Wilds"])
    execute_action(state, Action(ActionType.PLAY_LAND, "Evolving Wilds", timing="sorcery"))
    wilds = next(p for p in state.battlefield if p.name == "Evolving Wilds")
    assert not validate_action(
        state, Action(ActionType.ACTIVATE_MANA_ABILITY, "Evolving Wilds", mana_choice="C")
    ).accepted
    execute_action(
        state,
        Action(
            ActionType.ACTIVATE_ABILITY, "Evolving Wilds", mana_cost={}, ability_id="basic_fetch"
        ),
    )
    assert wilds not in state.battlefield
    assert "Evolving Wilds" in state.graveyard
    assert any(p.name in {"Island", "Mountain"} and p.tapped for p in state.battlefield)

    no_basic = GameState(library=["Opt"], hand=["Terramorphic Expanse"])
    execute_action(no_basic, Action(ActionType.PLAY_LAND, "Terramorphic Expanse", timing="sorcery"))
    assert not validate_action(
        no_basic,
        Action(
            ActionType.ACTIVATE_ABILITY,
            "Terramorphic Expanse",
            mana_cost={},
            ability_id="basic_fetch",
        ),
    ).accepted


def test_pr22_declare_attackers_does_not_deal_damage_or_make_treasure() -> None:
    state = GameState(phase=Phase.COMBAT)
    pirate = Permanent("Glint-Horn Buccaneer", {"Creature"}, {"Pirate"}, summoning_sick=False)
    state.battlefield.append(pirate)
    execute_action(state, Action(ActionType.DECLARE_ATTACKERS, "attack", (pirate,)))
    assert pirate.attacking and pirate.tapped
    assert state.opponent_life == [40, 40, 40]
    assert state.treasures == 0
    execute_action(state, Action(ActionType.COMBAT_DAMAGE, "combat_damage"))
    assert state.opponent_life[0] == 39
    assert state.treasures == 1


def test_pr22_replay_verification_is_pure_and_detects_tampering() -> None:
    result = dualcaster_twinflame_fixture()
    events = result.events
    before_count = len(events)
    before_hash = hashlib.sha256(
        json.dumps(events, sort_keys=True, default=str).encode()
    ).hexdigest()
    first = verify_replay_events(events)
    second = verify_replay_events(events)
    assert first == second
    assert replay_events(events) == "won"
    assert len(events) == before_count
    assert (
        hashlib.sha256(json.dumps(events, sort_keys=True, default=str).encode()).hexdigest()
        == before_hash
    )
    assert events[-1]["event"] == "game_ended"
    tampered = list(events)
    tampered[-1] = dict(tampered[-1], event="not_game_ended")
    with pytest.raises(RulesError):
        verify_replay_events(tampered)
