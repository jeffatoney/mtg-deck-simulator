#!/usr/bin/env python3
"""Protected-main control-plane comparison and attack-matrix validation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

FROZEN = (
    "tests/acceptance/PHASE_A_ACCEPTANCE_SPEC.md",
    "automation/frozen-spec-sha256.txt",
    "automation/architecture-invariants.json",
    "automation/architecture-attack-matrix.json",
    "scripts/check_architecture_invariants.py",
    "scripts/check_production_pilot_lock.py",
    "scripts/run_phase_a_reference_tests.py",
    "scripts/validate_phase_a_reference_suite.py",
    "scripts/phase_a_runtime_guard.py",
    "scripts/check_kernel_liveness.py",
    "automation/reference-scenarios.json",
    "automation/reference-scenario.schema.json",
    "automation/phase-a-reference-manifest.json",
    "automation/trace-invariants.json",
    "automation/golden-replay.schema.json",
    "automation/golden-replay-approvals.json",
    "tests/fixtures/golden-replays/README.md",
    "tests/phase_a_reference/test_reference_contract.py",
    "tests/phase_a_reference/test_forced_scenarios.py",
    "tests/phase_a_reference/test_trace_invariants.py",
    "tests/phase_a_reference/test_replay_contract.py",
    "tests/phase_a_reference/test_analytics_contract.py",
    "tests/phase_a_reference/reference_adapter.py",
    "tests/fixtures/golden-replays/sol-ring.json",
    "tests/fixtures/golden-replays/soul-guide-lantern-targeted-etb.json",
    "tests/fixtures/golden-replays/malcolm-counterspell-commit.json",
    "tests/fixtures/golden-replays/dualcaster-twinflame.json",
    "tests/fixtures/golden-replays/glint-horn-attack-cleanup.json",
    "tests/fixtures/golden-replays/illegal-target-before-resolution.json",
    "tests/fixtures/golden-replays/additional-cleanup.json",
    "tests/fixtures/golden-replays/commander-replacement.json",
    "tests/fixtures/golden-replays/empty-library-loss.json",
    ".github/workflows/architecture-referee.yml",
    ".github/workflows/phase-a-isolated-acceptance.yml",
    "prompts/recovery/PHASE_A_KERNEL.md",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(referee: Path, candidate: Path) -> list[str]:
    errors: list[str] = []
    for relative in FROZEN:
        expected, actual = referee / relative, candidate / relative
        if actual.is_symlink():
            errors.append(f"symlink substitution: {relative}")
        elif not actual.is_file():
            errors.append(f"missing or replaced: {relative}")
        elif not expected.is_file() or digest(expected) != digest(actual):
            errors.append(f"differs from protected main: {relative}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--referee", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--protected-main-sha")
    parser.add_argument("--candidate-sha")
    parser.add_argument("--attack-matrix", action="store_true")
    args = parser.parse_args()
    if args.attack_matrix:
        data = json.loads((args.referee / "automation/architecture-attack-matrix.json").read_text())
        errors = (
            []
            if data.get("families") and all(data["families"].values())
            else ["empty attack family"]
        )
    else:
        errors = compare(args.referee, args.candidate)
        if not args.protected_main_sha or not args.candidate_sha:
            errors.append("missing referee/candidate provenance")
    print(f"Control plane: {'PASS' if not errors else 'FAIL'}")
    for error in errors:
        print(f"- {error}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
