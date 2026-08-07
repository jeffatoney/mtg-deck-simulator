"""Secondary paired earliest-access timing artifact for the Phase C pilot.

The primary aggregate remains the pre-registered paired Turn-8 comparison. This
module derives a separate, digest-bound secondary timing artifact from the already
validated immutable shard measurements. Censored arms are never assigned a
synthetic Turn 11 or any other numeric value.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from mtg_measure import GameMeasurement
from mtg_runs.phase_c_artifacts import PhaseCAggregateManifest, load_phase_c_shard
from mtg_runs.phase_c_pairing import PAIRED_GAME_COUNT, build_paired_earliest_access_timing


def _canonical(value: Any) -> bytes:
    normalized = json.loads(
        json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    )
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unavailable or malformed: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _measurement_maps(
    shard_dirs: Sequence[Path],
) -> tuple[dict[str, GameMeasurement], dict[str, GameMeasurement], tuple[str, ...]]:
    standard: dict[str, GameMeasurement] = {}
    exploratory: dict[str, GameMeasurement] = {}
    manifest_shas: list[str] = []
    for shard_dir in shard_dirs:
        manifest, _games, _replays, measurements, _summary = load_phase_c_shard(shard_dir)
        manifest_shas.append(manifest.shard_sha256)
        target = standard if manifest.mode == "STANDARD" else exploratory
        for record in measurements:
            raw_pair_id = record.extra.get("pair_id")
            if raw_pair_id is None:
                continue
            pair_id = str(raw_pair_id)
            if pair_id in target:
                raise ValueError(f"paired timing rejects duplicate {manifest.mode} pair ID")
            target[pair_id] = record
    return standard, exploratory, tuple(sorted(manifest_shas))


def build_phase_c_paired_timing_artifact(
    *,
    shard_root: Path,
    aggregate_root: Path,
    output_root: Path,
) -> Mapping[str, Any]:
    """Validate source bindings and write one immutable secondary timing artifact."""
    aggregate_payload = _load_object(
        aggregate_root / "manifest.json",
        "Phase C aggregate manifest",
    )
    try:
        aggregate_manifest = PhaseCAggregateManifest(**aggregate_payload)
    except (TypeError, ValueError) as exc:
        raise ValueError("Phase C aggregate manifest failed self-validation") from exc
    primary_analysis = _load_object(
        aggregate_root / "paired-turn8-analysis.json",
        "Phase C paired Turn-8 analysis",
    )
    if _digest(primary_analysis) != aggregate_manifest.paired_analysis_sha256:
        raise ValueError("paired timing source Turn-8 analysis digest does not match aggregate")

    shard_dirs = sorted(
        path
        for path in shard_root.rglob("*")
        if path.is_dir() and (path / "manifest.json").is_file()
    )
    if not shard_dirs:
        raise ValueError("paired timing requires immutable Phase C shard artifacts")
    standard, exploratory, shard_manifest_shas = _measurement_maps(shard_dirs)
    if shard_manifest_shas != tuple(sorted(aggregate_manifest.shard_manifest_sha256s)):
        raise ValueError("paired timing shard set differs from the validated aggregate")
    if len(standard) != PAIRED_GAME_COUNT or len(exploratory) != PAIRED_GAME_COUNT:
        raise ValueError(
            "paired timing requires exactly 200 STANDARD and 200 EXPLORATORY pair records"
        )
    if set(standard) != set(exploratory):
        raise ValueError("paired timing STANDARD/EXPLORATORY pair-ID sets differ")

    ordered_pair_ids = sorted(exploratory, key=lambda pair_id: exploratory[pair_id].game_index)
    if [exploratory[pair_id].game_index for pair_id in ordered_pair_ids] != list(
        range(1, PAIRED_GAME_COUNT + 1)
    ):
        raise ValueError("paired timing exploratory pair order is not the exact 1-200 game order")

    rows: list[dict[str, Any]] = []
    for pair_id in ordered_pair_ids:
        standard_record = standard[pair_id]
        exploratory_record = exploratory[pair_id]
        if standard_record.seed != exploratory_record.seed:
            raise ValueError("paired timing records do not share the environment seed")
        if standard_record.extra.get(
            "environment_initial_state_hash"
        ) != exploratory_record.extra.get("environment_initial_state_hash"):
            raise ValueError("paired timing records do not share the initial environment state")
        if standard_record.extra.get("search_seed") is not None:
            raise ValueError("paired timing standard record consumed exploratory search randomness")
        if exploratory_record.extra.get("search_seed") is None:
            raise ValueError("paired timing exploratory record lost its search seed")
        rows.append(
            {
                "pair_id": pair_id,
                "standard_game_index": standard_record.game_index,
                "exploratory_game_index": exploratory_record.game_index,
                "environment_seed": standard_record.seed,
                "standard_earliest_access_turn": standard_record.earliest_legal_attempt_turn,
                "exploratory_earliest_access_turn": exploratory_record.earliest_legal_attempt_turn,
            }
        )

    analysis = build_paired_earliest_access_timing(rows)
    data: dict[str, Any] = {
        "schema_version": "phase-c-paired-timing-artifact-v1",
        "source_aggregate_sha256": aggregate_manifest.aggregation_sha256,
        "source_paired_turn8_analysis_sha256": aggregate_manifest.paired_analysis_sha256,
        "source_shard_manifest_sha256s": shard_manifest_shas,
        "pair_count": PAIRED_GAME_COUNT,
        "analysis": analysis,
        "analysis_sha256": _digest(analysis),
        "pair_records_sha256": str(analysis["pair_records_sha256"]),
        "artifact_sha256": "",
    }
    data["artifact_sha256"] = _digest(
        {key: value for key, value in data.items() if key != "artifact_sha256"}
    )

    output_root.mkdir(parents=True, exist_ok=False)
    path = output_root / "paired-earliest-access-timing.json"
    path.write_bytes(_canonical(data) + b"\n")
    path.chmod(0o444)
    output_root.chmod(0o555)
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Phase C paired earliest-access timing")
    parser.add_argument("--shard-root", type=Path, required=True)
    parser.add_argument("--aggregate-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = build_phase_c_paired_timing_artifact(
        shard_root=args.shard_root,
        aggregate_root=args.aggregate_root,
        output_root=args.output_root,
    )
    print(json.dumps(dict(result), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
