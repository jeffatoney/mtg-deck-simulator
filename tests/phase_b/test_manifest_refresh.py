"""Deterministic refresh coverage for the handoff manifest."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


def load_script() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts/check_manifest.py"
    spec = importlib.util.spec_from_file_location("check_manifest_for_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_write_mode_refreshes_existing_entries_and_then_validates(
    tmp_path: Path, monkeypatch
) -> None:
    module = load_script()
    alpha = tmp_path / "alpha.txt"
    beta = tmp_path / "beta.txt"
    alpha.write_text("alpha\n", encoding="utf-8")
    beta.write_text("beta\n", encoding="utf-8")
    manifest = tmp_path / "HANDOFF_MANIFEST.json"
    manifest.write_text(
        json.dumps(
            {
                "beta.txt": {"bytes": 0, "sha256": "stale"},
                "alpha.txt": {"bytes": 0, "sha256": "stale"},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "MANIFEST", manifest)
    monkeypatch.setattr(module, "REQUIRED_TRACKED_PATHS", ("alpha.txt", "beta.txt"))
    monkeypatch.setattr(module, "is_tracked", lambda _relative: True)

    assert module.main(["--write"]) == 0
    refreshed = json.loads(manifest.read_text(encoding="utf-8"))
    assert list(refreshed) == ["alpha.txt", "beta.txt"]
    assert refreshed["alpha.txt"] == {
        "bytes": alpha.stat().st_size,
        "sha256": module.sha256(alpha),
    }
    assert refreshed["beta.txt"] == {
        "bytes": beta.stat().st_size,
        "sha256": module.sha256(beta),
    }
    assert module.main([]) == 0

    alpha.write_text("changed\n", encoding="utf-8")
    assert module.main([]) == 1
    assert module.main(["--write"]) == 0
    assert module.main([]) == 0


def test_write_mode_refuses_missing_or_untracked_files(tmp_path: Path, monkeypatch) -> None:
    module = load_script()
    manifest = tmp_path / "HANDOFF_MANIFEST.json"
    original = {"missing.txt": {"bytes": 1, "sha256": "x"}}
    manifest.write_text(json.dumps(original), encoding="utf-8")

    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "MANIFEST", manifest)
    monkeypatch.setattr(module, "REQUIRED_TRACKED_PATHS", ())
    monkeypatch.setattr(module, "is_tracked", lambda _relative: False)

    assert module.main(["--write"]) == 1
    assert json.loads(manifest.read_text(encoding="utf-8")) == original
