"""Clean-engine contamination guard, active for the whole test session.

Two channels are audited:

*linkage* -- any attempt to import the quarantined legacy package;
*provenance* -- any attempt to read a legacy-produced artifact as input.

``sys.addaudithook`` is used rather than a ``sys.meta_path`` finder or an
``__import__`` patch on purpose. An audit hook cannot be removed once installed
(CPython provides no API to pop one), so code under test cannot disable the guard
the way it can pop a meta-path entry. It also fires for *every* import, including
imports written inside a function body, which an import-time module sweep misses
entirely -- and a lazy import inside a function is the natural shape of an
accidental legacy dependency.

The guard is defence in depth. The structural boundary is that
``legacy/mtg_sim`` is not an installed package and therefore is unavailable through
ordinary package resolution (see ``[tool.hatch.build.targets.wheel]`` in
``pyproject.toml``). Arbitrary file execution remains possible in Python; this hook
makes tested import and provenance violations explicit.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_IMPORT_ROOT = "mtg_sim"

# Directories whose contents were produced by, or belong to, the legacy engine.
# Reading any of these during a test is a provenance violation: it means a clean
# result is being compared against legacy output.
FORBIDDEN_READ_ROOTS = (
    ROOT / "artifacts",
    ROOT / "legacy",
)

# Frozen inputs the clean engine is entitled to read.
ALLOWED_READ_ROOTS = (
    ROOT / "docs" / "source",
    ROOT / "docs" / "spec",
    ROOT / "tests",
    ROOT / "src",
    ROOT / "automation",
    ROOT / "configs",
)


class CleanEngineBoundaryViolation(RuntimeError):
    """Raised when a test crosses the clean-engine boundary."""


def _is_forbidden_module(name: str) -> bool:
    # Exact match or a true submodule. A bare ``startswith`` would also reject an
    # unrelated future package such as ``mtg_simulator``.
    return name == FORBIDDEN_IMPORT_ROOT or name.startswith(f"{FORBIDDEN_IMPORT_ROOT}.")


_FORBIDDEN_HINTS = tuple(path.name for path in FORBIDDEN_READ_ROOTS)


def _is_forbidden_read(raw_path: object) -> Path | None:
    if isinstance(raw_path, bytes):
        try:
            raw_path = raw_path.decode()
        except UnicodeDecodeError:
            return None
    if not isinstance(raw_path, str):
        # int -> already-open descriptor; anything else is not a path we can judge.
        return None

    # Fast reject before touching the filesystem. The audit hook runs on every open
    # in the process, including pytest's own, so the common case must stay cheap.
    if not any(hint in raw_path for hint in _FORBIDDEN_HINTS):
        return None

    try:
        resolved = Path(raw_path).resolve()
    except (OSError, ValueError):
        return None

    for allowed in ALLOWED_READ_ROOTS:
        if resolved.is_relative_to(allowed):
            return None
    for forbidden in FORBIDDEN_READ_ROOTS:
        if resolved.is_relative_to(forbidden):
            return resolved
    return None


def _audit(event: str, args: tuple[object, ...]) -> None:
    if event == "import":
        name = args[0]
        if isinstance(name, str) and _is_forbidden_module(name):
            raise CleanEngineBoundaryViolation(
                f"clean-engine boundary violation: import of quarantined module {name!r}. "
                f"{FORBIDDEN_IMPORT_ROOT} is ARCHIVAL_REFERENCE_ONLY and is not an "
                f"installed package; the clean engine may not link against it."
            )
    elif event == "open":
        offending = _is_forbidden_read(args[0])
        if offending is not None:
            raise CleanEngineBoundaryViolation(
                f"clean-engine boundary violation: read of legacy artifact "
                f"{offending.relative_to(ROOT)}. Legacy output is "
                f"PROHIBITED_AS_PHASE_A_EVIDENCE and may not be used as test input."
            )


sys.addaudithook(_audit)
