"""Append-only transcript integrity and replay comparison."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any, Callable

from mtg_kernel.errors import ReplayError
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import GameState


def transcript(state: GameState) -> dict[str, Any]:
    body = {
        "schema": "phase-a-replay-v1",
        "actions": [asdict(a) for a in state.actions],
        "choices": [asdict(c) for c in state.choices],
        "events": [asdict(e) for e in state.events],
        "zone_changes": [asdict(z) for z in state.zone_changes],
        "rng_positions": state.rng_positions,
        "final_state_hash": state_hash(state),
    }
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
    body["digest"] = hashlib.sha256(encoded).hexdigest()
    return body


def validate_replay(expected: dict[str, Any], execute: Callable[[], GameState]) -> GameState:
    supplied = dict(expected)
    digest = supplied.pop("digest", None)
    encoded = json.dumps(supplied, sort_keys=True, separators=(",", ":"), default=str).encode()
    if digest != hashlib.sha256(encoded).hexdigest():
        raise ReplayError("transcript digest mismatch")
    replayed = execute()
    actual = transcript(replayed)
    if actual != expected:
        raise ReplayError("production replay diverged")
    return replayed
