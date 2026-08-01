"""Temporary exact-head source export for focused local validation."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def test_export_exact_head_workspace_into_existing_ci_artifact() -> None:
    root = Path.cwd()
    runner_temp = Path(os.environ["RUNNER_TEMP"])
    staging = runner_temp / "phase-b-workspace-export"
    shutil.copytree(
        root,
        staging,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            ".pytest_cache",
            ".ruff_cache",
            ".mypy_cache",
            "__pycache__",
            "legacy",
        ),
    )
    destination = runner_temp / "phase-a-result" / "phase-b-workspace"
    destination.parent.mkdir(parents=True, exist_ok=True)
    archive = Path(shutil.make_archive(str(destination), "zip", staging))
    assert archive.is_file()
