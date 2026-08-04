"""Immutable run manifests, deterministic aggregation, and independent replay audit."""

from mtg_runs.manifests import (
    RunManifest,
    SeedAssignment,
    TestEvidence,
    build_manifest,
    load_manifest,
    validate_aggregation,
    write_immutable_run,
)
from mtg_runs.replay_audit import (
    FreshProcessReplayResult,
    replay_in_fresh_process,
    verify_worker_invariance,
)

__all__ = [
    "FreshProcessReplayResult",
    "RunManifest",
    "SeedAssignment",
    "TestEvidence",
    "build_manifest",
    "load_manifest",
    "replay_in_fresh_process",
    "validate_aggregation",
    "verify_worker_invariance",
    "write_immutable_run",
]
