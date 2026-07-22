"""Phase 9 pilot dry-run manifest and reporting support."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import tomllib
from typing import Any

from mtg_sim.exploratory_search import MAX_EVALUATED_NODES_PER_GAME
from mtg_sim.policies import frozen_policy_matrix, frozen_seed_split, sha256_json


@dataclass(frozen=True, slots=True)
class PilotConfig:
    standard_games: int
    exploratory_games: int
    discovery_count: int
    validation_count: int
    standard_shards: int
    exploratory_shards: int
    output_root: str
    finalist_advancement_rule: str


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
    return PilotConfig(
        standard_games=int(pilot["standard_games"]),
        exploratory_games=int(pilot["exploratory_games"]),
        discovery_count=int(split["discovery_count"]),
        validation_count=int(split["validation_count"]),
        standard_shards=int(shards["standard_shards"]),
        exploratory_shards=int(shards["exploratory_shards"]),
        output_root=str(pilot["output_root"]),
        finalist_advancement_rule=str(data["policy"]["finalist_advancement_rule"]),
    )


def validate_plan(config: PilotConfig, seeds: dict[str, Any]) -> None:
    if config.standard_games != 500 or config.exploratory_games != 200:
        raise PilotError("pilot must plan exactly 500 standard and 200 exploratory games")
    if config.discovery_count != 300 or config.validation_count != 200:
        raise PilotError("pilot split must be exactly 300 discovery and 200 validation")
    if seeds["base_seed_count"] != 500:
        raise PilotError("pilot requires exactly 500 frozen standard base seed IDs")
    if len(seeds["discovery_seeds"]) != 300 or len(seeds["validation_seeds"]) != 200:
        raise PilotError("frozen seed split does not match 300/200")


def build_manifest(config_path: Path, dry_run: bool) -> dict[str, Any]:
    config = load_config(config_path)
    seeds = frozen_seed_split()
    policies = frozen_policy_matrix()
    validate_plan(config, seeds)
    status = git_output("status", "--porcelain")
    source_files = [
        Path("docs/source/MagicCompRules_2026-06-19.txt"),
        *Path("docs/source/oracle").glob("**/*"),
        Path("docs/source/decklist.txt"),
        Path("docs/source/commanders.txt"),
    ]
    source_files = [p for p in source_files if p.is_file()]
    policy_evaluations = (len(policies) * config.discovery_count) + (3 * config.validation_count)
    run_id = "dry-run-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    manifest: dict[str, Any] = {
        "schema_version": "phase9-pilot-manifest-v1",
        "run_id": run_id,
        "run_type": "pilot_dry_run" if dry_run else "pilot",
        "dry_run": dry_run,
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
        "source_tree_hash": sha256_tree(source_files),
        "seed_list_hash": sha256_json(seeds),
        "base_seed_count": 500,
        "discovery_count": 300,
        "validation_count": 200,
        "standard_game_count": 500,
        "exploratory_game_count": 200,
        "exploratory_pairing": "standard_games_1_through_200",
        "candidate_policy_count": len(policies),
        "candidate_policy_ids": [p.policy_config_id for p in policies],
        "planned_policy_evaluation_count": policy_evaluations,
        "policy_evaluation_formula": f"{len(policies)} policies * 300 discovery + 3 finalists * 200 validation",
        "finalist_advancement_rule": config.finalist_advancement_rule,
        "audit_plan": {
            "random_standard_games": 50,
            "random_exploratory_games": 25,
            "all_turn_3_or_4_wins": True,
            "all_unfamiliar_or_nonstandard_lines": True,
            "minimum_mulligans_to_four": 10,
            "minimum_one_piece_short_games": 10,
            "minimum_protection_delay_games": 10,
            "supplemental_audit_only_excluded_from_percentages": True,
        },
        "shard_plan": {
            "standard_shards": config.standard_shards,
            "exploratory_shards": config.exploratory_shards,
            "shard_assignment": "contiguous canonical game indexes; exploratory paired to standard games 1-200",
        },
        "expected_maximum_exploratory_node_count": config.exploratory_games
        * MAX_EVALUATED_NODES_PER_GAME,
        "artifact_paths": {
            "manifest": f"{config.output_root}/{run_id}/manifest.json",
            "raw_standard_games": f"{config.output_root}/{run_id}/raw/standard_games.jsonl.zst",
            "raw_exploratory_games": f"{config.output_root}/{run_id}/raw/exploratory_games.jsonl.zst",
            "event_logs": f"{config.output_root}/{run_id}/raw/events/",
            "audit_reports": f"{config.output_root}/{run_id}/audit/",
            "reports": f"{config.output_root}/{run_id}/reports/",
            "shards": f"{config.output_root}/{run_id}/shards/",
        },
        "preflight_required_before_games": [
            "git commit/tree match",
            "sources unchanged",
            "uv.lock unchanged",
            "verify-rules pass",
            "validate-sources pass",
            "validate-coverage pass",
            "no blocking decision",
        ],
        "status": "dry_run_planned_no_games_executed" if dry_run else "planned",
    }
    return manifest


def write_manifest(manifest: dict[str, Any]) -> Path:
    path = Path(str(manifest["artifact_paths"]["manifest"]))
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
                k: manifest[k]
                for k in [
                    "git_commit",
                    "tree_status",
                    "comprehensive_rules_hash",
                    "oracle_snapshot_hash",
                    "decklist_hash",
                    "commander_hash",
                    "configuration_hash",
                    "dependency_lock_hash",
                    "base_seed_count",
                    "discovery_count",
                    "validation_count",
                    "candidate_policy_count",
                    "planned_policy_evaluation_count",
                    "standard_game_count",
                    "exploratory_game_count",
                    "finalist_advancement_rule",
                    "audit_plan",
                    "shard_plan",
                    "expected_maximum_exploratory_node_count",
                ]
            }
            | {"manifest_path": str(path)},
            indent=2,
            sort_keys=True,
        )
    )
    return path
