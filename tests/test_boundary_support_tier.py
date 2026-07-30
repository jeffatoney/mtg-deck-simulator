"""Negative coverage for the installed SUPPORT-package boundary tier."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _run(cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(cwd / "scripts/check_clean_engine_boundary.py")],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    for relative in ("scripts", "src"):
        shutil.copytree(ROOT / relative, tmp_path / relative, dirs_exist_ok=True)
    return tmp_path


def test_current_strict_and_support_packages_pass(sandbox: Path) -> None:
    result = _run(sandbox)
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert "src/mtg_verify" in payload["support_package_directories"]


@pytest.mark.parametrize(
    "source",
    [
        "import mtg_sim\n",
        "from mtg_sim import engine\n",
        "import importlib\nimportlib.import_module('json')\n",
        "TARGET = 'mtg_sim'\n",
        "import subprocess\nsubprocess.run(['echo', 'ok'], check=False)\n",
    ],
)
def test_support_package_probe_is_rejected(sandbox: Path, source: str) -> None:
    (sandbox / "src/mtg_verify/_probe.py").write_text(source, encoding="utf-8")
    result = _run(sandbox)
    assert result.returncode == 1, result.stdout
    assert json.loads(result.stdout)["forbidden_findings"]


def test_support_process_allowlist_is_file_and_call_specific(sandbox: Path) -> None:
    (sandbox / "src/mtg_sources/_probe.py").write_text(
        "import subprocess\nsubprocess.check_output(['echo', 'ok'])\n", encoding="utf-8"
    )
    result = _run(sandbox)
    assert result.returncode == 1
    assert "not allowlisted" in result.stdout


def test_strict_package_still_forbids_process_execution(sandbox: Path) -> None:
    (sandbox / "src/mtg_kernel/_probe.py").write_text(
        "import subprocess\nsubprocess.run(['echo', 'ok'], check=False)\n", encoding="utf-8"
    )
    result = _run(sandbox)
    assert result.returncode == 1
    assert "STRICT" in result.stdout
