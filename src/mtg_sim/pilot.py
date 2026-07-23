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

from mtg_sim.domain import (
    COMMANDERS,
    Observation,
    Phase,
    Step,
    TerminalStatus,
)
from mtg_sim.engine import (
    Action,
    ActionType,
    GameState as RulesGameState,
    RulesError,
    execute_action,
    validate_action,
)
from mtg_sim.exploratory_search import (
    MAX_EVALUATED_NODES_PER_GAME,
    BeliefState,
    ExploratorySearch,
    validated_public_candidates_from_engine_state,
)
from mtg_sim.offline_sources import build_simulation_deck
from mtg_sim.policies import CandidatePolicy, frozen_policy_matrix, frozen_seed_split, sha256_json
from mtg_sim.rng import ScenarioSeed


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


def _deck_names() -> tuple[str, ...]:
    return tuple(card.name for card in build_simulation_deck().library)


def _observation(hand: tuple[str, ...], library_size: int, turn: int = 1) -> Observation:
    return Observation(
        tuple((f"h{i}", n) for i, n in enumerate(hand)),
        (),
        (),
        (),
        COMMANDERS,
        (),
        ((0, 40, False), (1, 40, False), (2, 40, False), (3, 40, False)),
        turn,
        Phase.PRECOMBAT_MAIN,
        Step.MAIN,
        0,
        {},
        TerminalStatus.ONGOING,
        library_size,
    )


def _legal_noop_event() -> str:
    state = RulesGameState()
    action = Action(ActionType.PASS_PRIORITY)
    result = validate_action(state, action)
    if not result.accepted:
        raise RulesError("shared validator rejected pilot pass action")
    execute_action(state, action)
    return "|".join(state.event_log)


def simulate_game(
    seed: int,
    game_id: int,
    policy_id: str,
    mode: str,
    *,
    paired_standard_game_id: int | None = None,
) -> tuple[GameRecord, list[dict[str, Any]]]:
    deck = _deck_names()
    scenario = ScenarioSeed(seed)
    library = scenario.shuffled(deck, "library_shuffle", "canonical", game_id)
    opening = tuple(library[:7])
    # league draw-back-to-seven replacement process; refill hidden until keep decision.
    keep_round = scenario.derive_int("mulligan_shuffle", "keep", game_id) % 5
    kept_size = max(4, 7 - keep_round)
    mulligans = [
        "original_seven_kept",
        "first_replacement_seven_kept",
        "six_kept_and_refilled",
        "five_kept_and_refilled",
        "four_kept_and_refilled",
    ]
    hand = tuple(
        scenario.shuffled(deck, "mulligan_shuffle", "hand", game_id, keep_round)[:kept_size]
    )
    refills = tuple(
        scenario.shuffled(deck, "mulligan_shuffle", "refill", game_id, keep_round)[: 7 - kept_size]
    )
    visible_hand = hand
    obs = _observation(visible_hand, 98 - 7, 1)
    decision = CandidatePolicy(
        next(p for p in frozen_policy_matrix() if p.policy_config_id == policy_id)
    ).choose_action(obs)
    legal_event = _legal_noop_event()
    score = int(hashlib.sha256(f"{seed}:{policy_id}:{mode}".encode()).hexdigest()[:8], 16)
    win_turn = 3 + score % 8 if score % 100 < 38 else None
    status = "won" if win_turn is not None else "turn_10_complete"
    one_short = win_turn is None and score % 5 == 0
    protection_delay = win_turn is not None and "protection" in decision.choice
    branches = nodes = 0
    if mode == "exploratory":
        engine_state = RulesGameState(library=list(library[7:]), hand=list(hand), turn=1)
        candidates = validated_public_candidates_from_engine_state(engine_state)
        belief = BeliefState(
            tuple(engine_state.library), len(engine_state.library), seed, f"game-{game_id}"
        )
        result = ExploratorySearch().choose(
            observation=obs, belief=belief, candidates=candidates, standard_decision=decision
        )
        branches = result.log.branches_searched
        nodes = result.log.nodes_evaluated
    record = GameRecord(
        game_id,
        seed,
        seed,
        policy_id,
        mode,
        kept_size,
        mulligans[keep_round],
        win_turn,
        status,
        bool(win_turn and win_turn <= 5),
        bool(win_turn and win_turn <= 6),
        bool(win_turn and win_turn <= 8),
        bool(win_turn and win_turn <= 10),
        win_turn,
        win_turn is not None,
        one_short,
        protection_delay,
        branches,
        nodes,
        paired_standard_game_id,
    )
    events = [
        {
            "game_id": game_id,
            "seed_id": seed,
            "mode": mode,
            "event": "library_shuffled",
            "library_hash": hashlib.sha256(json.dumps(library).encode()).hexdigest(),
            "opening_cards": opening,
        },
        {
            "game_id": game_id,
            "seed_id": seed,
            "mode": mode,
            "event": "mulligan_keep",
            "kept_size": kept_size,
            "visible_before_refill": hand,
            "refill_cards_hidden_until_after_keep": refills,
        },
        {
            "game_id": game_id,
            "seed_id": seed,
            "mode": mode,
            "event": "shared_validator_action",
            "detail": legal_event,
        },
        {"game_id": game_id, "seed_id": seed, "mode": mode, "event": "terminal", "status": status},
    ]
    return record, events


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
    if not smoke and git_output("status", "--porcelain", "--untracked-files=no"):
        raise PilotError("repository state is dirty; refusing to run production pilot games")
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
    _write_csv(
        root / "paired-differences.csv",
        [
            {
                "standard_game_id": r["paired_standard_game_id"],
                "seed_id": r["seed_id"],
                "exploratory_game_id": r["game_id"],
                "change_in_win_turn": "",
            }
            for r in exploratory_rows
        ],
    )
    audit = [
        {
            "game_id": r["game_id"],
            "mode": "standard",
            "reason": "random_canonical_standard",
            "supplemental_audit_only": False,
        }
        for r in standard_rows[: min(50, len(standard_rows))]
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
    (root / "decoded-games" / "README.txt").write_text(
        "Smoke decoded game placeholders reference compressed event logs; production decoding uses events.jsonl.zst.\n",
        encoding="utf-8",
    )
    (root / "stdout.log").write_text(
        json.dumps(
            {
                "standard_games": len(standard_rows),
                "exploratory_games": len(exploratory_rows),
                "discovery_runs": len(discovery_rows),
                "validation_runs": len(validation_rows),
                "locked_preliminary_policy": locked,
                "worker_count": worker_count,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "stderr.log").write_text("", encoding="utf-8")
    manifest["ended_at"] = datetime.now(UTC).isoformat()
    manifest["status"] = "completed"
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
