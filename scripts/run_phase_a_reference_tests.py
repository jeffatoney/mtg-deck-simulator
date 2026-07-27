#!/usr/bin/env python3
"""Run frozen Phase A evidence against candidate packages in a closed world."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

STAGED_REFERENCE_PATHS = (
    "automation/reference-scenarios.json",
    "automation/reference-scenario.schema.json",
    "automation/trace-invariants.json",
    "automation/golden-replay.schema.json",
    "automation/golden-replay-approvals.json",
    "automation/phase-a-reference-manifest.json",
    "tests/fixtures/golden-replays",
    "scripts/phase_a_runtime_guard.py",
    "scripts/check_kernel_liveness.py",
    "scripts/check_production_pilot_lock.py",
    ".github/workflows",
    "docs/workflows/pilot-simulation.phase-c.yml.template",
)


def _copy(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination, symlinks=False)
    elif source.is_file() and not source.is_symlink():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--referee", type=Path, default=Path("."))
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run_id = f"{args.candidate_sha[:12]}-{time.time_ns()}"
    output = args.output / run_id
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="phase-a-closed-world-") as temporary:
        stage = Path(temporary)
        for package in ("mtg_kernel", "mtg_cards"):
            _copy(args.candidate / "src" / package, stage / "src" / package)
        for relative in STAGED_REFERENCE_PATHS:
            _copy(args.referee / relative, stage / relative)
        _copy(
            args.referee / "tests/phase_a_acceptance",
            stage / "tests/phase_a_acceptance",
        )
        reference = stage / "tests/phase_a_acceptance"
        if not reference.is_dir():
            print(
                "Phase A reference suite unavailable: kernel evidence is intentionally future work"
            )
            return 2
        bootstrap_prefix = (
            "from pathlib import Path; import runpy; "
            "g=runpy.run_path('scripts/phase_a_runtime_guard.py'); "
            "g['install'](Path('.')); import pytest; "
        )
        collect_bootstrap = (
            bootstrap_prefix
            + f"code=pytest.main(['--collect-only','-q','--confcutdir={reference}', '{reference}']); "
            "g['verify_loaded'](Path('.')); raise SystemExit(code)"
        )
        env = {"PATH": os.environ.get("PATH", ""), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
        collected = subprocess.run(
            [sys.executable, "-I", "-c", collect_bootstrap],
            cwd=stage,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        (output / "collection.log").write_text(collected.stdout, encoding="utf-8")
        if collected.returncode:
            completed = collected
        else:
            run_bootstrap = (
                bootstrap_prefix
                + f"code=pytest.main(['-q','-ra','--confcutdir={reference}', '{reference}']); "
                "g['verify_loaded'](Path('.')); raise SystemExit(code)"
            )
            completed = subprocess.run(
                [sys.executable, "-I", "-c", run_bootstrap],
                cwd=stage,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
        (output / "pytest.log").write_text(completed.stdout, encoding="utf-8")
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "candidate_sha": args.candidate_sha,
            "exit_code": completed.returncode,
            "collected_node_ids": [line for line in collected.stdout.splitlines() if "::" in line],
            "staged_files": sorted(
                p.relative_to(stage).as_posix() for p in stage.rglob("*") if p.is_file()
            ),
            "staging_digest": hashlib.sha256(
                "\n".join(
                    sorted(p.relative_to(stage).as_posix() for p in stage.rglob("*") if p.is_file())
                ).encode()
            ).hexdigest(),
        }
        (output / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
