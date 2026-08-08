#!/usr/bin/env python3
"""Mandatory exact-deck Phase C production-policy Turn-10/replay smoke."""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mtg_runs.phase_c_runner import run_phase_c_game_execution  # noqa: E402

_DIAGNOSTIC_BASELINE = "9a35fdd4fdb8e7ef7528e2188ee1ed1db99d3903"


def _action_signature(action: dict[str, Any]) -> tuple[Any, ...]:
    return (
        action.get("turn"),
        action.get("phase"),
        action.get("step"),
        action.get("kind"),
        action.get("identity"),
    )


def _baseline_diagnostics() -> dict[str, Any]:
    """Run the last known-good seed-101 code in a temporary worktree for diagnosis only."""

    with tempfile.TemporaryDirectory(prefix="phase-c-turn10-baseline-") as temporary:
        worktree = Path(temporary) / "repo"
        add = subprocess.run(
            [
                "git",
                "worktree",
                "add",
                "--detach",
                str(worktree),
                _DIAGNOSTIC_BASELINE,
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if add.returncode != 0:
            return {"error": "baseline worktree creation failed", "stderr": add.stderr[-2000:]}
        try:
            code = """
import json
from dataclasses import asdict
from mtg_runs.phase_c_runner import run_phase_c_game_execution
execution = run_phase_c_game_execution(
    seed=101,
    mode='STANDARD',
    through_turn=10,
    validate_fresh_replay=True,
    policy_actions=True,
)
measurement = execution.measurement
print(json.dumps({
    'actual_first_attempt_turn': measurement.actual_first_attempt_turn,
    'attempt_package': measurement.attempt_package,
    'command_count': execution.technical_game.command_count,
    'selected_actions': list(measurement.extra.get('selected_actions', ())),
    'malcolm_glint_horn': [
        asdict(record)
        for record in measurement.combo_records
        if record.package == 'malcolm_glint_horn'
    ],
}, sort_keys=True))
"""
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(worktree / "src")
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=worktree,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if completed.returncode != 0:
                return {
                    "error": "baseline execution failed",
                    "stderr": completed.stderr[-4000:],
                    "stdout": completed.stdout[-4000:],
                }
            return json.loads(completed.stdout)
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )


def _first_action_divergence(
    current: tuple[dict[str, Any], ...], baseline: list[dict[str, Any]]
) -> dict[str, Any] | None:
    limit = min(len(current), len(baseline))
    for index in range(limit):
        if _action_signature(current[index]) != _action_signature(baseline[index]):
            start = max(0, index - 4)
            end = index + 6
            return {
                "index": index,
                "current_window": list(current[start:end]),
                "baseline_window": baseline[start:end],
            }
    if len(current) != len(baseline):
        return {
            "index": limit,
            "current_window": list(current[max(0, limit - 4) : limit + 6]),
            "baseline_window": baseline[max(0, limit - 4) : limit + 6],
        }
    return None


def main() -> int:
    execution = run_phase_c_game_execution(
        seed=101,
        mode="STANDARD",
        through_turn=10,
        validate_fresh_replay=True,
        policy_actions=True,
    )
    game = execution.technical_game
    measurement = execution.measurement
    errors: list[str] = []
    if game.controlled_turns_completed != 10:
        errors.append("production policy did not reach controlled Turn 10")
    if game.final_state_hash != game.fresh_replay_state_hash:
        errors.append("fresh-process replay diverged from the Turn-10 final state")
    if game.command_count < 100:
        errors.append("Turn-10 production run recorded implausibly few commands")
    if measurement.actual_first_attempt_turn != 10:
        errors.append("frozen seed 101 no longer records its first actual attempt on Turn 10")
    if measurement.attempt_package != "malcolm_glint_horn":
        errors.append("frozen seed 101 no longer attempts the expected Malcolm/Glint-Horn line")
    if set(measurement.checkpoint_table_win_access) != {5, 6, 8, 10}:
        errors.append("Turn-10 measurement omits a frozen checkpoint")
    if len(measurement.combo_records) != 24:
        errors.append("Turn-10 measurement does not record six packages at four checkpoints")
    if execution.replay_transcript.get("digest") != game.replay_digest:
        errors.append("Turn-10 replay transcript digest is inconsistent")

    selected_actions = tuple(measurement.extra.get("selected_actions", ()))
    combo_blockers = dict(measurement.extra.get("combo_checkpoint_blockers", {}))
    malcolm_glint_horn = [
        asdict(record)
        for record in measurement.combo_records
        if record.package == "malcolm_glint_horn"
    ]
    relevant_cards = [
        asdict(record)
        for record in measurement.card_records
        if record.card_name in {"Malcolm, Keen-Eyed Navigator", "Glint-Horn Buccaneer", "Curiosity"}
    ]
    baseline = _baseline_diagnostics() if errors else {}
    baseline_actions = baseline.get("selected_actions", []) if isinstance(baseline, dict) else []
    divergence = (
        _first_action_divergence(selected_actions, baseline_actions)
        if isinstance(baseline_actions, list)
        else None
    )
    if isinstance(baseline, dict):
        baseline.pop("selected_actions", None)

    result = {
        "status": "FAIL" if errors else "PASS",
        "controlled_turns_completed": game.controlled_turns_completed,
        "command_count": game.command_count,
        "fresh_replay_equal": game.final_state_hash == game.fresh_replay_state_hash,
        "actual_first_attempt_turn": measurement.actual_first_attempt_turn,
        "attempt_package": measurement.attempt_package,
        "combo_record_count": len(measurement.combo_records),
        "checkpoint_table_win_access": dict(measurement.checkpoint_table_win_access),
        "primary_failure": dict(measurement.primary_failure),
        "malcolm_glint_horn_combo_records": malcolm_glint_horn,
        "malcolm_glint_horn_blockers": {
            turn: packages.get("malcolm_glint_horn", [])
            for turn, packages in combo_blockers.items()
            if isinstance(packages, dict)
        },
        "relevant_card_records": relevant_cards,
        "selected_action_count": len(selected_actions),
        "selected_actions_tail": list(selected_actions[-40:]),
        "baseline": baseline,
        "first_selected_action_divergence": divergence,
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
