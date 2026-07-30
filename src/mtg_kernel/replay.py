"""Append-only transcript creation, digest validation, and production-engine replay."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from mtg_kernel.errors import ReplayError
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import GameState
from mtg_kernel.serialization import state_from_data

TRANSCRIPT_SCHEMA = "phase-a-replay-v2"


def _json_safe(value: Any) -> Any:
    return json.loads(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        )
    )


def _digest(body: dict[str, Any]) -> str:
    encoded = json.dumps(
        _json_safe(body),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def transcript(state: GameState, *, seed: str = "phase-a") -> dict[str, Any]:
    if state.replay_initial_state is None:
        raise ReplayError("no initial replay state was captured before the first action")
    body: dict[str, Any] = {
        "schema": TRANSCRIPT_SCHEMA,
        "summary": "Replay the recorded choices, payments, targets, and actions through the clean engine.",
        "seed": seed,
        "initial_state": state.replay_initial_state,
        "commands": list(state.replay_commands),
        "actions": [asdict(action) for action in state.actions],
        "choices": [asdict(choice) for choice in state.choices],
        "events": [asdict(event) for event in state.events],
        "zone_changes": [asdict(change) for change in state.zone_changes],
        "rng_streams": {name: asdict(stream) for name, stream in sorted(state.rng_streams.items())},
        "final_state_hash": state_hash(state),
    }
    body = _json_safe(body)
    body["digest"] = _digest(body)
    return body


def validate_replay(expected: dict[str, Any]) -> GameState:
    supplied = dict(expected)
    digest = supplied.pop("digest", None)
    if expected.get("schema") != TRANSCRIPT_SCHEMA:
        raise ReplayError("unsupported replay transcript schema")
    if digest != _digest(supplied):
        raise ReplayError("transcript digest mismatch")
    initial = expected.get("initial_state")
    commands = expected.get("commands")
    if not isinstance(initial, dict) or not isinstance(commands, list):
        raise ReplayError("transcript omits initial state or ordered commands")
    try:
        state = state_from_data(initial)
        from mtg_kernel.engine import GameExecutor

        executor = GameExecutor(state, str(expected.get("seed", "phase-a")), replaying=True)
        for command in commands:
            if not isinstance(command, dict):
                raise ReplayError("replay command is malformed")
            executor.execute_replay_command(command)
        state.replay_initial_state = initial
        state.replay_commands = [dict(command) for command in commands]
        actual = transcript(state, seed=str(expected.get("seed", "phase-a")))
    except ReplayError:
        raise
    except Exception as exc:
        raise ReplayError(f"production replay rejected a recorded command: {exc}") from exc
    if actual != expected:
        raise ReplayError("production replay diverged from the recorded transcript")
    return state
