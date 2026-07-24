from mtg_sim.engine import (
    Action,
    ActionType,
    GameState,
    Permanent,
    execute_action,
    generate_legal_actions,
    validate_action,
)


def mana_pool():
    return {"C": 3, "U": 1, "R": 0, "W": 0, "B": 0, "G": 0}


def test_targeted_commit_action_normalizes_chosen_half_before_stack_creation():
    target = Permanent("Mind Stone", {"Artifact"}, controller=0)
    state = GameState(
        hand=["Commit // Memory"],
        battlefield=[target],
        mana_pool=mana_pool(),
    )
    action = Action(
        ActionType.CAST_SPELL,
        "Commit // Memory",
        targets=(target,),
        mana_cost={"generic": 3, "U": 1},
        timing="instant",
        origin_zone="hand",
    )

    validation = validate_action(state, action)
    assert validation.accepted
    assert validation.normalized_action is not None
    assert validation.normalized_action.choice == "Commit"

    execute_action(state, action)
    assert state.stack[-1].chosen_face == "Commit"
    assert state.stack[-1].types == {"Instant"}


def test_commit_rejects_opponent_owned_permanent_without_moving_card_or_paying_mana():
    target = Permanent("Opponent Rock", {"Artifact"}, controller=1)
    state = GameState(
        hand=["Commit // Memory"],
        battlefield=[target],
        mana_pool=mana_pool(),
    )
    before_pool = dict(state.mana_pool)
    action = Action(
        ActionType.CAST_SPELL,
        "Commit // Memory",
        targets=(target,),
        mana_cost={"generic": 3, "U": 1},
        timing="instant",
        origin_zone="hand",
        choice="Commit",
    )

    validation = validate_action(state, action)
    assert not validation.accepted
    assert any("opponent-owned permanent" in error for error in validation.errors)
    assert "Commit // Memory" in state.hand
    assert state.mana_pool == before_pool

    generated = [
        candidate
        for candidate in generate_legal_actions(state)
        if candidate.source_name == "Commit // Memory"
        and candidate.targets == (target,)
    ]
    assert generated == []
