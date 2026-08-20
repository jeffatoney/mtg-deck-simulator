#!/usr/bin/env python3
"""Mandatory exact-deck Phase C production-policy Turn-10/replay smoke."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mtg_runs.phase_c_runner import run_phase_c_game_execution  # noqa: E402


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
    # The public-policy noninterference repair intentionally replaces the prior
    # hidden-state-dependent final tie-break. Keep the same frozen smoke seed but
    # lock its repaired STANDARD result rather than tuning the new public order to
    # reproduce the historical tie outcome.
    if measurement.actual_first_attempt_turn is not None:
        errors.append("repaired public-policy seed 101 actual-attempt baseline drifted")
    if measurement.attempt_package is not None:
        errors.append("repaired public-policy seed 101 attempt-package baseline drifted")
    if set(measurement.checkpoint_table_win_access) != {5, 6, 8, 10}:
        errors.append("Turn-10 measurement omits a frozen checkpoint")
    if len(measurement.combo_records) != 24:
        errors.append("Turn-10 measurement does not record six packages at four checkpoints")
    if execution.replay_transcript.get("digest") != game.replay_digest:
        errors.append("Turn-10 replay transcript digest is inconsistent")
    result = {
        "status": "FAIL" if errors else "PASS",
        "controlled_turns_completed": game.controlled_turns_completed,
        "command_count": game.command_count,
        "fresh_replay_equal": game.final_state_hash == game.fresh_replay_state_hash,
        "actual_first_attempt_turn": measurement.actual_first_attempt_turn,
        "attempt_package": measurement.attempt_package,
        "combo_record_count": len(measurement.combo_records),
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
