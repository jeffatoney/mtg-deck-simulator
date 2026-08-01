"""Temporary exact-head source export for focused local validation."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def test_export_exact_head_workspace_into_existing_ci_artifact() -> None:
    root = Path.cwd()
    runner_temp = Path(os.environ["RUNNER_TEMP"])
    staging = runner_temp / "phase-b-workspace-export"
    staging.mkdir(parents=True, exist_ok=True)
    for path in ("src", "tests", "docs/spec", "scripts"):
        source = root / path
        destination = staging / path
        shutil.copytree(source, destination, dirs_exist_ok=True)
    for path in ("pyproject.toml", "uv.lock", ".python-version"):
        shutil.copy2(root / path, staging / path)
    destination = runner_temp / "phase-a-result" / "phase-b-workspace"
    destination.parent.mkdir(parents=True, exist_ok=True)
    archive = Path(shutil.make_archive(str(destination), "zip", staging))
    assert archive.is_file()
