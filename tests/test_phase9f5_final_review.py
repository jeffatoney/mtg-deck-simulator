from mtg_sim.engine import (
    Action,
    ActionType,
    GameState,
    Permanent,
    StackObject,
    cleanup_step,
    execute_action,
    validate_action,
)


def pool(**values):
    mana = dict.fromkeys(("C", "U", "R", "W", "B", "G"), 0)
    mana.update(values)
    return mana


def cast_commit(target, *, state):
    action = Action(
        ActionType.CAST_SPELL,
        "Commit // Memory",
        targets=(target,) if isinstance(target, Permanent) else (),
        mana_cost={"generic": 3, "U": 1},
        timing="instant",
        origin_zone="hand",
        choice="Commit",
        stack_target=target if isinstance(target, StackObject) else None,
    )
    execute_action(state, action)
    execute_action(state, Action(ActionType.PASS_PRIORITY))


def test_commit_owned_permanent_goes_second_from_top_and_replays_zone_result():
    artifact = Permanent("Sol Ring", {"Artifact"})
    state = GameState(
        hand=["Commit // Memory"],
        library=["Island", "Mountain"],
        battlefield=[artifact],
        mana_pool=pool(C=3, U=1),
    )

    cast_commit(artifact, state=state)

    assert artifact not in state.battlefield
    assert state.library == ["Island", "Sol Ring", "Mountain"]
    assert "commit_second_from_top:Sol Ring" in state.event_log

    replay_artifact = Permanent("Sol Ring", {"Artifact"})
    replay = GameState(
        hand=["Commit // Memory"],
        library=["Island", "Mountain"],
        battlefield=[replay_artifact],
        mana_pool=pool(C=3, U=1),
    )
    cast_commit(replay_artifact, state=replay)
    assert replay.library == state.library
    assert replay.command_zone == state.command_zone
    assert replay.event_log == state.event_log


def test_commit_malcolm_and_breeches_token_copies_cease_without_library_or_command_zone():
    for name in ("Malcolm, Keen-Eyed Navigator", "Breeches, Brazen Plunderer"):
        token = Permanent(name, {"Creature"}, {"Pirate"}, is_token=True, power=2, toughness=2)
        state = GameState(
            hand=["Commit // Memory"],
            library=["Island", "Mountain"],
            battlefield=[token],
            mana_pool=pool(C=3, U=1),
        )
        starting_command_zone = list(state.command_zone)

        cast_commit(token, state=state)

        assert token not in state.battlefield
        assert state.library == ["Island", "Mountain"]
        assert state.command_zone == starting_command_zone
        assert name not in state.graveyard
        assert f"token_ceased_to_exist:{name}" in state.event_log


def test_commit_commanders_use_replacement_or_decline_second_from_top():
    for name in ("Malcolm, Keen-Eyed Navigator", "Breeches, Brazen Plunderer"):
        commander = Permanent(name, {"Creature"}, {"Pirate"}, power=2, toughness=2)
        state = GameState(
            hand=["Commit // Memory"],
            command_zone=[],
            commander_casts={name: 2},
            library=["Island", "Mountain"],
            battlefield=[commander],
            mana_pool=pool(C=3, U=1),
        )
        state.command_zone_replacements[name] = True
        cast_commit(commander, state=state)
        assert state.command_zone == [name]
        assert state.library == ["Island", "Mountain"]
        assert state.commander_casts[name] == 2

        commander = Permanent(name, {"Creature"}, {"Pirate"}, power=2, toughness=2)
        state = GameState(
            hand=["Commit // Memory"],
            command_zone=[],
            library=["Island", "Mountain"],
            battlefield=[commander],
            mana_pool=pool(C=3, U=1),
        )
        state.command_zone_replacements[name] = False
        cast_commit(commander, state=state)
        assert state.command_zone == []
        assert state.library == ["Island", name, "Mountain"]


