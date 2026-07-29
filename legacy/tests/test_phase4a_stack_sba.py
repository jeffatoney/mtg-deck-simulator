from __future__ import annotations

import pytest

from mtg_sim.engine import (
    Action,
    ActionType,
    GameState,
    Permanent,
    Phase,
    RulesError,
    StackObject,
    activate_glint_horn,
    curiosity_trigger,
    execute_action,
    generate_legal_actions,
    validate_action,
)


def glint_state(**kwargs) -> GameState:
    base = {
        "hand": ["discard"],
        "mana_pool": {"C": 1, "U": 0, "R": 1, "W": 0, "B": 0, "G": 0},
        "battlefield": [
            Permanent("Glint-Horn Buccaneer", {"Creature"}, {"Pirate"}, attacking=True)
        ],
    }
    base.update(kwargs)
    return GameState(**base)


def test_phase4a_stack_lifo_order():
    s = GameState()
    s.stack.append(
        StackObject(
            "bottom", "ability", lambda state: state.record_event("effect", "bottom"), cast=False
        )
    )
    s.stack.append(
        StackObject("top", "ability", lambda state: state.record_event("effect", "top"), cast=False)
    )
    s.resolve_all()
    assert [e for e in s.event_log if e.startswith("effect:")] == ["effect:top", "effect:bottom"]


def test_phase4a_trigger_placement_after_activation_costs_are_paid():
    s = glint_state()
    activate_glint_horn(s, s.battlefield[0])
    assert s.graveyard == ["discard"]
    assert s.event_log.index("cost:discard") < s.event_log.index(
        "trigger_put_on_stack:Glint-Horn discard damage trigger"
    )
    assert [obj.name for obj in s.stack] == [
        "Glint-Horn draw ability",
        "Glint-Horn discard damage trigger",
    ]


def test_phase4a_state_based_actions_not_during_resolution():
    s = GameState(opponent_life=[1, 1, 1])

    def lethal_then_probe(state: GameState) -> None:
        state.opponent_life = [0, 0, 0]
        assert not state.won
        with pytest.raises(RulesError):
            state.check_state_based_actions()

    s.stack.append(StackObject("lethal resolving object", "ability", lethal_then_probe, cast=False))
    s.resolve_top()
    assert s.won


def test_phase4a_empty_library_mandatory_draw():
    s = glint_state(library=[])
    activate_glint_horn(s, s.battlefield[0])
    s.resolve_all()
    assert s.lost and "draw_attempt_empty_library" in s.event_log


def test_phase4a_optional_empty_library_draw_declined():
    s = GameState(library=[])
    curiosity_trigger(s, decline=True)
    s.resolve_all()
    assert not s.lost and "optional_draw_declined" in s.event_log


def test_phase4a_optional_empty_library_draw_accepted():
    s = GameState(library=[])
    curiosity_trigger(s, decline=False)
    s.resolve_all()
    assert s.lost and "state_based_action:empty_library_loss" in s.event_log


def test_phase4a_game_ending_before_lower_stack_object_resolves():
    s = glint_state(library=[], opponent_life=[1, 1, 1])
    activate_glint_horn(s, s.battlefield[0])
    s.resolve_all()
    assert s.won and not s.lost
    assert not any(e == "resolve:Glint-Horn draw ability" for e in s.event_log)


def test_phase4a_illegal_target_rejection():
    target = Permanent("Sol Ring", {"Artifact"})
    s = GameState(hand=["Twinflame"], battlefield=[target])
    action = Action(ActionType.CAST_SPELL, "Twinflame", (target,), timing="sorcery")
    result = validate_action(s, action)
    assert not result.accepted and "requires one legal creature target" in result.errors[0]
    with pytest.raises(RulesError):
        execute_action(s, action)


def test_phase4a_illegal_timing_rejection():
    target = Permanent("Siren", {"Creature"})
    s = GameState(hand=["Twinflame"], battlefield=[target], phase=Phase.COMBAT)
    action = Action(ActionType.CAST_SPELL, "Twinflame", (target,), timing="sorcery")
    assert not validate_action(s, action).accepted
    assert action not in generate_legal_actions(s)


def test_phase4a_no_action_after_terminal_state():
    s = glint_state(lost=True)
    assert generate_legal_actions(s) == []
    with pytest.raises(RulesError):
        execute_action(s, Action(ActionType.ACTIVATE_ABILITY, "Glint-Horn Buccaneer"))
