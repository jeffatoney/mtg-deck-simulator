"""Commit // Memory zone movement corrections for the Phase 9F-5 gate."""

from __future__ import annotations

from . import engine as _engine

_ORIGINAL_COMMIT = _engine.commit
_COMMANDERS = {"Malcolm, Keen-Eyed Navigator", "Breeches, Brazen Plunderer"}
_INSTALLED = False


def _put_second_from_top(library: list[str], card_name: str) -> None:
    insert_at = 1 if library else 0
    library.insert(insert_at, card_name)


def _commit_permanent(state: _engine.GameState, target: _engine.Permanent) -> None:
    if target not in state.battlefield:
        state.record_event("resolution_countered_illegal_targets", "Commit // Memory")
        return
    if "Land" in target.types:
        raise _engine.RulesError("Commit permanent target must be a nonland permanent")
    if target.controller != 0:
        raise _engine.RulesError(
            "Commit cannot target opponent-owned permanents while opponent libraries are unmodeled"
        )

    state.battlefield.remove(target)
    if target.is_token:
        state.record_event("token_ceased_to_exist", target.name)
        return

    if target.name in _COMMANDERS and state.command_zone_replacements.get(target.name, True):
        state.command_zone.append(target.name)
        state.command_zone_replacements[target.name] = True
        state.record_event("command_zone_replacement", target.name)
        return

    _put_second_from_top(state.library, target.name)
    state.record_event("commit_second_from_top", target.name)


def commit(
    state: _engine.GameState,
    target: _engine.StackObject | _engine.Permanent,
) -> None:
    """Resolve Commit without inventing library cards from copies, tokens, or commanders."""

    if isinstance(target, _engine.StackObject) and target.kind == "copy":
        if target not in state.stack:
            raise _engine.RulesError("Commit spell target must be on stack")
        state.stack.remove(target)
        state.record_event("copy_ceased_to_exist", target.name)
        return
    if isinstance(target, _engine.Permanent):
        _commit_permanent(state, target)
        return
    _ORIGINAL_COMMIT(state, target)


def install() -> None:
    """Install the Commit correction once."""

    global _INSTALLED
    if _INSTALLED:
        return
    setattr(_engine, "commit", commit)
    _INSTALLED = True
