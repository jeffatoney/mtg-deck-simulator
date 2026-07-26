"""Frozen runtime import boundary used by the protected-main reference runner."""

from __future__ import annotations

import importlib.abc
import sys
from pathlib import Path


class PhaseAImportGuard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path: object = None, target: object = None) -> None:
        del path, target
        if fullname == "mtg_sim" or fullname.startswith("mtg_sim."):
            raise ImportError(f"Phase A closed world rejects {fullname}")
        return None


def install(staging_root: Path) -> PhaseAImportGuard:
    if any(name == "mtg_sim" or name.startswith("mtg_sim.") for name in sys.modules):
        raise RuntimeError("mtg_sim was present before the Phase A guard")
    guard = PhaseAImportGuard()
    sys.meta_path.insert(0, guard)
    source = (staging_root / "src").resolve()
    sys.path[:] = [str(source), *[item for item in sys.path if "site-packages" in item]]
    return guard


def verify_loaded(staging_root: Path) -> None:
    source = (staging_root / "src").resolve()
    for name, module in tuple(sys.modules.items()):
        if name in {"mtg_kernel", "mtg_cards"} or name.startswith(("mtg_kernel.", "mtg_cards.")):
            origin = getattr(getattr(module, "__spec__", None), "origin", None)
            if not origin or source not in Path(origin).resolve().parents:
                raise RuntimeError(f"unapproved module provenance: {name}: {origin}")
