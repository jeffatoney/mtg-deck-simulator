"""Immutable, identity-bound Phase C pilot shard and aggregate artifacts.

The serializer is deliberately separate from execution authorization.  Tests and
technical smokes may exercise these validators with non-pilot records, but the
production shard writer accepts only records created after the Phase C activation
gate has passed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from mtg_runs.phase_c_pairing import (
    PAIRED_GAME_COUNT,
    build_paired_turn8_analysis,
)

from mtg_measure import (
    CardMeasurement,
    ComboMeasurement,
    DivergenceMeasurement,
    GameMeasurement,
    OpeningHandMeasurement,
    aggregate_measurements,
)


def _canonical(value: Any) -> bytes:
    # Normalize integer mapping keys and tuples through JSON before sorting so a
    # value has the same digest before and after it is written/read as JSON.
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


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _is_git_oid(value: str) -> bool:
    return len(value) == 40 and all(char in "0123456789abcdef" for char in value)


def _require_sha256(label: str, value: str) -> None:
    if not _is_sha256(value):
        raise ValueError(f"{label} must be a lowercase 64-character SHA-256")


def _require_git_oid(label: str, value: str) -> None:
    if not _is_git_oid(value):
        raise ValueError(f"{label} must be a lowercase 40-character Git object ID")


@dataclass(frozen=True)
class PhaseCGameArtifact:
    schema_version: str
    mode: str
    game_index: int
    seed: int
    technical_game_sha256: str
    replay_file_sha256: str
    replay_digest: str
    measurement_sha256: str
    final_state_hash: str
    terminal_status: str
    pilot_authorized: bool

    def __post_init__(self) -> None:
        if self.schema_version != "phase-c-pilot-game-artifact-v1":
            raise ValueError("unsupported Phase C game-artifact schema")
        if self.mode not in {"STANDARD", "EXPLORATORY"}:
            raise ValueError("Phase C game-artifact mode is invalid")
        if self.game_index < 1:
            raise ValueError("Phase C game index must be positive")
        for label, value in (
            ("technical game digest", self.technical_game_sha256),
            ("replay file digest", self.replay_file_sha256),
            ("replay transcript digest", self.replay_digest),
            ("measurement digest", self.measurement_sha256),
            ("final state hash", self.final_state_hash),
        ):
            _require_sha256(label, value)
        if not self.pilot_authorized:
            raise ValueError("production Phase C game artifacts must be explicitly authorized")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PhaseCShardManifest:
    schema_version: str
    mode: str
    shard_index: int
    shard_count: int
    first_game_index: int
    last_game_index: int
    seeds: tuple[int, ...]
    pair_ids: tuple[str | None, ...]
    paired_standard_game_indexes: tuple[int | None, ...]
    search_seeds: tuple[int | None, ...]
    implementation_commit: str
    implementation_tree: str
    activation_commit: str
    locked_config_sha256: str
    workflow_sha256: str
    approval_record_sha256: str
    policy_config_id: str
    policy_config_sha256: str
    evaluator_snapshot_id: str
    evaluator_snapshot_sha256: str
    learning_plan_sha256: str
    seed_sha256: str
    pairing_sha256: str
    search_seed_sha256: str
    technical_games_sha256: str
    game_records_sha256: str
    replay_bundle_sha256: str
    measurement_sha256: str
    summary_sha256: str
    production_decision_layer_depth: int
    pilot_authorized: bool
    shard_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != "phase-c-pilot-shard-manifest-v2":
            raise ValueError("unsupported Phase C shard-manifest schema")
        if self.mode not in {"STANDARD", "EXPLORATORY"}:
            raise ValueError("Phase C shard mode is invalid")
        if self.shard_count < 1 or not (0 <= self.shard_index < self.shard_count):
            raise ValueError("Phase C shard index/count is invalid")
        if self.first_game_index < 1 or self.last_game_index < self.first_game_index:
            raise ValueError("Phase C shard game-index range is invalid")
        if len(self.seeds) != self.last_game_index - self.first_game_index + 1:
            raise ValueError("Phase C shard seed count does not match its game-index range")
        if len(self.seeds) != len(set(self.seeds)):
            raise ValueError("Phase C shard contains duplicate seeds")
        if not (
            len(self.pair_ids)
            == len(self.paired_standard_game_indexes)
            == len(self.search_seeds)
            == len(self.seeds)
        ):
            raise ValueError("Phase C shard pairing metadata length mismatch")
        nonempty_pair_ids = [value for value in self.pair_ids if value is not None]
        if len(nonempty_pair_ids) != len(set(nonempty_pair_ids)):
            raise ValueError("Phase C shard contains duplicate pair IDs")
        if any(
            value is not None
            and (len(value) != 24 or any(char not in "0123456789abcdef" for char in value))
            for value in self.pair_ids
        ):
            raise ValueError("Phase C pair IDs must be lowercase 24-character hex values")
        if self.mode == "STANDARD" and any(value is not None for value in self.search_seeds):
            raise ValueError("standard shard cannot contain exploratory search seeds")
        if self.mode == "EXPLORATORY" and (
            any(value is None for value in self.pair_ids)
            or any(value is None for value in self.paired_standard_game_indexes)
            or any(value is None for value in self.search_seeds)
        ):
            raise ValueError("exploratory shard requires complete pairing/search metadata")
        for label, value in (
            ("implementation commit", self.implementation_commit),
            ("implementation tree", self.implementation_tree),
            ("activation commit", self.activation_commit),
        ):
            _require_git_oid(label, value)
        for label, value in (
            ("locked config digest", self.locked_config_sha256),
            ("workflow digest", self.workflow_sha256),
            ("approval digest", self.approval_record_sha256),
            ("policy config digest", self.policy_config_sha256),
            ("evaluator digest", self.evaluator_snapshot_sha256),
            ("learning-plan digest", self.learning_plan_sha256),
            ("seed digest", self.seed_sha256),
            ("pairing digest", self.pairing_sha256),
            ("search-seed digest", self.search_seed_sha256),
            ("technical-game digest", self.technical_games_sha256),
            ("game-record digest", self.game_records_sha256),
            ("replay-bundle digest", self.replay_bundle_sha256),
            ("measurement digest", self.measurement_sha256),
            ("summary digest", self.summary_sha256),
            ("shard digest", self.shard_sha256),
        ):
            _require_sha256(label, value)
        if not self.policy_config_id or not self.evaluator_snapshot_id:
            raise ValueError("Phase C shard omits policy/evaluator identity")
        expected_depth = 0 if self.mode == "STANDARD" else 1
        if self.production_decision_layer_depth != expected_depth:
            raise ValueError("Phase C shard reports the wrong production decision-layer depth")
        if not self.pilot_authorized:
            raise ValueError("production Phase C shard manifests must be explicitly authorized")
        expected = _digest(self.to_dict(include_shard_sha=False))
        if self.shard_sha256 != expected:
            raise ValueError("Phase C shard manifest digest does not match its content")

    def to_dict(self, *, include_shard_sha: bool = True) -> dict[str, Any]:
        value = asdict(self)
        if not include_shard_sha:
            value.pop("shard_sha256", None)
        return value


@dataclass(frozen=True)
class PhaseCAggregateManifest:
    schema_version: str
    implementation_commit: str
    implementation_tree: str
    activation_commit: str
    locked_config_sha256: str
    workflow_sha256: str
    approval_record_sha256: str
    standard_game_count: int
    exploratory_game_count: int
    standard_seed_sha256: str
    exploratory_seed_sha256: str
    exploratory_search_seed_sha256: str
    pair_assignment_sha256: str
    paired_game_count: int
    paired_analysis_sha256: str
    standard_shard_count: int
    exploratory_shard_count: int
    standard_summary_sha256: str
    exploratory_summary_sha256: str
    shard_manifest_sha256s: tuple[str, ...]
    pilot_authorized: bool
    aggregation_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != "phase-c-pilot-aggregate-manifest-v2":
            raise ValueError("unsupported Phase C aggregate schema")
        for label, value in (
            ("implementation commit", self.implementation_commit),
            ("implementation tree", self.implementation_tree),
            ("activation commit", self.activation_commit),
        ):
            _require_git_oid(label, value)
        for label, value in (
            ("locked config digest", self.locked_config_sha256),
            ("workflow digest", self.workflow_sha256),
            ("approval digest", self.approval_record_sha256),
            ("standard seed digest", self.standard_seed_sha256),
            ("exploratory seed digest", self.exploratory_seed_sha256),
            ("exploratory search seed digest", self.exploratory_search_seed_sha256),
            ("pair assignment digest", self.pair_assignment_sha256),
            ("paired analysis digest", self.paired_analysis_sha256),
            ("standard summary digest", self.standard_summary_sha256),
            ("exploratory summary digest", self.exploratory_summary_sha256),
            ("aggregate digest", self.aggregation_sha256),
        ):
            _require_sha256(label, value)
        if any(not _is_sha256(value) for value in self.shard_manifest_sha256s):
            raise ValueError("aggregate contains a non-SHA-256 shard manifest digest")
        if self.standard_game_count != 500 or self.exploratory_game_count != 200:
            raise ValueError("Phase C aggregate must contain exactly 500/200 games")
        if self.paired_game_count != PAIRED_GAME_COUNT:
            raise ValueError("Phase C aggregate must contain exactly 200 paired comparisons")
        if self.standard_shard_count < 1 or self.exploratory_shard_count < 1:
            raise ValueError("Phase C aggregate shard counts must be positive")
        if not self.pilot_authorized:
            raise ValueError("production Phase C aggregate must be explicitly authorized")
        expected = _digest(self.to_dict(include_aggregation_sha=False))
        if self.aggregation_sha256 != expected:
            raise ValueError("Phase C aggregate digest does not match its content")

    def to_dict(self, *, include_aggregation_sha: bool = True) -> dict[str, Any]:
        value = asdict(self)
        if not include_aggregation_sha:
            value.pop("aggregation_sha256", None)
        return value


def _measurement_from_dict(payload: Mapping[str, Any]) -> GameMeasurement:
    opening = tuple(OpeningHandMeasurement(**dict(value)) for value in payload["opening_hands"])
    combos = tuple(ComboMeasurement(**dict(value)) for value in payload["combo_records"])
    cards = tuple(CardMeasurement(**dict(value)) for value in payload["card_records"])
    divergence_payload = payload.get("divergence")
    divergence = (
        DivergenceMeasurement(**dict(divergence_payload))
        if isinstance(divergence_payload, Mapping)
        else None
    )
    checkpoint_access = {
        int(key): bool(value) for key, value in dict(payload["checkpoint_table_win_access"]).items()
    }
    failure_labels = {
        int(key): tuple(str(item) for item in value)
        for key, value in dict(payload["failure_labels"]).items()
    }
    primary_failure = {
        int(key): (None if value is None else str(value))
        for key, value in dict(payload["primary_failure"]).items()
    }
    return GameMeasurement(
        schema_version=str(payload["schema_version"]),
        game_index=int(payload["game_index"]),
        seed=int(payload["seed"]),
        mode=str(payload["mode"]),
        policy_config_id=str(payload["policy_config_id"]),
        opening_hands=opening,
        kept_at=int(payload["kept_at"]),
        checkpoint_table_win_access=checkpoint_access,
        failure_labels=failure_labels,
        primary_failure=primary_failure,
        combo_records=combos,
        earliest_legal_attempt_turn=(
            None
            if payload.get("earliest_legal_attempt_turn") is None
            else int(payload["earliest_legal_attempt_turn"])
        ),
        actual_first_attempt_turn=(
            None
            if payload.get("actual_first_attempt_turn") is None
            else int(payload["actual_first_attempt_turn"])
        ),
        attempt_package=(
            None if payload.get("attempt_package") is None else str(payload["attempt_package"])
        ),
        attempt_timing=(
            None if payload.get("attempt_timing") is None else str(payload["attempt_timing"])
        ),
        usable_protection_count=int(payload["usable_protection_count"]),
        protection_in_hand_not_payable=bool(payload["protection_in_hand_not_payable"]),
        protection_category_mismatch=bool(payload["protection_category_mismatch"]),
        independent_second_line_available=bool(payload["independent_second_line_available"]),
        card_records=cards,
        divergence=divergence,
        search_decisions=tuple(dict(value) for value in payload.get("search_decisions", ())),
        future_information_rejections=int(payload.get("future_information_rejections", 0)),
        post_result_optimization_rejections=int(
            payload.get("post_result_optimization_rejections", 0)
        ),
        terminal_status=str(payload.get("terminal_status", "ACTIVE")),
        terminal_turn=(
            None if payload.get("terminal_turn") is None else int(payload["terminal_turn"])
        ),
        extra=dict(payload.get("extra", {})),
    )


def make_game_artifact(
    *,
    mode: str,
    game_index: int,
    seed: int,
    technical_game: Mapping[str, Any],
    replay: Mapping[str, Any],
    measurement: GameMeasurement,
) -> PhaseCGameArtifact:
    replay_file_sha = _digest(replay)
    measurement_sha = _digest(measurement.to_dict())
    replay_digest = str(technical_game.get("replay_digest", ""))
    final_hash = str(technical_game.get("final_state_hash", ""))
    return PhaseCGameArtifact(
        schema_version="phase-c-pilot-game-artifact-v1",
        mode=mode,
        game_index=game_index,
        seed=seed,
        technical_game_sha256=_digest(technical_game),
        replay_file_sha256=replay_file_sha,
        replay_digest=replay_digest,
        measurement_sha256=measurement_sha,
        final_state_hash=final_hash,
        terminal_status=str(technical_game.get("terminal_status", "")),
        pilot_authorized=True,
    )


def build_shard_manifest(
    *,
    mode: str,
    shard_index: int,
    shard_count: int,
    first_game_index: int,
    seeds: Sequence[int],
    pair_ids: Sequence[str | None],
    paired_standard_game_indexes: Sequence[int | None],
    search_seeds: Sequence[int | None],
    implementation_commit: str,
    implementation_tree: str,
    activation_commit: str,
    locked_config_sha256: str,
    workflow_sha256: str,
    approval_record_sha256: str,
    policy_config_id: str,
    policy_config_sha256: str,
    evaluator_snapshot_id: str,
    evaluator_snapshot_sha256: str,
    learning_plan_sha256: str,
    technical_games: Sequence[Mapping[str, Any]],
    game_records: Sequence[PhaseCGameArtifact],
    replays: Sequence[Mapping[str, Any]],
    measurements: Sequence[GameMeasurement],
    summary: Mapping[str, Any],
) -> PhaseCShardManifest:
    seed_tuple = tuple(int(seed) for seed in seeds)
    if not seed_tuple:
        raise ValueError("Phase C shard cannot be empty")
    technical_dicts = [dict(record) for record in technical_games]
    record_dicts = [record.to_dict() for record in game_records]
    replay_digests = [_digest(replay) for replay in replays]
    measurement_dicts = [record.to_dict() for record in measurements]
    data: dict[str, Any] = {
        "schema_version": "phase-c-pilot-shard-manifest-v2",
        "mode": mode,
        "shard_index": shard_index,
        "shard_count": shard_count,
        "first_game_index": first_game_index,
        "last_game_index": first_game_index + len(seed_tuple) - 1,
        "seeds": seed_tuple,
        "pair_ids": tuple(pair_ids),
        "paired_standard_game_indexes": tuple(paired_standard_game_indexes),
        "search_seeds": tuple(search_seeds),
        "implementation_commit": implementation_commit,
        "implementation_tree": implementation_tree,
        "activation_commit": activation_commit,
        "locked_config_sha256": locked_config_sha256,
        "workflow_sha256": workflow_sha256,
        "approval_record_sha256": approval_record_sha256,
        "policy_config_id": policy_config_id,
        "policy_config_sha256": policy_config_sha256,
        "evaluator_snapshot_id": evaluator_snapshot_id,
        "evaluator_snapshot_sha256": evaluator_snapshot_sha256,
        "learning_plan_sha256": learning_plan_sha256,
        "seed_sha256": _digest(seed_tuple),
        "pairing_sha256": _digest(
            [
                {
                    "pair_id": pair_id,
                    "standard_game_index": standard_index,
                    "environment_seed": seed,
                }
                for pair_id, standard_index, seed in zip(
                    pair_ids, paired_standard_game_indexes, seed_tuple, strict=True
                )
            ]
        ),
        "search_seed_sha256": _digest(tuple(search_seeds)),
        "technical_games_sha256": _digest(technical_dicts),
        "game_records_sha256": _digest(record_dicts),
        "replay_bundle_sha256": _digest(replay_digests),
        "measurement_sha256": _digest(measurement_dicts),
        "summary_sha256": _digest(summary),
        "production_decision_layer_depth": 0 if mode == "STANDARD" else 1,
        "pilot_authorized": True,
        "shard_sha256": "",
    }
    data["shard_sha256"] = _digest(
        {key: value for key, value in data.items() if key != "shard_sha256"}
    )
    manifest = PhaseCShardManifest(**data)
    _validate_shard_payloads(
        manifest, technical_games, game_records, replays, measurements, summary
    )
    return manifest


def _validate_shard_payloads(
    manifest: PhaseCShardManifest,
    technical_games: Sequence[Mapping[str, Any]],
    game_records: Sequence[PhaseCGameArtifact],
    replays: Sequence[Mapping[str, Any]],
    measurements: Sequence[GameMeasurement],
    summary: Mapping[str, Any],
) -> None:
    expected_count = len(manifest.seeds)
    if not (
        len(technical_games)
        == len(game_records)
        == len(replays)
        == len(measurements)
        == expected_count
    ):
        raise ValueError("Phase C shard files do not have the manifest record count")
    expected_indexes = list(range(manifest.first_game_index, manifest.last_game_index + 1))
    if [record.game_index for record in game_records] != expected_indexes:
        raise ValueError("Phase C game artifacts do not match the manifest index range")
    if [record.seed for record in game_records] != list(manifest.seeds):
        raise ValueError("Phase C game artifacts do not match the manifest seed assignment")

    for (
        expected_index,
        expected_seed,
        expected_pair_id,
        expected_standard_index,
        expected_search_seed,
        game,
        technical,
        replay,
        measurement,
    ) in zip(
        expected_indexes,
        manifest.seeds,
        manifest.pair_ids,
        manifest.paired_standard_game_indexes,
        manifest.search_seeds,
        game_records,
        technical_games,
        replays,
        measurements,
        strict=True,
    ):
        if game.mode != manifest.mode or measurement.mode != manifest.mode:
            raise ValueError("Phase C per-game mode differs from the shard manifest")
        if game.game_index != expected_index or measurement.game_index != expected_index:
            raise ValueError("Phase C per-game index linkage is inconsistent")
        if game.seed != expected_seed or measurement.seed != expected_seed:
            raise ValueError("Phase C per-game seed linkage is inconsistent")
        if str(technical.get("mode", "")) != manifest.mode:
            raise ValueError("Phase C technical-game mode differs from the shard manifest")
        if int(technical.get("seed", -1)) != expected_seed:
            raise ValueError("Phase C technical-game seed differs from the shard manifest")
        if (
            technical.get("pair_id") != expected_pair_id
            or measurement.extra.get("pair_id") != expected_pair_id
        ):
            raise ValueError("Phase C per-game pair ID linkage is inconsistent")
        if (
            technical.get("paired_standard_game_index") != expected_standard_index
            or measurement.extra.get("paired_standard_game_index") != expected_standard_index
        ):
            raise ValueError("Phase C paired standard index linkage is inconsistent")
        if (
            technical.get("search_seed") != expected_search_seed
            or measurement.extra.get("search_seed") != expected_search_seed
        ):
            raise ValueError("Phase C per-game search seed linkage is inconsistent")
        if measurement.extra.get("environment_seed") != expected_seed:
            raise ValueError("Phase C measurement environment seed linkage is inconsistent")
        if _digest(technical) != game.technical_game_sha256:
            raise ValueError("Phase C technical-game digest differs from its game artifact")
        if _digest(replay) != game.replay_file_sha256:
            raise ValueError("Phase C replay file digest differs from its game artifact")
        if _digest(measurement.to_dict()) != game.measurement_sha256:
            raise ValueError("Phase C measurement digest differs from its game artifact")
        if str(technical.get("replay_digest", "")) != game.replay_digest:
            raise ValueError("Phase C technical-game replay digest differs from its game artifact")
        if str(replay.get("digest", "")) != game.replay_digest:
            raise ValueError("Phase C replay transcript digest differs from its game artifact")
        if str(technical.get("final_state_hash", "")) != game.final_state_hash:
            raise ValueError("Phase C technical-game final hash differs from its game artifact")

    if _digest([dict(record) for record in technical_games]) != manifest.technical_games_sha256:
        raise ValueError("Phase C technical-game bundle digest mismatch")
    if _digest([record.to_dict() for record in game_records]) != manifest.game_records_sha256:
        raise ValueError("Phase C game-record digest mismatch")
    if _digest([_digest(replay) for replay in replays]) != manifest.replay_bundle_sha256:
        raise ValueError("Phase C replay-bundle digest mismatch")
    if _digest([record.to_dict() for record in measurements]) != manifest.measurement_sha256:
        raise ValueError("Phase C measurement digest mismatch")
    if _digest(summary) != manifest.summary_sha256:
        raise ValueError("Phase C shard summary digest mismatch")
    expected_summary = asdict(aggregate_measurements(measurements))
    if _digest(summary) != _digest(expected_summary):
        raise ValueError("Phase C shard summary does not match its measurements")


def write_phase_c_shard(
    root: Path,
    manifest: PhaseCShardManifest,
    technical_games: Sequence[Mapping[str, Any]],
    game_records: Sequence[PhaseCGameArtifact],
    replays: Sequence[Mapping[str, Any]],
    measurements: Sequence[GameMeasurement],
    summary: Mapping[str, Any],
) -> Path:
    _validate_shard_payloads(
        manifest, technical_games, game_records, replays, measurements, summary
    )

    shard_dir = root / f"{manifest.mode.lower()}-{manifest.shard_index:02d}"
    shard_dir.mkdir(parents=True, exist_ok=False)
    replay_dir = shard_dir / "replays"
    replay_dir.mkdir()
    files: list[Path] = []
    manifest_path = shard_dir / "manifest.json"
    technical_games_path = shard_dir / "technical-games.jsonl"
    games_path = shard_dir / "games.jsonl"
    measurements_path = shard_dir / "measurements.jsonl"
    summary_path = shard_dir / "summary.json"
    manifest_path.write_bytes(_canonical(manifest.to_dict()) + b"\n")
    technical_games_path.write_bytes(
        b"".join(_canonical(dict(record)) + b"\n" for record in technical_games)
    )
    games_path.write_bytes(
        b"".join(_canonical(record.to_dict()) + b"\n" for record in game_records)
    )
    measurements_path.write_bytes(
        b"".join(_canonical(record.to_dict()) + b"\n" for record in measurements)
    )
    summary_path.write_bytes(_canonical(summary) + b"\n")
    files.extend((manifest_path, technical_games_path, games_path, measurements_path, summary_path))
    for game_index, replay in zip(
        range(manifest.first_game_index, manifest.last_game_index + 1), replays, strict=True
    ):
        path = replay_dir / f"game-{game_index:04d}.json"
        path.write_bytes(_canonical(replay) + b"\n")
        files.append(path)
    for path in files:
        path.chmod(0o444)
    replay_dir.chmod(0o555)
    shard_dir.chmod(0o555)
    return shard_dir


def load_phase_c_shard(
    shard_dir: Path,
) -> tuple[
    PhaseCShardManifest,
    tuple[PhaseCGameArtifact, ...],
    tuple[Mapping[str, Any], ...],
    tuple[GameMeasurement, ...],
    Mapping[str, Any],
]:
    manifest_payload = json.loads((shard_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest = PhaseCShardManifest(**manifest_payload)
    technical_games = tuple(
        json.loads(line)
        for line in (shard_dir / "technical-games.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    )
    game_payloads = [
        json.loads(line)
        for line in (shard_dir / "games.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    games = tuple(PhaseCGameArtifact(**payload) for payload in game_payloads)
    measurement_payloads = [
        json.loads(line)
        for line in (shard_dir / "measurements.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    measurements = tuple(_measurement_from_dict(payload) for payload in measurement_payloads)
    replays = tuple(
        json.loads((shard_dir / "replays" / f"game-{index:04d}.json").read_text(encoding="utf-8"))
        for index in range(manifest.first_game_index, manifest.last_game_index + 1)
    )
    summary = json.loads((shard_dir / "summary.json").read_text(encoding="utf-8"))
    _validate_shard_payloads(manifest, technical_games, games, replays, measurements, summary)
    return manifest, games, replays, measurements, summary


def validate_phase_c_aggregate(
    shard_dirs: Sequence[Path],
    *,
    expected_standard_seeds: Sequence[int],
    expected_exploratory_seeds: Sequence[int],
    expected_exploratory_search_seeds: Sequence[int],
    expected_pair_ids: Sequence[str],
    expected_paired_standard_game_indexes: Sequence[int],
    expected_standard_shards: int,
    expected_exploratory_shards: int,
) -> tuple[PhaseCAggregateManifest, Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    if not shard_dirs:
        raise ValueError("Phase C aggregation requires shard artifacts")
    loaded = [load_phase_c_shard(path) for path in shard_dirs]
    manifests = [value[0] for value in loaded]
    invariant_fields = (
        "implementation_commit",
        "implementation_tree",
        "activation_commit",
        "locked_config_sha256",
        "workflow_sha256",
        "approval_record_sha256",
        "policy_config_id",
        "policy_config_sha256",
        "evaluator_snapshot_id",
        "evaluator_snapshot_sha256",
        "learning_plan_sha256",
        "pilot_authorized",
    )
    first = manifests[0]
    for manifest in manifests[1:]:
        mixed = [
            field for field in invariant_fields if getattr(manifest, field) != getattr(first, field)
        ]
        if mixed:
            raise ValueError(f"Phase C aggregation rejects mixed shard identity fields: {mixed}")

    mode_data: dict[str, list[tuple[PhaseCShardManifest, tuple[GameMeasurement, ...]]]] = {
        "STANDARD": [],
        "EXPLORATORY": [],
    }
    for manifest, _games, _replays, shard_measurements, _summary in loaded:
        mode_data[manifest.mode].append((manifest, shard_measurements))

    expected_standard = tuple(int(v) for v in expected_standard_seeds)
    expected_exploratory = tuple(int(v) for v in expected_exploratory_seeds)
    expected_search = tuple(int(v) for v in expected_exploratory_search_seeds)
    expected_pairs = tuple(str(v) for v in expected_pair_ids)
    expected_standard_indexes = tuple(int(v) for v in expected_paired_standard_game_indexes)
    if not (
        len(expected_exploratory)
        == len(expected_search)
        == len(expected_pairs)
        == len(expected_standard_indexes)
        == PAIRED_GAME_COUNT
    ):
        raise ValueError("Phase C paired aggregate expectations must contain exactly 200 pairs")
    pair_by_standard_index = dict(zip(expected_standard_indexes, expected_pairs, strict=True))
    expected_pair_by_mode = {
        "STANDARD": tuple(
            pair_by_standard_index.get(index) for index in range(1, len(expected_standard) + 1)
        ),
        "EXPLORATORY": expected_pairs,
    }
    expected_index_by_mode = {
        "STANDARD": tuple(
            index if index in pair_by_standard_index else None
            for index in range(1, len(expected_standard) + 1)
        ),
        "EXPLORATORY": expected_standard_indexes,
    }
    expected_search_by_mode = {
        "STANDARD": (None,) * len(expected_standard),
        "EXPLORATORY": expected_search,
    }
    expected_by_mode = {
        "STANDARD": (expected_standard, expected_standard_shards),
        "EXPLORATORY": (expected_exploratory, expected_exploratory_shards),
    }
    summaries: dict[str, Mapping[str, Any]] = {}
    all_manifest_shas: list[str] = []
    mode_measurements: dict[str, list[GameMeasurement]] = {}
    for mode, entries in mode_data.items():
        expected_seeds, expected_shards = expected_by_mode[mode]
        if len(entries) != expected_shards:
            raise ValueError(
                f"Phase C aggregation requires exactly {expected_shards} {mode} shards"
            )
        entries.sort(key=lambda value: value[0].shard_index)
        if [manifest.shard_index for manifest, _ in entries] != list(range(expected_shards)):
            raise ValueError(
                f"Phase C aggregation rejects missing or duplicate {mode} shard indexes"
            )
        flattened_seeds: list[int] = []
        flattened_indexes: list[int] = []
        flattened_pair_ids: list[str | None] = []
        flattened_standard_indexes: list[int | None] = []
        flattened_search_seeds: list[int | None] = []
        measurements: list[GameMeasurement] = []
        expected_next = 1
        for manifest, shard_measurements in entries:
            if manifest.shard_count != expected_shards:
                raise ValueError(f"Phase C {mode} shard count declaration is inconsistent")
            if manifest.first_game_index != expected_next:
                raise ValueError(f"Phase C aggregation rejects {mode} game-index gaps or overlaps")
            expected_next = manifest.last_game_index + 1
            flattened_seeds.extend(manifest.seeds)
            flattened_indexes.extend(range(manifest.first_game_index, manifest.last_game_index + 1))
            flattened_pair_ids.extend(manifest.pair_ids)
            flattened_standard_indexes.extend(manifest.paired_standard_game_indexes)
            flattened_search_seeds.extend(manifest.search_seeds)
            measurements.extend(shard_measurements)
            all_manifest_shas.append(manifest.shard_sha256)
        if tuple(flattened_seeds) != expected_seeds:
            raise ValueError(f"Phase C aggregation rejects {mode} environment seed partition drift")
        if tuple(flattened_pair_ids) != expected_pair_by_mode[mode]:
            raise ValueError(f"Phase C aggregation rejects {mode} pair assignment drift")
        if tuple(flattened_standard_indexes) != expected_index_by_mode[mode]:
            raise ValueError(f"Phase C aggregation rejects {mode} paired standard-index drift")
        if tuple(flattened_search_seeds) != expected_search_by_mode[mode]:
            raise ValueError(f"Phase C aggregation rejects {mode} search-seed drift")
        if flattened_indexes != list(range(1, len(expected_seeds) + 1)):
            raise ValueError(f"Phase C aggregation rejects {mode} game-index drift")
        if [record.game_index for record in measurements] != flattened_indexes:
            raise ValueError(f"Phase C aggregation rejects {mode} measurement-index drift")
        if [record.seed for record in measurements] != flattened_seeds:
            raise ValueError(f"Phase C aggregation rejects {mode} measurement-seed drift")
        summary = aggregate_measurements(measurements)
        summaries[mode] = asdict(summary)
        mode_measurements[mode] = measurements

    standard_by_index = {record.game_index: record for record in mode_measurements["STANDARD"]}
    exploratory_measurements = mode_measurements["EXPLORATORY"]
    pair_records: list[dict[str, Any]] = []
    for exploratory_index, (pair_id, standard_index, environment_seed, search_seed) in enumerate(
        zip(
            expected_pairs,
            expected_standard_indexes,
            expected_exploratory,
            expected_search,
            strict=True,
        ),
        start=1,
    ):
        standard_record = standard_by_index[standard_index]
        exploratory_record = exploratory_measurements[exploratory_index - 1]
        if standard_record.seed != environment_seed or exploratory_record.seed != environment_seed:
            raise ValueError("paired STANDARD/EXPLORATORY executions do not share environment seed")
        if exploratory_record.extra.get("search_seed") != search_seed:
            raise ValueError("paired exploratory measurement lost its search seed binding")
        if standard_record.extra.get("search_seed") is not None:
            raise ValueError("paired standard measurement consumed exploratory search randomness")
        if (
            standard_record.extra.get("pair_id") != pair_id
            or exploratory_record.extra.get("pair_id") != pair_id
        ):
            raise ValueError("paired measurements do not share the exact pair ID")
        if standard_record.extra.get(
            "environment_initial_state_hash"
        ) != exploratory_record.extra.get("environment_initial_state_hash"):
            raise ValueError("paired executions did not start from the same environment state")
        pair_records.append(
            {
                "pair_id": pair_id,
                "standard_game_index": standard_index,
                "exploratory_game_index": exploratory_index,
                "environment_seed": environment_seed,
                "search_seed": search_seed,
                "standard_access": bool(standard_record.checkpoint_table_win_access[8]),
                "exploratory_access": bool(exploratory_record.checkpoint_table_win_access[8]),
            }
        )

    paired_analysis = build_paired_turn8_analysis(pair_records)
    standard_summary = summaries["STANDARD"]
    exploratory_summary = summaries["EXPLORATORY"]
    pair_assignment_rows = [
        {
            "pair_id": pair_id,
            "standard_game_index": standard_index,
            "environment_seed": environment_seed,
            "search_seed": search_seed,
        }
        for pair_id, standard_index, environment_seed, search_seed in zip(
            expected_pairs,
            expected_standard_indexes,
            expected_exploratory,
            expected_search,
            strict=True,
        )
    ]
    data: dict[str, Any] = {
        "schema_version": "phase-c-pilot-aggregate-manifest-v2",
        "implementation_commit": first.implementation_commit,
        "implementation_tree": first.implementation_tree,
        "activation_commit": first.activation_commit,
        "locked_config_sha256": first.locked_config_sha256,
        "workflow_sha256": first.workflow_sha256,
        "approval_record_sha256": first.approval_record_sha256,
        "standard_game_count": len(expected_standard),
        "exploratory_game_count": len(expected_exploratory),
        "standard_seed_sha256": _digest(expected_standard),
        "exploratory_seed_sha256": _digest(expected_exploratory),
        "exploratory_search_seed_sha256": _digest(expected_search),
        "pair_assignment_sha256": _digest(pair_assignment_rows),
        "paired_game_count": PAIRED_GAME_COUNT,
        "paired_analysis_sha256": _digest(paired_analysis),
        "standard_shard_count": expected_standard_shards,
        "exploratory_shard_count": expected_exploratory_shards,
        "standard_summary_sha256": _digest(standard_summary),
        "exploratory_summary_sha256": _digest(exploratory_summary),
        "shard_manifest_sha256s": tuple(sorted(all_manifest_shas)),
        "pilot_authorized": True,
        "aggregation_sha256": "",
    }
    data["aggregation_sha256"] = _digest(
        {key: value for key, value in data.items() if key != "aggregation_sha256"}
    )
    return PhaseCAggregateManifest(**data), standard_summary, exploratory_summary, paired_analysis


def write_phase_c_aggregate(
    root: Path,
    manifest: PhaseCAggregateManifest,
    standard_summary: Mapping[str, Any],
    exploratory_summary: Mapping[str, Any],
    paired_analysis: Mapping[str, Any],
) -> Path:
    output = root / "aggregate"
    output.mkdir(parents=True, exist_ok=False)
    manifest_path = output / "manifest.json"
    standard_path = output / "standard-summary.json"
    exploratory_path = output / "exploratory-summary.json"
    paired_path = output / "paired-turn8-analysis.json"
    if _digest(standard_summary) != manifest.standard_summary_sha256:
        raise ValueError("standard summary digest differs from aggregate manifest")
    if _digest(exploratory_summary) != manifest.exploratory_summary_sha256:
        raise ValueError("exploratory summary digest differs from aggregate manifest")
    if _digest(paired_analysis) != manifest.paired_analysis_sha256:
        raise ValueError("paired analysis digest differs from aggregate manifest")
    manifest_path.write_bytes(_canonical(manifest.to_dict()) + b"\n")
    standard_path.write_bytes(_canonical(standard_summary) + b"\n")
    exploratory_path.write_bytes(_canonical(exploratory_summary) + b"\n")
    paired_path.write_bytes(_canonical(paired_analysis) + b"\n")
    for path in (manifest_path, standard_path, exploratory_path, paired_path):
        path.chmod(0o444)
    output.chmod(0o555)
    return output


__all__ = [
    "PhaseCAggregateManifest",
    "PhaseCGameArtifact",
    "PhaseCShardManifest",
    "build_shard_manifest",
    "load_phase_c_shard",
    "make_game_artifact",
    "validate_phase_c_aggregate",
    "write_phase_c_aggregate",
    "write_phase_c_shard",
]
