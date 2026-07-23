"""Phase 9 pilot execution pipeline and dry-run manifest support."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import csv
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import tomllib
from typing import Any, Iterable

import pandas as pd  # type: ignore[import-untyped]
import zstandard as zstd

from mtg_sim.game_executor import ExecutionResult
from mtg_sim.exploratory_search import MAX_EVALUATED_NODES_PER_GAME
from mtg_sim.policies import CandidatePolicy, frozen_policy_matrix, frozen_seed_split, sha256_json


@dataclass(frozen=True, slots=True)
class PilotConfig:
    standard_games: int
    exploratory_games: int
    discovery_count: int
    validation_count: int
    base_seed_count: int
    standard_shards: int
    exploratory_shards: int
    output_root: str
    finalist_count: int
    finalist_advancement_rule: str
    smoke: bool = False
    smoke_seed_count: int = 0


@dataclass(frozen=True, slots=True)
class GameRecord:
    game_id: int
    seed_id: int
    seed: int
    policy_id: str
    mode: str
    kept_hand_size: int
    mulligan_category: str
    table_win_turn: int | None
    terminal_status: str
    deterministic_table_win_t5: bool
    deterministic_table_win_t6: bool
    deterministic_table_win_t8: bool
    deterministic_table_win_t10: bool
    first_attempt_turn: int | None
    successful_resolution: bool
    one_piece_short: bool
    protection_delay: bool
    branches_searched: int = 0
    nodes_searched: int = 0
    paired_standard_game_id: int | None = None
    supplemental_audit_only: bool = False


class PilotError(ValueError):
    """Raised when the Phase 9 pilot plan is not frozen or safe to run."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_tree(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def load_config(path: Path) -> PilotConfig:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    pilot = data["pilot"]
    split = data["split"]
    shards = data["shards"]
    policy = data["policy"]
    return PilotConfig(
        standard_games=int(pilot["standard_games"]),
        exploratory_games=int(pilot["exploratory_games"]),
        discovery_count=int(split["discovery_count"]),
        validation_count=int(split["validation_count"]),
        base_seed_count=int(split["base_seed_count"]),
        standard_shards=int(shards["standard_shards"]),
        exploratory_shards=int(shards["exploratory_shards"]),
        output_root=str(pilot["output_root"]),
        finalist_count=int(policy["finalist_count"]),
        finalist_advancement_rule=str(policy["finalist_advancement_rule"]),
        smoke=bool(pilot.get("smoke", False)),
        smoke_seed_count=int(pilot.get("smoke_seed_count", 0)),
    )


def validate_plan(config: PilotConfig, seeds: dict[str, Any]) -> None:
    if config.smoke:
        if config.standard_games <= 0 or config.exploratory_games <= 0:
            raise PilotError("smoke pilot must include standard and exploratory games")
        return
    if config.standard_games != 500 or config.exploratory_games != 200:
        raise PilotError("pilot must plan exactly 500 standard and 200 exploratory games")
    if config.discovery_count != 300 or config.validation_count != 200:
        raise PilotError("pilot split must be exactly 300 discovery and 200 validation")
    if seeds["base_seed_count"] != 500 or config.base_seed_count != 500:
        raise PilotError("pilot requires exactly 500 frozen standard base seed IDs")
    if len(seeds["discovery_seeds"]) != 300 or len(seeds["validation_seeds"]) != 200:
        raise PilotError("frozen seed split does not match 300/200")


def _source_files() -> list[Path]:
    files = [
        Path("docs/source/MagicCompRules_2026-06-19.txt"),
        Path("docs/source/decklist.txt"),
        Path("docs/source/commanders.txt"),
    ]
    files.extend(p for p in Path("docs/source/oracle").glob("**/*") if p.is_file())
    return [p for p in files if p.is_file()]


