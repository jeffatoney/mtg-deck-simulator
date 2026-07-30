"""identity-state-v2.0.0 deterministic canonical state hashing."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from mtg_kernel.models import GameState


def _safe(value: Any) -> Any:
    if isinstance(value, float):
        raise TypeError("floating-point state is outside the Phase A hash schema")
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items() if k not in {"debug_label"}}
    if isinstance(value, (list, tuple, set)):
        values = [_safe(v) for v in value]
        return sorted(values) if isinstance(value, set) else values
    return value


def canonical_state_bytes(state: GameState) -> bytes:
    document = _safe(asdict(state))
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def state_hash(state: GameState) -> str:
    return hashlib.sha256(b"identity-state-v2.0.0\x00" + canonical_state_bytes(state)).hexdigest()
