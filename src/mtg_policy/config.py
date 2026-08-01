"""Immutable, hash-verified policy configuration loading."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
POLICIES = ROOT / "configs/policies.yaml"
SEEDS = ROOT / "configs/policy_seeds.json"

REQUIRED_AXES = {
    "mulligan_style",
    "development_plan",
    "malcolm_vs_mana_rock",
    "breeches_timing",
    "tutor_priority",
    "combo_priority",
    "protection_plan",
    "attempt_timing",
    "velocity_plan",
    "muddle_use",
    "glint_horn_use",
}


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    copy = {key: value for key, value in payload.items() if key != "config_hash"}
    encoded = json.dumps(copy, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class PolicyBundle:
    policy_config_id: str
    values: Mapping[str, Any]
    config_hash: str

    def value(self, name: str) -> Any:
        return self.values[name]


@dataclass(frozen=True)
class SeedSplit:
    discovery: tuple[int, ...]
    validation: tuple[int, ...]


def load_policy_matrix(path: Path | None = None) -> tuple[PolicyBundle, ...]:
    source = path or POLICIES
    payload = json.loads(source.read_text(encoding="utf-8"))
    policies = payload.get("policies")
    if not isinstance(policies, list) or not policies:
        raise ValueError("policy matrix is empty")
    if payload.get("full_factorial_run") is not False:
        raise ValueError("Phase B policy screening must not claim a full-factorial run")

    result: list[PolicyBundle] = []
    ids: set[str] = set()
    for raw in policies:
        if not isinstance(raw, dict):
            raise ValueError("policy bundle must be an object")
        policy_id = str(raw.get("policy_config_id", "")).strip()
        if not policy_id or policy_id in ids:
            raise ValueError(f"invalid or duplicate policy_config_id: {policy_id!r}")
        ids.add(policy_id)
        missing = REQUIRED_AXES - raw.keys()
        if missing:
            raise ValueError(f"policy {policy_id} misses axes {sorted(missing)}")
        if raw.get("documented_before_results") is not True:
            raise ValueError(f"policy {policy_id} was not documented before results")
        if raw.get("validation_seed_influence_allowed") is not False:
            raise ValueError(f"policy {policy_id} permits validation-seed influence")
        expected = _canonical_hash(raw)
        recorded = str(raw.get("config_hash", ""))
        if recorded != expected:
            raise ValueError(f"policy {policy_id} config_hash mismatch")
        result.append(PolicyBundle(policy_id, _freeze(dict(raw)), recorded))
    return tuple(result)


def load_seed_split(path: Path | None = None) -> SeedSplit:
    payload = json.loads((path or SEEDS).read_text(encoding="utf-8"))
    discovery = tuple(int(value) for value in payload["discovery_seeds"])
    validation = tuple(int(value) for value in payload["validation_seeds"])
    if len(discovery) != 300 or len(validation) != 200:
        raise ValueError("policy seeds must preserve the precommitted 300/200 split")
    if len(set(discovery)) != len(discovery) or len(set(validation)) != len(validation):
        raise ValueError("policy seed lists contain duplicates")
    if set(discovery).intersection(validation):
        raise ValueError("discovery and validation seeds overlap")
    return SeedSplit(discovery, validation)