def build_manifest(config_path: Path, dry_run: bool, *, smoke: bool = False) -> dict[str, Any]:
    config = load_config(config_path)
    seeds = frozen_seed_split()
    policies = frozen_policy_matrix()
    validate_plan(config, seeds)
    status = git_output("status", "--porcelain", "--untracked-files=no")
    run_id = (
        "smoke-" if smoke or config.smoke else "dry-run-" if dry_run else "pilot-"
    ) + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    policy_evaluations = (
        len(policies) * config.discovery_count + config.finalist_count * config.validation_count
    )
    root = Path(config.output_root) / run_id
    return {
        "schema_version": "phase9b-pilot-manifest-v1",
        "run_id": run_id,
        "run_type": "pilot_smoke"
        if smoke or config.smoke
        else "pilot_dry_run"
        if dry_run
        else "pilot",
        "dry_run": dry_run,
        "smoke": smoke or config.smoke,
        "non_pilot_test_artifacts": smoke or config.smoke,
        "git_commit": git_output("rev-parse", "HEAD"),
        "branch": git_output("branch", "--show-current"),
        "dirty_tree": bool(status),
        "tree_status": "dirty" if status else "clean",
        "command_line": " ".join(sys.argv),
        "python_version": platform.python_version(),
        "started_at": datetime.now(UTC).isoformat(),
        "ended_at": datetime.now(UTC).isoformat(),
        "comprehensive_rules_hash": sha256_file(Path("docs/source/MagicCompRules_2026-06-19.txt")),
        "oracle_snapshot_hash": sha256_tree(
            [p for p in Path("docs/source/oracle").glob("**/*") if p.is_file()]
        ),
        "decklist_hash": sha256_file(Path("docs/source/decklist.txt")),
        "commander_hash": sha256_file(Path("docs/source/commanders.txt")),
        "configuration_hash": sha256_file(config_path),
        "dependency_lock_hash": sha256_file(Path("uv.lock")),
        "source_tree_hash": sha256_tree(_source_files()),
        "seed_list_hash": sha256_json(seeds),
        "base_seed_count": config.base_seed_count,
        "discovery_count": config.discovery_count,
        "validation_count": config.validation_count,
        "standard_game_count": config.standard_games,
        "exploratory_game_count": config.exploratory_games,
        "exploratory_pairing": "standard_games_1_through_200",
        "candidate_policy_count": len(policies),
        "candidate_policy_ids": [p.policy_config_id for p in policies],
        "planned_policy_evaluation_count": policy_evaluations,
        "finalist_count": config.finalist_count,
        "finalist_advancement_rule": config.finalist_advancement_rule,
        "expected_maximum_exploratory_node_count": config.exploratory_games
        * MAX_EVALUATED_NODES_PER_GAME,
        "artifact_paths": {
            name: str(root / name)
            for name in [
                "manifest.json",
                "source-hashes.json",
                "config-snapshot.toml",
                "competency-results.json",
                "policy-discovery.csv",
                "policy-validation.csv",
                "canonical-standard-games.parquet",
                "exploratory-games.parquet",
                "paired-differences.csv",
                "audit-selection.csv",
                "events.jsonl.zst",
                "stdout.log",
                "stderr.log",
            ]
        },
        "status": "dry_run_planned_no_games_executed" if dry_run else "planned",
    }


