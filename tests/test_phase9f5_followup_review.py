from dataclasses import replace

from mtg_sim.engine import (
    Action,
    ActionType,
    GameState,
    Permanent,
    execute_action,
    generate_legal_actions,
    validate_action,
)
from mtg_sim.executable_adapters import (
    adapter_registry,
    collected_pytest_node_ids,
    validate_executable_coverage,
)


def pool(**kwargs):
    mana = dict.fromkeys(("C", "U", "R", "W", "B", "G"), 0)
    mana.update(kwargs)
    return mana


def test_psychosis_crawler_uses_dynamic_hand_size_and_zero_toughness_sba():
    crawler = Permanent(
        "Psychosis Crawler",
        {"Artifact", "Creature"},
        power=0,
        toughness=0,
    )
    state = GameState(
        hand=["Island", "Mountain"],
        library=["Opt"],
        battlefield=[crawler],
    )
    state.record_event("fixture_ready")
    assert (crawler.power, crawler.toughness) == (2, 2)

    state.draw(1)
    assert (crawler.power, crawler.toughness) == (3, 3)
    assert state.opponent_life == [39, 39, 39]
    assert "life_lost:Psychosis Crawler:1" in state.event_log
    assert not any(
        event.startswith("noncombat_damage:Psychosis Crawler")
        for event in state.event_log
    )

    state.hand.pop()
    state.record_event("discard", "one")
    assert (crawler.power, crawler.toughness) == (2, 2)

    state.hand.clear()
    state.check_state_based_actions()
    assert crawler not in state.battlefield
    assert "Psychosis Crawler" in state.graveyard


def test_cascade_bluffs_generates_explicit_input_output_branches():
    bluffs = Permanent("Cascade Bluffs", {"Land"})
    state = GameState(battlefield=[bluffs], mana_pool=pool(U=1, R=1))
    actions = [
        action
        for action in generate_legal_actions(state)
        if action.action_type is ActionType.ACTIVATE_MANA_ABILITY
        and action.source_name == "Cascade Bluffs"
    ]

    assert any(action.mana_choice == "C" and action.choice is None for action in actions)
    assert {
        (action.choice, action.mana_choice)
        for action in actions
        if action.mana_choice != "C"
    } == {
        ("U", "UU"),
        ("U", "UR"),
        ("U", "RR"),
        ("R", "UU"),
        ("R", "UR"),
        ("R", "RR"),
    }


def test_cascade_bluffs_spends_selected_input_and_records_it():
    state = GameState(
        battlefield=[Permanent("Cascade Bluffs", {"Land"})],
        mana_pool=pool(U=1, R=1),
    )
    action = Action(
        ActionType.ACTIVATE_MANA_ABILITY,
        "Cascade Bluffs",
        mana_choice="RR",
        choice="R",
    )
    assert validate_action(state, action).accepted
    execute_action(state, action)
    assert state.mana_pool["U"] == 1
    assert state.mana_pool["R"] == 2
    assert any(
        "Cascade Bluffs:input=R:output=RR" in event
        for event in state.event_log
    )

    state = GameState(
        battlefield=[Permanent("Cascade Bluffs", {"Land"})],
        mana_pool=pool(U=1, R=1),
    )
    execute_action(
        state,
        Action(
            ActionType.ACTIVATE_MANA_ABILITY,
            "Cascade Bluffs",
            mana_choice="RR",
            choice="U",
        ),
    )
    assert state.mana_pool["U"] == 0
    assert state.mana_pool["R"] == 3


def test_cascade_bluffs_colorless_mode_needs_no_input_and_filter_needs_choice():
    state = GameState(
        battlefield=[Permanent("Cascade Bluffs", {"Land"})],
        mana_pool=pool(),
    )
    actions = [
        action
        for action in generate_legal_actions(state)
        if action.source_name == "Cascade Bluffs"
    ]
    assert [(action.choice, action.mana_choice) for action in actions] == [(None, "C")]
    assert not validate_action(
        state,
        Action(
            ActionType.ACTIVATE_MANA_ABILITY,
            "Cascade Bluffs",
            mana_choice="UR",
        ),
    ).accepted


def test_executable_coverage_validates_complete_collected_pytest_node_id():
    collected, collection_error = collected_pytest_node_ids()
    assert collection_error is None
    real_node = (
        "tests/test_phase9f4_creatures_combos_coverage.py::"
        "test_every_unique_card_generates_validated_executable_replayable_event[Opt]"
    )
    assert real_node in collected

    registry = adapter_registry()
    original = registry["Opt"]

    registry["Opt"] = replace(
        original,
        integration_test_ids=(
            "tests/test_phase9f4_creatures_combos_coverage.py::test_no_such_node",
        ),
    )
    assert any(
        "nonexistent collected pytest node" in error
        for error in validate_executable_coverage(registry)
    )

    registry["Opt"] = replace(
        original,
        integration_test_ids=(
            "tests/test_phase9f4_creatures_combos_coverage.py::"
            "test_every_unique_card_generates_validated_executable_replayable_event"
            "[not-a-real-parameter]",
        ),
    )
    assert any(
        "nonexistent collected pytest node" in error
        for error in validate_executable_coverage(registry)
    )