def test_commit_rejects_opponent_permanent_and_illegal_resolution_does_not_move():
    opponent = Permanent("Opponent Rock", {"Artifact"}, controller=1)
    state = GameState(hand=["Commit // Memory"], battlefield=[opponent], mana_pool=pool(C=3, U=1))
    result = validate_action(
        state,
        Action(
            ActionType.CAST_SPELL,
            "Commit // Memory",
            targets=(opponent,),
            mana_cost={"generic": 3, "U": 1},
            choice="Commit",
        ),
    )
    assert not result.accepted

    artifact = Permanent("Sol Ring", {"Artifact"})
    state = GameState(
        hand=["Commit // Memory"],
        library=["Island"],
        battlefield=[artifact],
        mana_pool=pool(C=3, U=1),
    )
    execute_action(
        state,
        Action(
            ActionType.CAST_SPELL,
            "Commit // Memory",
            targets=(artifact,),
            mana_cost={"generic": 3, "U": 1},
            choice="Commit",
        ),
    )
    state.battlefield.remove(artifact)
    execute_action(state, Action(ActionType.PASS_PRIORITY))
    assert artifact not in state.battlefield
    assert state.library == ["Island"]
    assert "resolution_countered_illegal_targets:Commit // Memory" in state.event_log


def test_cleanup_clears_damage_and_prevents_carryover_but_not_lethal_sba():
    creature = Permanent("Test Creature", {"Creature"}, power=2, toughness=4, damage=3)
    state = GameState(battlefield=[creature])
    state.check_state_based_actions()
    assert creature in state.battlefield
    cleanup_step(state)
    assert creature.damage == 0
    assert "cleanup_damage_removed:Test Creature" in state.event_log
    creature.damage = 1
    state.check_state_based_actions()
    assert creature in state.battlefield

    dead = Permanent("Dead Creature", {"Creature"}, power=2, toughness=4, damage=4)
    lethal = GameState(battlefield=[dead])
    lethal.check_state_based_actions()
    assert dead not in lethal.battlefield


def test_cleanup_clears_every_survivor_and_repeated_cleanup_damage():
    a = Permanent("A", {"Creature"}, power=1, toughness=4, damage=1, enchanted_by_curiosity=True)
    b = Permanent("B", {"Creature"}, power=1, toughness=4, damage=2)
    state = GameState(battlefield=[a, b], library=["x"])
    cleanup_step(state)
    assert state.cleanup_steps == 2
    assert a.damage == b.damage == 0
    assert "cleanup_damage_removed:A,B" in state.event_log


def test_soul_guide_lantern_mandatory_targeting_and_replay():
    state = GameState(hand=["Soul-Guide Lantern"], graveyard=["Opt"], mana_pool=pool(C=1))
    none_result = validate_action(
        state,
        Action(ActionType.CAST_SPELL, "Soul-Guide Lantern", mana_cost={"generic": 1}, choice=None),
    )
    assert not none_result.accepted
    cast = Action(
        ActionType.CAST_SPELL, "Soul-Guide Lantern", mana_cost={"generic": 1}, choice="Opt"
    )
    execute_action(state, cast)
    assert state.graveyard == []
    assert "Opt" in state.exile
    assert "trigger_put_on_stack:Soul-Guide Lantern ETB" in state.event_log

    replay = GameState(hand=["Soul-Guide Lantern"], graveyard=["Opt"], mana_pool=pool(C=1))
    execute_action(replay, cast)
    assert replay.exile == state.exile
    assert replay.event_log == state.event_log


def test_soul_guide_lantern_generates_each_target_and_empty_graveyard_removes_trigger():
    state = GameState(hand=["Soul-Guide Lantern"], graveyard=["Opt", "Ponder"], mana_pool=pool(C=1))
    choices = {
        action.choice
        for action in __import__(
            "mtg_sim.engine", fromlist=["generate_legal_actions"]
        ).generate_legal_actions(state)
        if action.action_type is ActionType.CAST_SPELL
        and action.source_name == "Soul-Guide Lantern"
    }
    assert choices == {"Opt", "Ponder"}

    empty = GameState(hand=["Soul-Guide Lantern"], graveyard=[], mana_pool=pool(C=1))
    execute_action(
        empty,
        Action(ActionType.CAST_SPELL, "Soul-Guide Lantern", mana_cost={"generic": 1}, choice=None),
    )
    assert any(p.name == "Soul-Guide Lantern" for p in empty.battlefield)
    assert "trigger_removed_no_legal_choice:Soul-Guide Lantern" in empty.event_log
    assert not any(
        event == "trigger_put_on_stack:Soul-Guide Lantern ETB" for event in empty.event_log
    )
