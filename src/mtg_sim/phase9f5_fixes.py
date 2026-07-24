"""Focused Phase 9F-5 follow-up fixes installed over the deck-scoped engine.

The project already uses an installation layer for Phase 5D card behavior. This
module follows that pattern for the small set of review fixes that must remain
visible to every caller importing :mod:`mtg_sim.engine`.
"""

from __future__ import annotations

from dataclasses import replace

from . import engine as _engine

_CRAWLER = "Psychosis Crawler"
_CASCADE = "Cascade Bluffs"
_COMMIT_MEMORY = "Commit // Memory"
_FILTER_OUTPUTS = {"UU", "UR", "RR"}
_ETB_ARTIFACTS = {"Sentinel Totem", "Soul-Guide Lantern"}

_ORIGINAL_RECORD_EVENT = _engine.GameState.record_event
_ORIGINAL_PERMANENT_FOR_CARD = _engine._permanent_for_card
_ORIGINAL_VALIDATE_ACTION = _engine.validate_action
_ORIGINAL_GENERATE_LEGAL_ACTIONS = _engine.generate_legal_actions
_ORIGINAL_EXECUTE_ACTION = _engine.execute_action
_ORIGINAL_TAP_FOR_MANA = _engine.tap_for_mana
_ORIGINAL_MOVE_TO_GRAVEYARD_OR_COMMAND_ZONE = _engine.move_to_graveyard_or_command_zone
_INSTALLED = False


def _refresh_psychosis_crawler(state: _engine.GameState) -> None:
    """Apply Psychosis Crawler's characteristic-defining power/toughness."""

    hand_size = len(state.hand)
    for permanent in state.battlefield:
        if permanent.name == _CRAWLER:
            permanent.power = hand_size
            permanent.toughness = hand_size


def _record_event(state: _engine.GameState, event_type: str, detail: str = "") -> None:
    # Hand changes in the engine are paired with typed events. Refreshing here
    # keeps the characteristic-defining ability current after draws, discards,
    # searches, Memory, and normal action resolution.
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


def move_to_graveyard_or_command_zone(
    state: _engine.GameState,
    permanent: _engine.Permanent,
    *,
    use_command_zone: bool = True,
) -> None:
    """Never create a command-zone card from a dying commander token copy."""

    _ORIGINAL_MOVE_TO_GRAVEYARD_OR_COMMAND_ZONE(
        state,
        permanent,
        use_command_zone=use_command_zone and not permanent.is_token,
    )


