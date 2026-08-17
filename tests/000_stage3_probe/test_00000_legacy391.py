from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROBE_PATH = ROOT / "tests/000_stage3_probe/test_stage3_probe.py"


def _probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage3_legacy391_probe_impl",
        PROBE_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_legacy_391_first_access_menu() -> None:
    probe = _probe()
    state, seed_text, snapshot = probe._capture_first_access(
        "legacy-391",
        391730338978874520,
        legacy=True,
    )
    payload = {
        "schema_version": "pr100-stage3-legacy391-probe-v1",
        "state": probe._state_facts(state, snapshot),
        "menu_and_legacy_selection": probe._public_menu_and_selection(
            state,
            seed_text,
            legacy=True,
        ),
    }
    pytest.exit(
        "STAGE3_LEGACY391_PROBE="
        + json.dumps(payload, sort_keys=True, separators=(",", ":")),
        returncode=1,
    )