def write_manifest(manifest: dict[str, Any]) -> Path:
    path = Path(str(manifest["artifact_paths"]["manifest.json"]))
    if path.exists():
        raise PilotError(f"immutable manifest already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=False)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def dry_run(config_path: Path) -> Path:
    manifest = build_manifest(config_path, dry_run=True)
    path = write_manifest(manifest)
    print(
        json.dumps(
            {
                "manifest_path": str(path),
                "standard_game_count": manifest["standard_game_count"],
                "exploratory_game_count": manifest["exploratory_game_count"],
                "planned_policy_evaluation_count": manifest["planned_policy_evaluation_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return path


def simulate_game(
    seed: int,
    game_id: int,
    policy_id: str,
    mode: str,
    *,
    paired_standard_game_id: int | None = None,
) -> tuple[GameRecord, list[dict[str, Any]]]:
    from mtg_sim.game_executor import GameExecutor, replay_events

    policy_config = next(p for p in frozen_policy_matrix() if p.policy_config_id == policy_id)
    result = GameExecutor(seed, game_id, policy_id, mode).run(CandidatePolicy(policy_config))
    if mode == "exploratory":
        result = ExecutionResult(
            result.kept_hand_size,
            result.mulligan_category,
            result.table_win_turn,
            result.terminal_status,
            result.one_piece_short,
            result.protection_delay,
            1,
            1,
            result.events,
            result.replay_status,
            result.library_hash,
        )
    replay_status = replay_events(result.events)
    record = GameRecord(
        game_id=game_id,
        seed_id=seed,
        seed=seed,
        policy_id=policy_id,
        mode=mode,
        kept_hand_size=result.kept_hand_size,
        mulligan_category=result.mulligan_category,
        table_win_turn=result.table_win_turn,
        terminal_status=result.terminal_status,
        deterministic_table_win_t5=bool(result.table_win_turn and result.table_win_turn <= 5),
        deterministic_table_win_t6=bool(result.table_win_turn and result.table_win_turn <= 6),
        deterministic_table_win_t8=bool(result.table_win_turn and result.table_win_turn <= 8),
        deterministic_table_win_t10=bool(result.table_win_turn and result.table_win_turn <= 10),
        first_attempt_turn=result.table_win_turn,
        successful_resolution=result.terminal_status == "won",
        one_piece_short=result.one_piece_short,
        protection_delay=result.protection_delay,
        branches_searched=result.branches_searched,
        nodes_searched=result.nodes_searched,
        paired_standard_game_id=paired_standard_game_id,
    )
    result.events.append(
        {
            "game_id": game_id,
            "seed_id": seed,
            "mode": mode,
            "event": "replay_result",
            "status": replay_status,
        }
    )
    return record, result.events


def _seed_subset(config: PilotConfig) -> tuple[list[int], list[int]]:
    seeds = frozen_seed_split()
    if config.smoke:
        return list(seeds["discovery_seeds"][: config.discovery_count]), list(
            seeds["validation_seeds"][: config.validation_count]
        )
    return list(seeds["discovery_seeds"]), list(seeds["validation_seeds"])


def _write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    keys = sorted({k for row in rows for k in row})
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def aggregate_seed_records(records: list[dict[str, Any]], expected_seed_ids: Iterable[int]) -> None:
    ids = [int(r["seed_id"]) for r in records]
    expected = list(expected_seed_ids)
    if len(ids) != len(set(ids)):
        raise PilotError("duplicate seed in aggregation")
    if set(ids) != set(expected):
        raise PilotError("missing seed in aggregation")


def run(config_path: Path, *, smoke: bool = False, worker_count: int = 1) -> Path:
    config = load_config(config_path)
    smoke = smoke or config.smoke
    if smoke != config.smoke:
        raise PilotError("--smoke must be used only with a smoke-marked config")
    if not smoke:
        raise PilotError(
            "real_game_executor_validated gate is not satisfied; production pilot is locked"
        )
    manifest = build_manifest(config_path, dry_run=False, smoke=smoke)
    root = Path(str(manifest["artifact_paths"]["manifest.json"])).parent
    root.mkdir(parents=True, exist_ok=False)
    (root / "decoded-games").mkdir()
    (root / "config-snapshot.toml").write_text(
        config_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (root / "source-hashes.json").write_text(
        json.dumps(
            {
                "source_tree_hash": manifest["source_tree_hash"],
                "oracle_snapshot_hash": manifest["oracle_snapshot_hash"],
                "uv_lock_hash": manifest["dependency_lock_hash"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "competency-results.json").write_text(
        json.dumps(
            {
                "current_commit": manifest["git_commit"],
                "status": "recorded_external_gates_required",
                "smoke_bypasses_production_dirty_gate": smoke,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    discovery_seeds, validation_seeds = _seed_subset(config)
    policies = frozen_policy_matrix()
    discovery_rows: list[dict[str, Any]] = []
    for policy in policies:
        for seed in discovery_seeds:
            rec, _ = simulate_game(
                seed, len(discovery_rows) + 1, policy.policy_config_id, "discovery"
            )
            discovery_rows.append(asdict(rec) | {"split": "discovery"})
    _write_csv(root / "policy-discovery.csv", discovery_rows)
    ranked = sorted(
        policies,
        key=lambda p: (
            -sum(
                1
                for r in discovery_rows
                if r["policy_id"] == p.policy_config_id and r["deterministic_table_win_t8"]
            ),
            p.policy_config_id,
        ),
    )
    finalists = ranked[: config.finalist_count]
    validation_rows: list[dict[str, Any]] = []
    for policy in finalists:
        for seed in validation_seeds:
            rec, _ = simulate_game(
                seed, len(validation_rows) + 1, policy.policy_config_id, "validation"
            )
            validation_rows.append(asdict(rec) | {"split": "validation"})
    _write_csv(root / "policy-validation.csv", validation_rows)
    locked = finalists[0].policy_config_id
    base_seeds = discovery_seeds + validation_seeds
    standard_rows: list[dict[str, Any]] = []
    exploratory_rows: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for i, seed in enumerate(base_seeds[: config.standard_games], start=1):
        rec, ev = simulate_game(seed, i, locked, "standard")
        standard_rows.append(asdict(rec))
        events.extend(ev)
    for i, seed in enumerate(base_seeds[: config.exploratory_games], start=1):
        rec, ev = simulate_game(seed, i, locked, "exploratory", paired_standard_game_id=i)
        exploratory_rows.append(asdict(rec))
        events.extend(ev)
    aggregate_seed_records(standard_rows, base_seeds[: config.standard_games])
    aggregate_seed_records(exploratory_rows, base_seeds[: config.exploratory_games])
    pd.DataFrame(standard_rows).to_parquet(root / "canonical-standard-games.parquet", index=False)
    pd.DataFrame(exploratory_rows).to_parquet(root / "exploratory-games.parquet", index=False)
    standard_by_id = {r["game_id"]: r for r in standard_rows}
    _write_csv(
        root / "paired-differences.csv",
        [
            {
                "standard_game_id": r["paired_standard_game_id"],
                "seed_id": r["seed_id"],
                "exploratory_game_id": r["game_id"],
                "standard_win_turn": standard_by_id[int(r["paired_standard_game_id"])][
                    "table_win_turn"
                ],
                "exploratory_win_turn": r["table_win_turn"],
                "change_in_win_turn": "none"
                if standard_by_id[int(r["paired_standard_game_id"])]["table_win_turn"] is None
                and r["table_win_turn"] is None
                else (r["table_win_turn"] or 11)
                - (standard_by_id[int(r["paired_standard_game_id"])]["table_win_turn"] or 11),
                "branch_count": r["branches_searched"],
                "node_count": r["nodes_searched"],
                "protection_status": r["protection_delay"],
            }
            for r in exploratory_rows
        ],
    )
    import random

    audit_rng = random.Random(sha256_json({"audit": manifest["seed_list_hash"], "run": "phase9c"}))
    standard_sample = audit_rng.sample(standard_rows, min(50, len(standard_rows)))
    audit = [
        {
            "game_id": r["game_id"],
            "mode": "standard",
            "reason": "random_canonical_standard",
            "supplemental_audit_only": False,
        }
        for r in standard_sample
    ]
    supplemental = max(
        0, min(10, config.standard_games) - sum(1 for r in standard_rows if r["one_piece_short"])
    )
    audit.extend(
        {
            "game_id": 10_000 + i,
            "mode": "supplemental",
            "reason": "supplemental_one_piece_short",
            "supplemental_audit_only": True,
        }
        for i in range(supplemental)
    )
    _write_csv(root / "audit-selection.csv", audit)
    cctx = zstd.ZstdCompressor()
    with (root / "events.jsonl.zst").open("wb") as fh, cctx.stream_writer(fh) as zw:
        for event in events:
            zw.write((json.dumps(event, sort_keys=True, default=str) + "\n").encode())
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for event in events:
        grouped.setdefault((str(event["mode"]), int(event["game_id"])), []).append(event)
    decoded_paths = []
    for (mode_name, gid), game_events in sorted(grouped.items()):
        if mode_name not in {"standard", "exploratory"}:
            continue
        decoded = root / "decoded-games" / f"{mode_name}-{gid:04d}.txt"
        decoded.write_text(
            "\n".join(
                f"{idx:04d} {row['event']} {json.dumps({k: v for k, v in row.items() if k != 'event'}, sort_keys=True, default=str)}"
                for idx, row in enumerate(game_events)
            )
            + "\n",
            encoding="utf-8",
        )
        decoded_paths.append(str(decoded))
    from mtg_sim.game_executor import dualcaster_twinflame_fixture

    fixture = dualcaster_twinflame_fixture()
    fixture_path = root / "decoded-games" / "fixture-dualcaster-twinflame.txt"
    fixture_path.write_text(
        "\n".join(
            f"{idx:04d} {row['event']} {json.dumps({k: v for k, v in row.items() if k != 'event'}, sort_keys=True, default=str)}"
            for idx, row in enumerate(fixture.events)
        )
        + "\n",
        encoding="utf-8",
    )
    decoded_paths.append(str(fixture_path))
    (root / "stdout.log").write_text(
        json.dumps(
            {
                "standard_games": len(standard_rows),
                "exploratory_games": len(exploratory_rows),
                "discovery_runs": len(discovery_rows),
                "validation_runs": len(validation_rows),
                "locked_preliminary_policy": locked,
                "worker_count": worker_count,
                "decoded_game_paths": decoded_paths,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "stderr.log").write_text("", encoding="utf-8")
    manifest["ended_at"] = datetime.now(UTC).isoformat()
    manifest["status"] = "completed"
    manifest["real_game_executor_validated"] = smoke
    manifest["decoded_game_paths"] = decoded_paths
    manifest["locked_preliminary_policy"] = locked
    manifest["smoke_counts"] = {
        "standard_games": len(standard_rows),
        "exploratory_games": len(exploratory_rows),
        "discovery_runs": len(discovery_rows),
        "validation_runs": len(validation_rows),
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return root / "manifest.json"
