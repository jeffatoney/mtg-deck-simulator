from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
SLOW_PROBE = ROOT / "tests/000_stage3_probe/test_stage3_probe.py"
ARCHIVE = (
    ROOT / "docs/audit/phase-c-postpilot/evidence/pr100-glint-horn-repaired-behavior-4d15c185.zip"
)


def _load_probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location("stage3_slow_probe", SLOW_PROBE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_stage3_quick_first_access_probe() -> None:
    probe = _load_probe()
    with zipfile.ZipFile(ARCHIVE) as bundle:
        raw_timelines = {
            name.removesuffix(".json"): probe._raw_timeline(json.loads(bundle.read(name)))
            for name in sorted(bundle.namelist())
        }

    captured: dict[str, tuple[Any, str, dict[str, Any]]] = {
        "repaired-391": probe._capture_first_access(
            "repaired-391",
            391730338978874520,
            legacy=False,
        ),
        "legacy-391": probe._capture_first_access(
            "legacy-391",
            391730338978874520,
            legacy=True,
        ),
        "legacy-101": probe._capture_first_access(
            "legacy-101",
            101,
            legacy=True,
        ),
    }
    positive: dict[str, Any] = {}
    for label, (state, seed_text, snapshot) in captured.items():
        positive[label] = {
            "state": probe._state_facts(state, snapshot),
            "menu_and_standard_selection": probe._public_menu_and_selection(
                state,
                seed_text,
                legacy=label.startswith("legacy-"),
            ),
        }

    payload = {
        "schema_version": "pr100-stage3-quick-probe-v1",
        "positive_first_access_states": positive,
        "raw_archive_timelines": raw_timelines,
    }
    pytest.exit(
        "STAGE3_QUICK_PROBE=" + json.dumps(payload, sort_keys=True, separators=(",", ":")),
        returncode=1,
    )
