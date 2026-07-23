from mtg_sim.engine import (
    Action,
    ActionType,
    GameState,
    Permanent,
    Phase,
    StackObject,
    execute_action,
    validate_action,
)
from dataclasses import replace

from mtg_sim.executable_adapters import adapter_registry, validate_executable_coverage


def pool(**kwargs):
    mana = dict.fromkeys(("C", "U", "R", "W", "B", "G"), 0)
    mana.update(kwargs)
    return mana


def spell(name, types, face=None):
    return StackObject(name, "spell", lambda s: None, types=set(types), chosen_face=face)


def test_commit_target_validation_legal_stack_and_permanent_before_costs():
    target = spell("Opt", {"Instant"})
    s = GameState(hand=["Commit // Memory"], stack=[target], mana_pool=pool(U=1, C=3))
    assert validate_action(
        s,
        Action(
            ActionType.CAST_SPELL,
            "Commit // Memory",
            mana_cost={"generic": 3, "U": 1},
            choice="Commit",
            stack_target=target,
        ),
    ).accepted

    artifact = Permanent("Sol Ring", {"Artifact"})
    s = GameState(hand=["Commit // Memory"], battlefield=[artifact], mana_pool=pool(U=1, C=3))
    assert validate_action(
        s,
        Action(
            ActionType.CAST_SPELL,
            "Commit // Memory",
            targets=(artifact,),
            mana_cost={"generic": 3, "U": 1},
            choice="Commit",
        ),
    ).accepted


def test_commit_rejects_land_missing_and_nonbattlefield_targets_before_payment():
    land = Permanent("Island", {"Land"})
    absent = Permanent("Sol Ring", {"Artifact"})
    for action in (
        Action(
            ActionType.CAST_SPELL,
            "Commit // Memory",
            targets=(land,),
            mana_cost={"generic": 3, "U": 1},
            choice="Commit",
        ),
        Action(
            ActionType.CAST_SPELL,
            "Commit // Memory",
            targets=(absent,),
            mana_cost={"generic": 3, "U": 1},
            choice="Commit",
        ),
        Action(
            ActionType.CAST_SPELL,
            "Commit // Memory",
            mana_cost={"generic": 3, "U": 1},
            choice="Commit",
        ),
    ):
        s = GameState(hand=["Commit // Memory"], battlefield=[land], mana_pool=pool(U=1, C=3))
        before = (list(s.hand), dict(s.mana_pool))
        result = validate_action(s, action)
        assert not result.accepted
        assert (list(s.hand), dict(s.mana_pool)) == before


def test_split_card_chosen_faces_drive_stack_type_legality_and_replay_metadata():
    commit = spell("Commit // Memory", {"Instant"}, "Commit")
    memory = spell("Commit // Memory", {"Sorcery"}, "Memory")
    s = GameState(hand=["Dispel"], stack=[commit], mana_pool=pool(U=1))
    assert validate_action(
        s, Action(ActionType.CAST_SPELL, "Dispel", mana_cost={"U": 1}, stack_target=commit)
    ).accepted
    s.stack = [memory]
    assert not validate_action(
        s, Action(ActionType.CAST_SPELL, "Dispel", mana_cost={"U": 1}, stack_target=memory)
    ).accepted
    s.hand = ["Negate"]
    s.mana_pool = pool(U=1, C=1)
    assert validate_action(
        s,
        Action(
            ActionType.CAST_SPELL, "Negate", mana_cost={"generic": 1, "U": 1}, stack_target=memory
        ),
    ).accepted

    target = spell("Opt", {"Instant"})
    s = GameState(hand=["Commit // Memory"], stack=[target], mana_pool=pool(U=1, C=3))
    execute_action(
        s,
        Action(
            ActionType.CAST_SPELL,
            "Commit // Memory",
            mana_cost={"generic": 3, "U": 1},
            choice="Commit",
            stack_target=target,
        ),
    )
    assert s.stack[-1].chosen_face == "Commit"
    assert s.stack[-1].types == {"Instant"}


def test_sentinel_totem_and_soul_guide_lantern_resolve_as_artifacts_with_abilities():
    for name in ("Sentinel Totem", "Soul-Guide Lantern"):
        s = GameState(hand=[name], mana_pool=pool(C=1))
        execute_action(s, Action(ActionType.CAST_SPELL, name, mana_cost={"generic": 1}))
        permanent = s.battlefield[-1]
        assert permanent.name == name
        assert "Artifact" in permanent.types
        action = Action(
            ActionType.ACTIVATE_ABILITY,
            name,
            ability_id="exile_all_graveyards"
            if name == "Sentinel Totem"
            else "exile_opponents_graveyards",
            mana_cost={},
        )
        assert validate_action(s, action).accepted


def test_cascade_bluffs_colorless_and_filter_modes():
    bluffs = Permanent("Cascade Bluffs", {"Land"})
    s = GameState(battlefield=[bluffs], mana_pool=pool())
    execute_action(s, Action(ActionType.ACTIVATE_MANA_ABILITY, "Cascade Bluffs", mana_choice="C"))
    assert s.mana_pool["C"] == 1
    assert bluffs.tapped
    assert not validate_action(
        s, Action(ActionType.ACTIVATE_MANA_ABILITY, "Cascade Bluffs", mana_choice="C")
    ).accepted

    s = GameState(battlefield=[Permanent("Cascade Bluffs", {"Land"})], mana_pool=pool())
    assert not validate_action(
        s, Action(ActionType.ACTIVATE_MANA_ABILITY, "Cascade Bluffs", mana_choice="UR")
    ).accepted
    s.mana_pool["U"] = 1
    execute_action(s, Action(ActionType.ACTIVATE_MANA_ABILITY, "Cascade Bluffs", mana_choice="UR"))
    assert s.mana_pool["U"] == 1 and s.mana_pool["R"] == 1


def test_executable_coverage_rejects_nonexistent_semantic_test_id():
    reg = adapter_registry()
    rec = reg["Opt"]
    reg["Opt"] = replace(rec, integration_test_ids=("tests/test_missing.py::test_nope",))
    assert any("nonexistent" in e for e in validate_executable_coverage(reg))

    reg["Opt"] = replace(rec, integration_test_ids=("SEM-OPT",))
    assert any("generated semantic" in e for e in validate_executable_coverage(reg))


def test_commander_sba_replacement_for_malcolm_and_breeches_tracks_tax_independently():
    for name in ("Malcolm, Keen-Eyed Navigator", "Breeches, Brazen Plunderer"):
        commander = Permanent(name, {"Creature"}, power=2, toughness=2, damage=2)
        s = GameState(battlefield=[commander], command_zone=[], commander_casts={name: 1})
        s.check_state_based_actions()
        assert commander not in s.battlefield
        assert name in s.command_zone
        assert name not in s.graveyard
        assert s.commander_casts[name] == 1
        assert s.command_zone_replacements[name] is True


def test_terminal_combat_damage_stops_before_breeches_and_later_events():
    breeches = Permanent(
        "Breeches, Brazen Plunderer",
        {"Creature"},
        {"Pirate"},
        attacking=True,
        tapped=True,
        power=3,
        toughness=3,
    )
    s = GameState(battlefield=[breeches], opponent_life=[1], phase=Phase.COMBAT)
    execute_action(s, Action(ActionType.COMBAT_DAMAGE, "combat_damage"))
    assert s.won
    assert not s.breeches_unknown_exiled
    assert s.event_log[-1] == "state_based_action:table_win"
    assert all(not event.startswith("breeches_unknown_exiled") for event in s.event_log)
    assert "combat_damage:unblocked" not in s.event_log
