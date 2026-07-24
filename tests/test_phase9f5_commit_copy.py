from mtg_sim.engine import (
    Action,
    ActionType,
    GameState,
    StackObject,
    execute_action,
)


def test_commit_makes_targeted_spell_copy_cease_instead_of_entering_library():
    copied_spell = StackObject(
        "Copy of Twinflame",
        "copy",
        lambda _state: None,
        cast=False,
    )
    state = GameState(
        hand=["Commit // Memory"],
        library=["Island", "Mountain"],
        stack=[copied_spell],
        mana_pool={"C": 3, "U": 1, "R": 0, "W": 0, "B": 0, "G": 0},
    )
    action = Action(
        ActionType.CAST_SPELL,
        "Commit // Memory",
        mana_cost={"generic": 3, "U": 1},
        timing="instant",
        origin_zone="hand",
        choice="Commit",
        stack_target=copied_spell,
    )

    execute_action(state, action)
    execute_action(state, Action(ActionType.PASS_PRIORITY))

    assert copied_spell not in state.stack
    assert "Copy of Twinflame" not in state.library
    assert state.library == ["Island", "Mountain"]
    assert "copy_ceased_to_exist:Copy of Twinflame" in state.event_log
