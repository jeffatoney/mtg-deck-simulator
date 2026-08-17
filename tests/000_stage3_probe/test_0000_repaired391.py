from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
SLOW_PROBE = ROOT / "tests/000_stage3_probe/test_stage3_probe.py"


def _load_probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location("stage3_repaired_probe", SLOW_PROBE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_repaired_391_first_access_probe() -> None:
    probe = _load_probe()
    state, seed_text, snapshot = probe._capture_first_access(
        "repaired-391",
        391730338978874520,
        legacy=False,
    )
    payload: dict[str, Any] = {
        "schema_version": "pr100-stage3-repaired391-probe-v1",
        "state": probe._state_facts(state, snapshot),
        "menu_and_standard_selection": probe._public_menu_and_selection(
            state,
            seed_text,
            legacy=False,
        ),
    }
    pytest.exit(
        "STAGE3_REPAIRED391_PROBE="
        + json.dumps(payload, sort_keys=True, separators=(",", ":")),
        returncode=1,
    )
