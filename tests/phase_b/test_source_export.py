"""Temporary source export for exact ordinary Git object reconstruction."""

from __future__ import annotations

import os
from pathlib import Path


def test_export_exact_engine_source_into_existing_ci_artifact() -> None:
    runner_temp = Path(os.environ["RUNNER_TEMP"])
    destination = runner_temp / "phase-a-result" / "exported-engine.py"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(Path("src/mtg_kernel/engine.py").read_bytes())
    assert destination.read_bytes() == Path("src/mtg_kernel/engine.py").read_bytes()
