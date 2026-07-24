"""Commit // Memory handling for copied spells in the Phase 9F-5 gate."""

from __future__ import annotations

from . import engine as _engine

_ORIGINAL_COMMIT = _engine.commit
_INSTALLED = False


def commit(
    state: _engine.GameState,
    target: _engine.StackObject | _engine.Permanent,
) -> None:
    """Move real targets normally and make a spell copy cease to exist."""

    if isinstance(target, _engine.StackObject) and target.kind == "copy":
        if target not in state.stack:
            raise _engine.RulesError("Commit spell target must be on stack")
        state.stack.remove(target)
        state.record_event("copy_ceased_to_exist", target.name)
        return
    _ORIGINAL_COMMIT(state, target)


def install() -> None:
    """Install the copied-spell Commit correction once."""

    global _INSTALLED
    if _INSTALLED:
        return
    setattr(_engine, "commit", commit)
    _INSTALLED = True
