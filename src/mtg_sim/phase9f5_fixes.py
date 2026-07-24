"""Focused Phase 9F-5 follow-up fixes installed over the deck-scoped engine.

The project already uses an installation layer for Phase 5D card behavior.  This
module follows that pattern for the small set of review fixes that must remain
visible to every caller importing :mod:`mtg_sim.engine`.
"""

from __future__ import annotations

from dataclasses import replace

from . import engine as _engine

_CRAWLER = "Psychosis Crawler"
_CASCADE = "Cascade Bluffs"
_FILTER_OUTPUTS = {"UU", "UR", "RR"}

_ORIGINAL_RECORD_EVENT = _engine.GameState.record_event
_ORIGINAL_PERMANENT_FOR_CARD = _engine._permanent_for_card
_ORIGINAL_VALIDATE_ACTION = _engine.validate_action
_ORIGINAL_GENERATE_LEGAL_ACTIONS = _engine.generate_legal_actions
_ORIGINAL_EXECUTE_ACTION = _engine.execute_action
_ORIGINAL_TAP_FOR_MANA = _engine.tap_for_mana
_INSTALLED = False


def _refresh_psychosis_crawler(state: _engine.GameState) -> None:
    """Apply Psychosis Crawler's characteristic-defining power/toughness."""

    hand_size = len(state.hand)
    for permanent in state.battlefield:
        if permanent.name == _CRAWLER:
            permanent.power = hand_size
            permanent.toughness = hand_size


def _record_event(state: _engine.GameState, event_type: str, detail: str = "") -> None:
    # Hand changes in the engine are always paired with typed events. Refreshing
    # here keeps the characteristic-defining ability current after draws,
    # discards, searches, Memory, and normal action resolution.
    _refresh_psychosis_crawler(state)
    _ORIGINAL_RECORD_EVENT(state, event_type, detail)


def _permanent_for_card(name: str) -> _engine.Permanent:
    permanent = _ORIGINAL_PERMANENT_FOR_CARD(name)
    if name == _CRAWLER:
        # The printed */* values are not a static 0/0. They are filled from the
        # controlling player's hand as soon as the permanent enters a game state.
        permanent.power = None
        permanent.toughness = None
    return permanent


def _cascade_result(
    normalized_action: _engine.Action,
    result: _engine.ValidationResult,
    errors: list[str],
) -> _engine.ValidationResult:
    deduped = tuple(dict.fromkeys(errors))
    return _engine.ValidationResult(
        not deduped,
        deduped,
        result.rules_refs,
        normalized_action if not deduped else None,
    )


def validate_action(
    state: _engine.GameState, action: _engine.Action
) -> _engine.ValidationResult:
    result = _ORIGINAL_VALIDATE_ACTION(state, action)
    if not (
        action.action_type is _engine.ActionType.ACTIVATE_MANA_ABILITY
        and action.source_name == _CASCADE
    ):
        return result

    errors = list(result.errors)
    output = action.mana_choice
    input_color = action.choice
    normalized_action = action

    if output == "C":
        if input_color is not None:
            errors.append("Cascade Bluffs colorless mode has no input mana")
    elif output in _FILTER_OUTPUTS:
        if input_color not in {"U", "R"}:
            available_inputs = [
                color for color in ("U", "R") if state.mana_pool.get(color, 0) > 0
            ]
            if input_color is None and len(available_inputs) == 1:
                normalized_action = replace(action, choice=available_inputs[0])
                input_color = available_inputs[0]
            else:
                errors.append("Cascade Bluffs filter action must choose U or R input mana")
        if input_color in {"U", "R"} and state.mana_pool.get(input_color, 0) < 1:
            errors.append(f"Cascade Bluffs selected {input_color} input is unavailable")
    else:
        errors.append("Cascade Bluffs must choose C, UU, UR, or RR")

    return _cascade_result(normalized_action, result, errors)


