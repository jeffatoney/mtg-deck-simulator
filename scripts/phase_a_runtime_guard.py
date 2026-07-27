"""Frozen runtime import boundary used by the protected-main reference runner."""

from __future__ import annotations

import importlib.abc
import sys
import sysconfig
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
    isolated_path = list(sys.path)
    standard_paths = {
        str(Path(value).resolve())
        for key in ("stdlib", "platstdlib")
        if (value := sysconfig.get_path(key))
    }
    dependency_paths = {
        str(Path(item).resolve()) for item in isolated_path if "site-packages" in Path(item).parts
    }
    approved = standard_paths | dependency_paths
    sys.path[:] = [
        str(source),
        *[
            item
            for item in isolated_path
            if str(Path(item).resolve()) in approved
            or any(root in Path(item).resolve().parents for root in map(Path, standard_paths))
        ],
    ]
    return guard


def verify_loaded(staging_root: Path) -> None:
    source = (staging_root / "src").resolve()
    for name, module in tuple(sys.modules.items()):
        if name in {"mtg_kernel", "mtg_cards"} or name.startswith(("mtg_kernel.", "mtg_cards.")):
            spec = getattr(module, "__spec__", None)
            origin = getattr(spec, "origin", None)
            locations = tuple(getattr(spec, "submodule_search_locations", ()) or ())
            origin_ok = bool(origin and source in Path(origin).resolve().parents)
            namespace_ok = bool(locations) and all(
                source == Path(location).resolve() or source in Path(location).resolve().parents
                for location in locations
            )
            if not (origin_ok or namespace_ok):
                raise RuntimeError(f"unapproved module provenance: {name}: {origin}")
