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
from mtg_sim.executable_adapters import adapter_registry, validate_executable_coverage


def pool(c=0, u=0, r=0):
    return {"C": c, "U": u, "R": r, "W": 0, "B": 0, "G": 0}


def test_phase9f5_soul_guide_lantern_draw_pays_before_sacrifice():
    lantern = Permanent("Soul-Guide Lantern", {"Artifact"})
    state = GameState(library=["Island"], battlefield=[lantern], mana_pool=pool())
    action = Action(
        ActionType.ACTIVATE_ABILITY,
        "Soul-Guide Lantern",
        mana_cost={"generic": 1},
        ability_id="draw",
    )
    assert not validate_action(state, action).accepted
    state.mana_pool["C"] = 1
    execute_action(state, action)
    assert state.hand == ["Island"]
    assert "Soul-Guide Lantern" in state.graveyard
    assert state.mana_pool["C"] == 0


def test_phase9f5_cascade_bluffs_and_prismatic_lens_semantics():
    state = GameState(battlefield=[Permanent("Cascade Bluffs", {"Land"})], mana_pool=pool(r=1))
    execute_action(
        state, Action(ActionType.ACTIVATE_MANA_ABILITY, "Cascade Bluffs", mana_choice="UR")
    )
    assert state.mana_pool["U"] == 1 and state.mana_pool["R"] == 1
    lens = Permanent("Prismatic Lens", {"Artifact"})
    state = GameState(battlefield=[lens], mana_pool=pool(c=1))
    assert any(
        a.mana_choice == "C"
        for a in generate_legal_actions(state)
        if a.source_name == "Prismatic Lens"
    )
    execute_action(
        state, Action(ActionType.ACTIVATE_MANA_ABILITY, "Prismatic Lens", mana_choice="U")
    )
    assert state.mana_pool["U"] == 1 and state.mana_pool["C"] == 0


def test_phase9f5_demolition_field_and_scavenger_grounds_require_legal_costs_and_targets():
    demo = Permanent("Demolition Field", {"Land"})
    target = Permanent("Command Tower", {"Land"})
    state = GameState(library=["Island"], battlefield=[demo, target], mana_pool=pool(c=2))
    action = Action(
        ActionType.ACTIVATE_ABILITY,
        "Demolition Field",
        (target,),
        {"generic": 2},
        ability_id="destroy_nonbasic",
        choice="Island",
    )
    execute_action(state, action)
    assert "Demolition Field" in state.graveyard and "Command Tower" in state.graveyard
    assert any(p.name == "Island" for p in state.battlefield)

    grounds = Permanent("Scavenger Grounds", {"Land"}, {"Desert"})
    state = GameState(battlefield=[grounds], graveyard=["Opt"], mana_pool=pool(c=2))
    execute_action(
        state,
        Action(
            ActionType.ACTIVATE_ABILITY,
            "Scavenger Grounds",
            mana_cost={"generic": 2},
            ability_id="exile_graveyards",
        ),
    )
    assert state.graveyard == []


def test_phase9f5_targets_and_conditional_counters_are_enforced():
    state = GameState(hand=["Expedite"], mana_pool=pool(r=1))
    assert not validate_action(
        state, Action(ActionType.CAST_SPELL, "Expedite", mana_cost={"R": 1})
    ).accepted
    state.stack.append(
        StackObject("Bear", "spell", lambda s: None, types={"Creature"}, mana_value=2)
    )
    assert not validate_action(
        state,
        Action(
            ActionType.CAST_SPELL,
            "Commit // Memory",
            mana_cost={"generic": 3, "U": 1},
            choice="Commit",
        ),
    ).accepted


def test_phase9f5_combat_uses_power_defenders_and_commander_presence():
    pirate = Permanent(
        "Storm Fleet Sprinter",
        {"Creature"},
        {"Pirate"},
        power=2,
        toughness=2,
        haste=True,
        summoning_sick=False,
    )
    bear = Permanent("Bear", {"Creature"}, set(), power=5, toughness=5, summoning_sick=False)
    state = GameState(battlefield=[pirate, bear], opponent_life=[0, 4, 0])
    state.phase = Phase.COMBAT
    execute_action(
        state, Action(ActionType.DECLARE_ATTACKERS, "attack", (pirate, bear), choice="1")
    )
    execute_action(state, Action(ActionType.COMBAT_DAMAGE, "combat_damage"))
    assert state.opponent_life[1] == -3
    assert state.terminal
    assert state.treasures == 0
    assert not any(e.startswith("breeches_unknown_exiled") for e in state.event_log)


def test_phase9f5_creature_and_artifact_spells_use_stack_and_sba_removes_lethal_damage():
    state = GameState(hand=["Wily Goblin"], mana_pool=pool(r=2))
    execute_action(
        state,
        Action(
            ActionType.CAST_SPELL,
            "Wily Goblin",
            mana_cost={"generic": 1, "R": 1},
            timing="sorcery",
            origin_zone="hand",
        ),
    )
    assert not any(p.name == "Wily Goblin" for p in state.battlefield)
    assert any(obj.name == "Wily Goblin" for obj in state.stack)
    state.resolve_all()
    assert any(p.name == "Wily Goblin" for p in state.battlefield)

    creature = Permanent("Bear", {"Creature"}, power=2, toughness=2, damage=2)
    state = GameState(battlefield=[creature])
    state.check_state_based_actions()
    assert creature not in state.battlefield
    assert "Bear" in state.graveyard


def test_phase9f5_callable_gate_rejects_blocked_missing_wrong_and_placeholder():
    reg = adapter_registry()
    assert validate_executable_coverage(reg) == []
    bad = dict(reg)
    island = bad["Island"]
    bad["Island"] = type(island)(
        **{**{f: getattr(island, f) for f in island.__dataclass_fields__}, "status": "BLOCKED"}
    )
    assert any("blocked adapter" in e for e in validate_executable_coverage(bad))
    bad = dict(reg)
    del bad["Island"]
    assert any("missing adapter" in e for e in validate_executable_coverage(bad))
    bad = dict(reg)
    bad["Island"] = type(island)(
        **{
            **{f: getattr(island, f) for f in island.__dataclass_fields__},
            "execution_handler": None,
        }
    )
    assert any("execution handler" in e for e in validate_executable_coverage(bad))
