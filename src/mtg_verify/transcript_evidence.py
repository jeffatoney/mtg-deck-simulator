"""Runtime-bound evidence for Phase B golden transcripts.

Golden transcripts may describe either canonical game-state events or explicit
verification/audit evidence.  This module keeps those evidence classes separate,
asserts the transcript's required order as a subsequence of the observed stream,
and optionally writes one immutable evidence record for the transcript gate.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mtg_kernel.models import GameState

ROOT = Path(__file__).resolve().parents[2]
TRANSCRIPT_ROOT = ROOT / "docs/audit/phase-b-golden-transcripts/transcripts"
EVIDENCE_DIR_ENV = "PHASE_B_TRANSCRIPT_EVIDENCE_DIR"
EVIDENCE_SCHEMA = "phase-b-transcript-evidence-v1"
GAME_STATE_EVENTS = "GAME_STATE_EVENTS"
AUDIT_EVIDENCE = "AUDIT_EVIDENCE"
ALLOWED_EVENT_SOURCES = frozenset({GAME_STATE_EVENTS, AUDIT_EVIDENCE})


@dataclass(frozen=True)
class AuditEvent:
    """One verified audit checkpoint produced by a named transcript test."""

    kind: str
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise ValueError("audit evidence kind must be nonempty")


def audit_event(kind: str, **payload: Any) -> AuditEvent:
    """Create an explicit audit checkpoint after its supporting assertion passes."""

    return AuditEvent(kind, dict(payload))


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def evidence_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def subsequence_indexes(
    required: Sequence[str], observed: Sequence[str]
) -> tuple[int, ...] | None:
    """Return indexes proving ``required`` occurs in order within ``observed``."""

    indexes: list[int] = []
    cursor = 0
    for required_kind in required:
        for index in range(cursor, len(observed)):
            if observed[index] == required_kind:
                indexes.append(index)
                cursor = index + 1
                break
        else:
            return None
    return tuple(indexes)


def assert_event_subsequence(
    required: Sequence[str], observed: Sequence[str], *, transcript_id: str
) -> tuple[int, ...]:
    indexes = subsequence_indexes(required, observed)
    if indexes is None:
        raise AssertionError(
            f"{transcript_id} required evidence is not an observed subsequence: "
            f"required={list(required)}, observed={list(observed)}"
        )
    return indexes


def _event_kind(value: object) -> str:
    if isinstance(value, AuditEvent):
        return value.kind
    if isinstance(value, str):
        return value
    kind = getattr(value, "kind", None)
    if not isinstance(kind, str) or not kind.strip():
        raise TypeError(f"transcript evidence item has no event kind: {value!r}")
    return kind


def _event_payload(value: object) -> Mapping[str, Any]:
    if isinstance(value, AuditEvent):
        return value.payload
    payload = getattr(value, "payload", {})
    return payload if isinstance(payload, Mapping) else {}


def _transcript_document(transcript_id: str) -> dict[str, Any]:
    path = TRANSCRIPT_ROOT / f"{transcript_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"transcript is missing: {path}")
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("transcript_id") != transcript_id:
        raise ValueError(f"transcript ID and file name differ: {transcript_id}")
    return dict(document)


def record_transcript_evidence(
    transcript_id: str,
    event_source: str,
    events: Sequence[object],
    *,
    facts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assert and optionally persist one transcript's observed evidence stream."""

    if event_source not in ALLOWED_EVENT_SOURCES:
        raise ValueError(f"unsupported transcript event source: {event_source}")
    document = _transcript_document(transcript_id)
    machine = document.get("machine")
    if not isinstance(machine, Mapping):
        raise ValueError(f"transcript machine contract is missing: {transcript_id}")
    declared_source = str(machine.get("event_source", ""))
    if declared_source != event_source:
        raise AssertionError(
            f"{transcript_id} evidence source differs: "
            f"declared={declared_source!r}, observed={event_source!r}"
        )
    raw_required = machine.get("required_event_order")
    if not isinstance(raw_required, list) or not all(
        isinstance(value, str) and value.strip() for value in raw_required
    ):
        raise ValueError(f"transcript required event order is malformed: {transcript_id}")
    required = tuple(raw_required)
    observed = tuple(_event_kind(event) for event in events)
    matched = assert_event_subsequence(required, observed, transcript_id=transcript_id)
    evidence = {
        "schema_version": EVIDENCE_SCHEMA,
        "transcript_id": transcript_id,
        "event_source": event_source,
        "required_event_order": list(required),
        "observed_event_order": list(observed),
        "matched_indexes": list(matched),
        "matched_events": [observed[index] for index in matched],
        "observed_payloads": [dict(_event_payload(event)) for event in events],
        "facts": dict(facts or {}),
    }
    output_root = os.environ.get(EVIDENCE_DIR_ENV, "").strip()
    if output_root:
        output_dir = Path(output_root)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{transcript_id}.json"
        path.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return evidence


def record_game_state_evidence(
    transcript_id: str,
    state: GameState,
    *,
    facts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return record_transcript_evidence(
        transcript_id,
        GAME_STATE_EVENTS,
        tuple(state.events),
        facts=facts,
    )


def record_audit_evidence(
    transcript_id: str,
    events: Sequence[AuditEvent],
    *,
    facts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return record_transcript_evidence(
        transcript_id,
        AUDIT_EVIDENCE,
        tuple(events),
        facts=facts,
    )
