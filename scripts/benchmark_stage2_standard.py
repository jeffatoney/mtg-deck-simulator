#!/usr/bin/env python3
"""Frozen, non-pilot Stage 2 bridge STANDARD benchmark.

Each trial runs in a fresh Python process so peak memory, instrumentation counters,
and monkeypatches are isolated. The benchmark executes only bounded technical
STANDARD games; it never invokes a pilot or exploratory search.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import resource
import statistics
import subprocess
import sys
import time
from copy import deepcopy as real_deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT / "benchmarks/stage2-bridge-standard/corpus.json"


def _json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _stats(values: list[float]) -> dict[str, float]:
    return {
        "median": statistics.median(values),
        "p95": _percentile(values, 0.95),
        "minimum": min(values),
        "maximum": max(values),
    }


def _coverage_event(executor: Any, legal_actions: int, semantic_classes: int) -> dict[str, Any]:
    return {
        "turn": int(executor.state.turn.number),
        "phase": str(executor.state.turn.phase),
        "step": str(executor.state.turn.step),
        "legal_action_count": legal_actions,
        "semantic_action_class_count": semantic_classes,
    }


def _worker(seed: int, corpus: dict[str, Any]) -> dict[str, Any]:
    import mtg_kernel.engine as engine_module
    import mtg_kernel.engine_core as engine_core
    import mtg_policy.broker_core as broker_core
    import mtg_runs.phase_c_runner as runner
    from mtg_kernel.models import GameState, Zone
    from mtg_policy.broker import ActionBroker
    from mtg_policy.choices import PolicyStrategicChoiceProvider
    from mtg_policy.public_actions import public_action_classes
    from mtg_policy.standard import StandardPolicy
    from mtg_runs.replay_audit import replay_in_fresh_process

    counters: dict[str, int] = {
        "decision_count": 0,
        "legal_action_count": 0,
        "semantic_action_class_count": 0,
        "broker_refresh_count": 0,
        "state_clone_count": 0,
        "max_legal_action_count": 0,
        "max_semantic_action_class_count": 0,
    }
    coverage: dict[str, dict[str, Any]] = {}
    thresholds = dict(corpus["coverage_thresholds"])

    def mark(name: str, event: dict[str, Any]) -> None:
        coverage.setdefault(name, event)

    original_refresh = ActionBroker.refresh

    def counted_refresh(self: ActionBroker) -> tuple[dict[str, Any], tuple[Any, ...]]:
        observation, actions = original_refresh(self)
        classes = public_action_classes(actions)
        legal_count = len(actions)
        class_count = len(classes)
        counters["broker_refresh_count"] += 1
        counters["legal_action_count"] += legal_count
        counters["semantic_action_class_count"] += class_count
        counters["max_legal_action_count"] = max(counters["max_legal_action_count"], legal_count)
        counters["max_semantic_action_class_count"] = max(
            counters["max_semantic_action_class_count"], class_count
        )
        event = _coverage_event(self.executor, legal_count, class_count)
        turn = int(self.executor.state.turn.number)
        phase = str(self.executor.state.turn.phase)
        if turn <= 2 and legal_count <= int(thresholds["low_action_max_legal_actions"]):
            mark("low_action_opening_state", event)
        if phase in {"PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"} and legal_count >= int(
            thresholds["high_action_min_legal_actions"]
        ):
            mark("high_action_main_phase", event)
        land_ids = {
            str(item.arguments.get("card_object_id"))
            for item in self._actions.values()
            if item.operation == "play_land"
        }
        if len(land_ids) >= 2:
            mark("multiple_playable_lands", event)
        mana_actions = [action for action in actions if "MANA_ABILITY" in set(action.tags)]
        if len(mana_actions) >= 2:
            mark("multiple_mana_abilities", event)
        if sum(action.kind == "DECLARE_ATTACKERS" for action in actions) >= 2:
            mark("attack_choice_state", event)
        if any("PROTECTION" in set(action.tags) for action in actions):
            mark("protection_choice_state", event)
        if class_count >= int(thresholds["many_semantic_classes_minimum"]):
            mark("many_semantic_legal_action_classes", event)
        active_names = {
            str(obj.current_characteristics.get("name", ""))
            for obj in self.executor.state.objects.values()
            if not obj.retired
            and not obj.ceased_to_exist
            and obj.zone is Zone.BATTLEFIELD
            and obj.controller == self.player_id
        }
        if {
            "Malcolm, Keen-Eyed Navigator",
            "Glint-Horn Buccaneer",
            "Treasure",
        }.issubset(active_names):
            mark("malcolm_glint_horn_treasure_state", event)
        return observation, actions

    ActionBroker.refresh = counted_refresh

    original_select = StandardPolicy.select_action

    def counted_select(self: StandardPolicy, observation: Any, actions: Any) -> str:
        counters["decision_count"] += 1
        return original_select(self, observation, actions)

    StandardPolicy.select_action = counted_select

    original_choose_cards = PolicyStrategicChoiceProvider.choose_cards

    def counted_choose_cards(self: PolicyStrategicChoiceProvider, request: Any) -> Any:
        if str(request.purpose).startswith("TUTOR_"):
            mark(
                "tutor_choice_state",
                {
                    "turn": int(request.turn_number),
                    "purpose": str(request.purpose),
                    "candidate_count": len(request.candidates),
                },
            )
        if request.purpose == "DISCARD":
            mark(
                "discard_choice_state",
                {
                    "turn": int(request.turn_number),
                    "purpose": "DISCARD",
                    "candidate_count": len(request.candidates),
                    "minimum": int(request.minimum),
                },
            )
        return original_choose_cards(self, request)

    PolicyStrategicChoiceProvider.choose_cards = counted_choose_cards

    patched_modules = [engine_module, engine_core, broker_core, runner]
    originals: dict[str, Any] = {}

    def counted_deepcopy(value: Any, memo: Any = None) -> Any:
        if isinstance(value, GameState):
            counters["state_clone_count"] += 1
        return real_deepcopy(value) if memo is None else real_deepcopy(value, memo)

    for module in patched_modules:
        if hasattr(module, "deepcopy"):
            key = module.__name__
            originals[key] = module.deepcopy
            module.deepcopy = counted_deepcopy

    replay_seconds = 0.0
    original_runner_validate = runner.validate_replay

    def timed_validate_replay(payload: Any) -> Any:
        nonlocal replay_seconds
        start = time.perf_counter()
        result = original_runner_validate(payload)
        replay_seconds += time.perf_counter() - start
        return result

    runner.validate_replay = timed_validate_replay

    start = time.perf_counter()
    execution = runner.run_phase_c_game_execution(
        seed=seed,
        mode="STANDARD",
        policy_config_id=str(corpus["policy_config_id"]),
        through_turn=int(corpus["through_turn"]),
        validate_fresh_replay=bool(corpus["validate_fresh_replay_in_game"]),
        policy_actions=bool(corpus["policy_actions"]),
    )
    seconds = time.perf_counter() - start
    peak_rss_bytes = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024

    fresh_start = time.perf_counter()
    fresh = replay_in_fresh_process(execution.replay_transcript, cwd=ROOT)
    fresh_seconds = time.perf_counter() - fresh_start
    if fresh.state_hash != execution.technical_game.final_state_hash:
        raise ValueError("fresh replay diverged during Stage 2 benchmark")

    technical = execution.technical_game
    if technical.pilot_result or technical.authorized_pilot_result:
        raise ValueError("Stage 2 benchmark must never produce pilot results")
    if technical.mode != "STANDARD" or technical.search_seed is not None:
        raise ValueError("Stage 2 benchmark must remain STANDARD and non-exploratory")
    loaded_context_modules = sorted(
        name for name in sys.modules if "strategic_context" in name.lower()
    )
    if loaded_context_modules:
        raise ValueError(
            "STANDARD benchmark loaded Strategic Context modules: "
            + ", ".join(loaded_context_modules)
        )
    if technical.controlled_turns_completed == int(corpus["through_turn"]):
        mark(
            "representative_complete_10_turn_game",
            {
                "turn": technical.controlled_turns_completed,
                "terminal_status": technical.terminal_status,
            },
        )

    return {
        "seed": seed,
        "seconds_per_10_turn_game": seconds,
        "games_per_minute": 60.0 / seconds,
        "decision_count": counters["decision_count"],
        "legal_action_count": counters["legal_action_count"],
        "semantic_action_class_count": counters["semantic_action_class_count"],
        "broker_refresh_count": counters["broker_refresh_count"],
        "state_clone_count": counters["state_clone_count"],
        "replay_validation_time": replay_seconds,
        "fresh_replay_time": fresh_seconds,
        "peak_memory": peak_rss_bytes,
        "peak_memory_measurement": "process_ru_maxrss_high_water_bytes",
        "process_peak_rss_bytes": peak_rss_bytes,
        "max_legal_action_count": counters["max_legal_action_count"],
        "max_semantic_action_class_count": counters["max_semantic_action_class_count"],
        "controlled_turns_completed": technical.controlled_turns_completed,
        "terminal_status": technical.terminal_status,
        "command_count": technical.command_count,
        "final_state_hash": technical.final_state_hash,
        "replay_digest": technical.replay_digest,
        "coverage": coverage,
        "strategic_context_instantiated": False,
        "pilot_result": False,
        "authorized_pilot_result": False,
    }


def _environment() -> dict[str, Any]:
    try:
        uv_version = subprocess.check_output(["uv", "--version"], text=True).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        uv_version = "unavailable"
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "uv": uv_version,
        "runner_os": os.environ.get("RUNNER_OS"),
        "runner_arch": os.environ.get("RUNNER_ARCH"),
        "runner_name": os.environ.get("RUNNER_NAME"),
        "image_os": os.environ.get("ImageOS"),
        "image_version": os.environ.get("ImageVersion"),
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
    }


def _aggregate(corpus: dict[str, Any], trials: list[dict[str, Any]]) -> dict[str, Any]:
    metric_names = (
        "seconds_per_10_turn_game",
        "games_per_minute",
        "decision_count",
        "legal_action_count",
        "semantic_action_class_count",
        "broker_refresh_count",
        "state_clone_count",
        "replay_validation_time",
        "fresh_replay_time",
        "peak_memory",
        "process_peak_rss_bytes",
    )
    aggregate = {name: _stats([float(trial[name]) for trial in trials]) for name in metric_names}
    coverage: dict[str, dict[str, Any]] = {}
    for trial in trials:
        for name, event in dict(trial["coverage"]).items():
            coverage.setdefault(name, {"seed": trial["seed"], **dict(event)})
    missing = sorted(set(corpus["required_coverage"]) - set(coverage))
    p95_seconds = aggregate["seconds_per_10_turn_game"]["p95"]
    p95_peak = aggregate["peak_memory"]["p95"]
    provisional_seconds = p95_seconds * 1.25
    return {
        "metrics": aggregate,
        "coverage": coverage,
        "missing_required_coverage": missing,
        "recommended_owner_review_budget": {
            "status": "PROVISIONAL_NOT_FINAL",
            "basis": "25 percent headroom over the measured p95 bridge corpus",
            "maximum_seconds_per_10_turn_game": provisional_seconds,
            "minimum_games_per_minute": 60.0 / provisional_seconds,
            "maximum_peak_memory_bytes": math.ceil(p95_peak * 1.25),
        },
    }


def _parent(corpus_path: Path, output: Path) -> int:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    if corpus.get("schema_version") != "stage2-bridge-standard-corpus-v1":
        raise ValueError("unsupported Stage 2 benchmark corpus schema")
    if corpus.get("mode") != "STANDARD":
        raise ValueError("Stage 2 bridge corpus must be STANDARD")
    if int(corpus.get("through_turn", 0)) != 10:
        raise ValueError("Stage 2 bridge corpus must use the complete Turn-10 horizon")
    trials: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for repetition in range(int(corpus["repetitions"])):
        for seed in [int(value) for value in corpus["seeds"]]:
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                "--seed",
                str(seed),
                "--corpus",
                str(corpus_path),
            ]
            completed = subprocess.run(
                command,
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            if completed.returncode != 0:
                errors.append(
                    {
                        "seed": seed,
                        "repetition": repetition + 1,
                        "stdout": completed.stdout,
                        "stderr": completed.stderr,
                    }
                )
                continue
            trial = json.loads(completed.stdout)
            trial["repetition"] = repetition + 1
            trials.append(trial)

    result: dict[str, Any] = {
        "schema_version": "stage2-bridge-standard-result-v1",
        "subject_sha": _git_sha(),
        "base_main_sha": str(corpus["base_main_sha"]),
        "corpus": corpus,
        "command": (
            "uv run python scripts/benchmark_stage2_standard.py "
            "--corpus benchmarks/stage2-bridge-standard/corpus.json --output <result.json>"
        ),
        "environment": _environment(),
        "trial_count": len(trials),
        "expected_trial_count": int(corpus["repetitions"]) * len(corpus["seeds"]),
        "trials": trials,
        "worker_errors": errors,
        "pilot_or_full_study_executed": False,
        "strategic_context_instantiated": False,
    }
    if trials:
        result["aggregate"] = _aggregate(corpus, trials)
    _json_dump(output, result)
    if errors:
        return 2
    missing = result["aggregate"]["missing_required_coverage"]
    return 3 if missing else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    if args.worker:
        if args.seed is None:
            raise ValueError("worker mode requires --seed")
        print(json.dumps(_worker(args.seed, corpus), sort_keys=True))
        return 0
    if args.output is None:
        raise ValueError("parent benchmark mode requires --output")
    return _parent(args.corpus, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