def tap_for_mana(
    state: _engine.GameState,
    permanent: _engine.Permanent,
    color: str | None = None,
    input_color: str | None = None,
) -> None:
    if permanent.name != _CASCADE:
        _ORIGINAL_TAP_FOR_MANA(state, permanent, color)
        return

    _engine.ensure_not_terminal(state)
    if permanent.tapped:
        raise _engine.RulesError("permanent is already tapped")

    output = color or "C"
    if output == "C":
        if input_color is not None:
            raise _engine.RulesError("Cascade Bluffs colorless mode has no input mana")
        permanent.tapped = True
        state.mana_pool["C"] += 1
        state.record_event("mana_produced", "Cascade Bluffs:input=none:output=C")
        return

    if output not in _FILTER_OUTPUTS:
        raise _engine.RulesError("Cascade Bluffs filter must produce UU, UR, or RR")
    if input_color not in {"U", "R"}:
        raise _engine.RulesError("Cascade Bluffs filter must choose U or R input mana")
    if state.mana_pool.get(input_color, 0) < 1:
        raise _engine.RulesError(f"Cascade Bluffs selected {input_color} input is unavailable")

    state.pay_mana({input_color: 1})
    permanent.tapped = True
    for mana_symbol in output:
        state.mana_pool[mana_symbol] += 1
    state.record_event(
        "mana_produced",
        f"Cascade Bluffs:input={input_color}:output={output}",
    )


def generate_legal_actions(state: _engine.GameState) -> list[_engine.Action]:
    actions = [
        action
        for action in _ORIGINAL_GENERATE_LEGAL_ACTIONS(state)
        if not (
            action.action_type is _engine.ActionType.ACTIVATE_MANA_ABILITY
            and action.source_name == _CASCADE
        )
    ]

    source = next(
        (permanent for permanent in state.battlefield if permanent.name == _CASCADE),
        None,
    )
    if source is None or source.tapped or state.terminal:
        return actions

    candidates = [
        _engine.Action(
            _engine.ActionType.ACTIVATE_MANA_ABILITY,
            _CASCADE,
            mana_choice="C",
        )
    ]
    for input_color in ("U", "R"):
        if state.mana_pool.get(input_color, 0) < 1:
            continue
        for output in ("UU", "UR", "RR"):
            candidates.append(
                _engine.Action(
                    _engine.ActionType.ACTIVATE_MANA_ABILITY,
                    _CASCADE,
                    mana_choice=output,
                    choice=input_color,
                )
            )

    for candidate in candidates:
        if validate_action(state, candidate).accepted:
            actions.append(candidate)
    return actions


def execute_action(state: _engine.GameState, action: _engine.Action) -> None:
    if (
        action.action_type is _engine.ActionType.ACTIVATE_MANA_ABILITY
        and action.source_name == _CASCADE
    ):
        result = validate_action(state, action)
        if not result.accepted:
            raise _engine.RulesError("; ".join(result.errors))
        normalized = result.normalized_action or action
        source = next(
            (permanent for permanent in state.battlefield if permanent.name == _CASCADE),
            None,
        )
        if source is None:
            raise _engine.RulesError("Cascade Bluffs is not on battlefield")
        tap_for_mana(state, source, normalized.mana_choice, normalized.choice)
        state.record_event(
            "action",
            (
                "activate_mana:Cascade Bluffs:"
                f"input={normalized.choice or 'none'}:output={normalized.mana_choice}"
            ),
        )
        return

    _ORIGINAL_EXECUTE_ACTION(state, action)
    _refresh_psychosis_crawler(state)


def install() -> None:
    """Install the focused fixes once for all engine importers."""

    global _INSTALLED
    if _INSTALLED:
        return

    _engine.GameState.record_event = _record_event
    _engine._permanent_for_card = _permanent_for_card
    _engine.validate_action = validate_action
    _engine.tap_for_mana = tap_for_mana
    _engine.generate_legal_actions = generate_legal_actions
    _engine.execute_action = execute_action
    _INSTALLED = True