def _validation_result(
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


def _normalize_commit_action(action: _engine.Action) -> _engine.Action:
    """Make the chosen split-card half explicit before normal validation."""

    if (
        action.action_type is _engine.ActionType.CAST_SPELL
        and action.source_name == _COMMIT_MEMORY
        and action.choice is None
        and (action.stack_target is not None or action.targets)
    ):
        return replace(action, choice="Commit")
    return action


def validate_action(state: _engine.GameState, action: _engine.Action) -> _engine.ValidationResult:
    normalized_input = _normalize_commit_action(action)
    result = _ORIGINAL_VALIDATE_ACTION(state, normalized_input)
    errors = list(result.errors)
    normalized_action = result.normalized_action or normalized_input

    if (
        normalized_input.action_type is _engine.ActionType.CAST_SPELL
        and normalized_input.source_name == _COMMIT_MEMORY
    ):
        if normalized_input.choice not in {"Commit", "Memory"}:
            errors.append("Commit // Memory requires an explicit legal chosen half")
        if normalized_input.choice == "Commit":
            for target in normalized_input.targets:
                if target.controller != 0:
                    errors.append(
                        "Commit cannot put an opponent-owned permanent into the simulated player's library"
                    )
        return _validation_result(normalized_action, result, errors)

    if (
        normalized_input.action_type is _engine.ActionType.CAST_SPELL
        and normalized_input.source_name == "Sentinel Totem"
    ):
        if normalized_input.choice is None:
            normalized_action = replace(normalized_action, choice="top")
        elif normalized_input.choice not in {"top", "bottom"}:
            errors.append("Sentinel Totem scry choice must be top or bottom")
        return _validation_result(normalized_action, result, errors)

    if (
        normalized_input.action_type is _engine.ActionType.CAST_SPELL
        and normalized_input.source_name == "Soul-Guide Lantern"
    ):
        if normalized_input.choice is not None and normalized_input.choice not in state.graveyard:
            errors.append("Soul-Guide Lantern ETB target must be a card in a graveyard")
        return _validation_result(normalized_action, result, errors)

    if not (
        normalized_input.action_type is _engine.ActionType.ACTIVATE_MANA_ABILITY
        and normalized_input.source_name == _CASCADE
    ):
        return result

    output = normalized_input.mana_choice
    input_color = normalized_input.choice

    if output == "C":
        if input_color is not None:
            errors.append("Cascade Bluffs colorless mode has no input mana")
    elif output in _FILTER_OUTPUTS:
        if input_color not in {"U", "R"}:
            available_inputs = [color for color in ("U", "R") if state.mana_pool.get(color, 0) > 0]
            if input_color is None and len(available_inputs) == 1:
                normalized_action = replace(normalized_input, choice=available_inputs[0])
                input_color = available_inputs[0]
            else:
                errors.append("Cascade Bluffs filter action must choose U or R input mana")
        if input_color in {"U", "R"} and state.mana_pool.get(input_color, 0) < 1:
            errors.append(f"Cascade Bluffs selected {input_color} input is unavailable")
    else:
        errors.append("Cascade Bluffs must choose C, UU, UR, or RR")

    return _validation_result(normalized_action, result, errors)


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


def _artifact_cast_variants(
    state: _engine.GameState,
    original_actions: list[_engine.Action],
) -> list[_engine.Action]:
    variants: list[_engine.Action] = []
    for card_name in sorted(_ETB_ARTIFACTS):
        base = next(
            (
                action
                for action in original_actions
                if action.action_type is _engine.ActionType.CAST_SPELL
                and action.source_name == card_name
            ),
            None,
        )
        if base is None:
            continue
        choices: tuple[str | None, ...]
        if card_name == "Sentinel Totem":
            choices = ("top", "bottom")
        elif state.graveyard:
            choices = tuple(sorted(set(state.graveyard)))
        else:
            choices = (None,)
        for choice in choices:
            candidate = replace(base, choice=choice)
            if validate_action(state, candidate).accepted:
                variants.append(candidate)
    return variants


def generate_legal_actions(state: _engine.GameState) -> list[_engine.Action]:
    original_actions = _ORIGINAL_GENERATE_LEGAL_ACTIONS(state)
    actions = [
        action
        for action in original_actions
        if not (
            action.action_type is _engine.ActionType.ACTIVATE_MANA_ABILITY
            and action.source_name == _CASCADE
        )
        and not (
            action.action_type is _engine.ActionType.CAST_SPELL
            and action.source_name in _ETB_ARTIFACTS
        )
        and not (
            action.action_type is _engine.ActionType.CAST_SPELL
            and action.source_name == _COMMIT_MEMORY
            and any(target.controller != 0 for target in action.targets)
        )
    ]
    actions.extend(_artifact_cast_variants(state, original_actions))

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


def _execute_etb_artifact(state: _engine.GameState, action: _engine.Action) -> None:
    result = validate_action(state, action)
    if not result.accepted:
        raise _engine.RulesError("; ".join(result.errors))
    normalized = result.normalized_action or action
    assert normalized.source_name is not None
    if normalized.origin_zone not in {None, "hand"} or normalized.source_name not in state.hand:
        raise _engine.RulesError(f"{normalized.source_name} must be cast from hand")

    state.hand.remove(normalized.source_name)
    state.pay_mana(normalized.mana_cost or {})
    state.record_event("action", f"cast:{normalized.source_name}:from:hand")
    state.battlefield.append(_permanent_for_card(normalized.source_name))
    state.record_event("resolve", normalized.source_name)
    state.record_event("trigger_detected", f"{normalized.source_name}:enters_the_battlefield")

    if normalized.source_name == "Sentinel Totem":
        if state.library and normalized.choice == "bottom":
            state.library.append(state.library.pop(0))
        state.record_event("scry", f"Sentinel Totem:{normalized.choice or 'top'}")
    elif normalized.choice is not None and normalized.choice in state.graveyard:
        state.graveyard.remove(normalized.choice)
        state.exile.append(normalized.choice)
        state.record_event("exile_graveyard_card", normalized.choice)
    else:
        state.record_event("trigger_no_legal_target", "Soul-Guide Lantern")

    state.would_receive_priority()


def execute_action(state: _engine.GameState, action: _engine.Action) -> None:
    normalized_action = _normalize_commit_action(action)
    if (
        normalized_action.action_type is _engine.ActionType.CAST_SPELL
        and normalized_action.source_name in _ETB_ARTIFACTS
    ):
        _execute_etb_artifact(state, normalized_action)
        _refresh_psychosis_crawler(state)
        return

    if (
        normalized_action.action_type is _engine.ActionType.ACTIVATE_MANA_ABILITY
        and normalized_action.source_name == _CASCADE
    ):
        result = validate_action(state, normalized_action)
        if not result.accepted:
            raise _engine.RulesError("; ".join(result.errors))
        normalized = result.normalized_action or normalized_action
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

    _ORIGINAL_EXECUTE_ACTION(state, normalized_action)
    _refresh_psychosis_crawler(state)


def install() -> None:
    """Install the focused fixes once for all engine importers."""

    global _INSTALLED
    if _INSTALLED:
        return

    setattr(_engine.GameState, "record_event", _record_event)
    setattr(_engine, "_permanent_for_card", _permanent_for_card)
    setattr(_engine, "move_to_graveyard_or_command_zone", move_to_graveyard_or_command_zone)
    setattr(_engine, "validate_action", validate_action)
    setattr(_engine, "tap_for_mana", tap_for_mana)
    setattr(_engine, "generate_legal_actions", generate_legal_actions)
    setattr(_engine, "execute_action", execute_action)
    _INSTALLED = True
