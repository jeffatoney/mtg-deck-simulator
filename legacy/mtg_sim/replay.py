"""Replay foundations for Phase 3 event-sourced transitions."""

from __future__ import annotations

from collections.abc import Sequence

from mtg_sim.domain import CardInstanceId, DomainError, Event, GameState, TerminalStatus, Zone


def replay_events(initial: GameState, events: Sequence[Event]) -> GameState:
    """Replay core-domain events without invoking policy code."""
    for event in events:
        if initial.state_hash() != event.before_hash:
            raise DomainError(f"before-hash mismatch at event {event.sequence}")
        if event.event_type == "move_card":
            payload = event.payload
            initial.move_card(
                CardInstanceId(str(payload["card_id"])),
                Zone(str(payload["source"])),
                Zone(str(payload["dest"])),
                str(payload["reason"]),
            )
        elif event.event_type == "terminal":
            initial.terminate(
                TerminalStatus(str(event.payload["status"])), str(event.payload["reason"])
            )
        else:
            raise DomainError(f"unsupported replay event type: {event.event_type}")
        if initial.events[-1].after_hash != event.after_hash:
            raise DomainError(f"after-hash mismatch at event {event.sequence}")
    initial.validate_invariants()
    return initial


def event_log_hash(events: Sequence[Event]) -> str:
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps([event.canonical() for event in events], sort_keys=True).encode()
    ).hexdigest()
