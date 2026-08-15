"""Handle-free public semantic action boundary for strategic policy ranking."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from mtg_policy.broker_core import ObservedAction

_PRIVATE_METADATA_KEYS = frozenset(
    {
        "arguments",
        "broker_arguments",
        "card_instance_id",
        "card_instance_ids",
        "full_state_hash",
        "hidden_library_order",
        "hidden_rng_state",
        "object_id",
        "object_ids",
        "rng_state",
        "state_hash",
    }
)


def _is_private_metadata_key(key: str) -> bool:
    lowered = key.lower()
    return (
        lowered in _PRIVATE_METADATA_KEYS
        or lowered.endswith("_object_id")
        or lowered.endswith("_object_ids")
        or lowered.endswith("_instance_id")
        or lowered.endswith("_instance_ids")
        or lowered.endswith("_state_hash")
        or lowered.endswith("_rng_state")
    )


def _canonical_public_value(value: Any, *, key: str | None = None) -> Any:
    """Return JSON-safe public data and fail closed on private execution metadata."""

    if key is not None and _is_private_metadata_key(key):
        raise ValueError(f"public action metadata exposes private field: {key}")
    if isinstance(value, Mapping):
        return {
            str(item_key): _canonical_public_value(item_value, key=str(item_key))
            for item_key, item_value in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_canonical_public_value(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise ValueError(f"public action metadata contains unsupported value: {type(value).__name__}")


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True, order=True)
class PublicActionKey:
    """Canonical total-order key containing only policy-visible action semantics."""

    canonical_json: str

    def __str__(self) -> str:
        return self.canonical_json


@dataclass(frozen=True)
class PolicyActionView:
    """Handle-free action view consumed by all strategic ranking code."""

    key: PublicActionKey
    kind: str
    identity: str | None
    mana_value: int
    tags: tuple[str, ...]
    target_count: int
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class PublicActionClass:
    """One public equivalence class, without any opaque execution capability."""

    key: PublicActionKey
    action: PolicyActionView
    representative_count: int


def policy_action_view(action: ObservedAction) -> PolicyActionView:
    """Project a broker action into the positive public-policy boundary.

    Public target/source handles contained in metadata are intentionally retained:
    they are part of the observation surface and may distinguish publicly different
    actions. The broker action capability handle is intentionally never copied.
    """

    metadata = _canonical_public_value(action.metadata)
    tags = tuple(sorted(str(tag) for tag in action.tags))
    payload = {
        "identity": action.identity,
        "kind": action.kind,
        "mana_value": int(action.mana_value),
        "metadata": metadata,
        "tags": tags,
        "target_count": int(action.target_count),
    }
    canonical_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return PolicyActionView(
        PublicActionKey(canonical_json),
        str(action.kind),
        action.identity,
        int(action.mana_value),
        tags,
        int(action.target_count),
        _freeze(metadata),
    )


def public_action_classes(actions: Sequence[ObservedAction]) -> tuple[PublicActionClass, ...]:
    """Collapse broker candidates into public semantic equivalence classes."""

    grouped: dict[PublicActionKey, tuple[PolicyActionView, int]] = {}
    for action in actions:
        view = policy_action_view(action)
        existing = grouped.get(view.key)
        if existing is None:
            grouped[view.key] = (view, 1)
        else:
            grouped[view.key] = (existing[0], existing[1] + 1)
    return tuple(
        PublicActionClass(key, view, count)
        for key, (view, count) in sorted(grouped.items(), key=lambda item: item[0])
    )


def resolve_selected_action_handle(
    actions: Sequence[ObservedAction], selected_key: PublicActionKey
) -> str:
    """Resolve an already-selected public class to an opaque execution capability.

    This is the only policy-layer adapter allowed to inspect ``ObservedAction.handle``.
    Representative choice occurs strictly after strategic selection. Multiple
    representatives are legal only when they share the complete public action key.
    """

    handles = sorted(
        action.handle for action in actions if policy_action_view(action).key == selected_key
    )
    if not handles:
        raise ValueError("selected public action class is no longer available")
    return handles[0]


__all__ = [
    "PolicyActionView",
    "PublicActionClass",
    "PublicActionKey",
    "policy_action_view",
    "public_action_classes",
    "resolve_selected_action_handle",
]
