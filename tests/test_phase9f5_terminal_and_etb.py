from mtg_sim.engine import (
    ActionType,
    GameState,
    Permanent,
    execute_action,
    generate_legal_actions,
)


def mana_pool(**values):
    pool = dict.fromkeys(("C", "U", "R", "W", "B", "G"), 0)
    pool.update(values)
    return pool


def test_dying_commander_token_does_not_create_command_zone_card():
    token = Permanent(
        "Malcolm, Keen-Eyed Navigator",
        {"Creature"},
        {"Pirate"},
        is_token=True,
        power=2,
        toughness=2,
        damage=2,
    )
    state = GameState(battlefield=[token])
    original_command_zone = list(state.command_zone)

    state.check_state_based_actions()

    assert state.command_zone == original_command_zone
    assert token not in state.battlefield
    assert "Malcolm, Keen-Eyed Navigator" not in state.graveyard
    assert "token_ceased_to_exist:Malcolm, Keen-Eyed Navigator" in state.event_log


def test_sentinel_totem_resolves_as_artifact_and_executes_scry_choice():
    state = GameState(
        hand=["Sentinel Totem"],
        library=["Opt", "Island"],
        mana_pool=mana_pool(C=1),
    )
    actions = [
        action
        for action in generate_legal_actions(state)
        if action.action_type is ActionType.CAST_SPELL
        and action.source_name == "Sentinel Totem"
    ]
    bottom = next(action for action in actions if action.choice == "bottom")

    execute_action(state, bottom)

    permanent = next(card for card in state.battlefield if card.name == "Sentinel Totem")
    assert "Artifact" in permanent.types
    assert state.library == ["Island", "Opt"]
    assert "scry:Sentinel Totem:bottom" in state.event_log


def test_soul_guide_lantern_resolves_as_artifact_and_exiles_chosen_card():
    state = GameState(
        hand=["Soul-Guide Lantern"],
        graveyard=["Opt"],
        mana_pool=mana_pool(C=1),
    )
    action = next(
        candidate
        for candidate in generate_legal_actions(state)
        if candidate.action_type is ActionType.CAST_SPELL
        and candidate.source_name == "Soul-Guide Lantern"
        and candidate.choice == "Opt"
    )

    execute_action(state, action)

    permanent = next(card for card in state.battlefield if card.name == "Soul-Guide Lantern")
    assert "Artifact" in permanent.types
    assert "Opt" not in state.graveyard
    assert "Opt" in state.exile
    assert "exile_graveyard_card:Opt" in state.event_log
