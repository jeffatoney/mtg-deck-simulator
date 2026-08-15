"""Deterministic JSON-file encoding that preserves non-string mapping key types."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

_TYPED_MAPPING_TAG = "__typed_mapping_entries_v1__"


def _typed_key(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"type": "bool", "value": value}
    if isinstance(value, int):
        return {"type": "int", "value": value}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    if isinstance(value, str):
        return {"type": "str", "value": value}
    if value is None:
        return {"type": "none", "value": None}
    raise TypeError(f"unsupported JSON mapping key type: {type(value).__name__}")


def typed_json_value(value: Any) -> Any:
    """Project Python audit data into JSON without coercing mapping key types."""

    if isinstance(value, Mapping):
        if all(isinstance(key, str) for key in value):
            return {
                str(key): typed_json_value(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            }
        entries = [
            {"key": _typed_key(key), "value": typed_json_value(item)}
            for key, item in value.items()
        ]
        entries.sort(
            key=lambda entry: json.dumps(
                entry["key"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )
        )
        return {_TYPED_MAPPING_TAG: entries}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [typed_json_value(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, set):
        return [typed_json_value(item) for item in sorted(value, key=repr)]
    raise TypeError(f"unsupported exact JSON value type: {type(value).__name__}")


def serialize_typed_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Return exact deterministic file bytes for a V2 diagnostic JSON artifact."""

    return (
        json.dumps(
            typed_json_value(value),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


__all__ = ["serialize_typed_json_bytes", "typed_json_value"]
