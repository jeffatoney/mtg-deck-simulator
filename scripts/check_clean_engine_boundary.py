"""Static tripwire for clean-engine boundary violations.

SCOPE -- read this before trusting the result.

This is a TRIPWIRE, not the boundary. It catches honest mistakes quickly and cheaply
at review time. It cannot be made complete: the set of ways a Python module can reach
another module is unbounded (``sys.modules`` lookups, ``getattr`` on a module object,
``pkgutil.resolve_name``, names assembled from ``chr()`` arithmetic, and so on).
Four previous rounds of hardening on this class of check each produced a new bypass.

The primary structural boundary is that ``legacy/mtg_sim`` is not an installed
package, so ordinary imports through Python's package resolver fail. That does not
prevent arbitrary file execution or every custom loader. The session-wide audit hook
in ``tests/conftest.py`` and this tripwire provide additional reviewed/tested layers.

Recorded as a known limit in ``docs/audit/GATE_KNOWN_LIMITS.md``.

WHAT THIS SCANNER DOES

1. Resolves import *bindings* rather than matching import *text*. It tracks the local
   names bound by ``import importlib as il``, ``from importlib import import_module``,
   ``from importlib import import_module as f``, and plain assignment aliases of those
   names, then flags calls made through any of them.
2. Fails closed on dynamic-loading machinery in clean-engine packages, whatever the
   argument. A card-agnostic rules kernel has no legitimate need to load code at
   runtime, so the mechanism itself is the finding -- this removes the whole class of
   "the module name was not a literal" bypass rather than chasing each instance.
3. Treats a non-constant module argument as a finding rather than ignoring it. The
   previous version returned early when it could not read a literal, which meant
   obfuscation was rewarded with silence.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLEAN_ROOTS = (ROOT / "src/mtg_kernel", ROOT / "src/mtg_cards")
FORBIDDEN_ROOT = "mtg_sim"

# Callables that load code at runtime. Forbidden outright inside clean packages.
DYNAMIC_LOADERS = {
    "__import__",
    "eval",
    "exec",
    "compile",
    "importlib.import_module",
    "importlib.reload",
    "importlib.util.spec_from_file_location",
    "importlib.util.module_from_spec",
    "importlib.machinery.SourceFileLoader",
    "importlib.machinery.SourcelessFileLoader",
    "importlib.machinery.ExtensionFileLoader",
    "pkgutil.resolve_name",
    "pkgutil.get_loader",
    "runpy.run_module",
    "runpy.run_path",
    "subprocess.run",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "subprocess.Popen",
    "os.system",
    "os.execv",
    "os.popen",
}

# Modules whose entire surface is dynamic loading or process execution.
DYNAMIC_MODULES = {"importlib", "pkgutil", "runpy", "subprocess"}


def _is_forbidden_module(module_name: str) -> bool:
    return module_name == FORBIDDEN_ROOT or module_name.startswith(f"{FORBIDDEN_ROOT}.")


class _BoundaryVisitor(ast.NodeVisitor):
    """Resolve local bindings, then judge calls made through them."""

    def __init__(self, relative: str) -> None:
        self.relative = relative
        self.findings: list[str] = []
        # local name -> canonical dotted name it refers to
        self.bindings: dict[str, str] = {}

    # -- reporting ----------------------------------------------------------
    def _flag(self, node: ast.AST, message: str) -> None:
        line = getattr(node, "lineno", 0)
        self.findings.append(f"{self.relative}:{line}: {message}")

    # -- binding collection -------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            if _is_forbidden_module(alias.name):
                self._flag(node, f"forbidden import {alias.name}")
            if alias.name in DYNAMIC_MODULES or alias.name.split(".")[0] in DYNAMIC_MODULES:
                # `import importlib.util` binds `importlib` unless aliased.
                self.bindings[local] = alias.name if alias.asname else alias.name.split(".")[0]
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if _is_forbidden_module(module):
            self._flag(node, f"forbidden import from {module}")
            self.generic_visit(node)
            return
        root = module.split(".")[0]
        if root in DYNAMIC_MODULES:
            for alias in node.names:
                local = alias.asname or alias.name
                self.bindings[local] = f"{module}.{alias.name}"
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # Follow `f = import_module` / `f = importlib.import_module` aliases.
        source = self._dotted(node.value)
        if source is not None:
            canonical = self.bindings.get(source, source)
            if canonical in DYNAMIC_LOADERS or canonical in DYNAMIC_MODULES:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.bindings[target.id] = canonical
        self.generic_visit(node)

    # -- resolution ---------------------------------------------------------
    def _dotted(self, node: ast.AST) -> str | None:
        """Render a Name/Attribute chain as a dotted string."""
        parts: list[str] = []
        current: ast.AST = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if not isinstance(current, ast.Name):
            return None
        parts.append(current.id)
        return ".".join(reversed(parts))

    def _canonical(self, node: ast.AST) -> str | None:
        dotted = self._dotted(node)
        if dotted is None:
            return None
        head, _, tail = dotted.partition(".")
        bound = self.bindings.get(head)
        if bound is None:
            return dotted
        return f"{bound}.{tail}" if tail else bound

    # -- call judgement -----------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        canonical = self._canonical(node.func)
        if canonical in DYNAMIC_LOADERS:
            literal = self._constant_string(node.args[0]) if node.args else None
            if literal is not None and _is_forbidden_module(literal):
                self._flag(node, f"forbidden dynamic import of {literal} via {canonical}")
            elif literal is None and node.args:
                self._flag(
                    node,
                    f"non-constant argument to {canonical}; the clean engine may not "
                    f"load code from a computed name",
                )
            else:
                self._flag(
                    node,
                    f"dynamic loading via {canonical} is forbidden in clean-engine packages",
                )
        self.generic_visit(node)

    @staticmethod
    def _constant_string(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        # Fold simple literal concatenation: "mtg_" + "sim".
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = _BoundaryVisitor._constant_string(node.left)
            right = _BoundaryVisitor._constant_string(node.right)
            if left is not None and right is not None:
                return left + right
        if isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                else:
                    return None
            return "".join(parts)
        return None


def _scan_file(path: Path) -> list[str]:
    relative = str(path.relative_to(ROOT))
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as error:
        return [f"{relative}:{error.lineno}: syntax error: {error.msg}"]

    visitor = _BoundaryVisitor(relative)
    visitor.visit(tree)

    # A module-level string equal to the forbidden root is how a name gets smuggled
    # into a dynamic loader. Flag it wherever it appears in a clean package.
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _is_forbidden_module(node.value):
                visitor.findings.append(
                    f"{relative}:{node.lineno}: literal reference to quarantined "
                    f"package {node.value!r}"
                )
    return sorted(set(visitor.findings))


def main() -> int:
    missing = [str(path.relative_to(ROOT)) for path in CLEAN_ROOTS if not path.is_dir()]
    findings: list[str] = []
    scanned_files = 0

    for root in CLEAN_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            scanned_files += 1
            findings.extend(_scan_file(path))

    # A legacy package that is importable defeats the whole arrangement, so assert the
    # structural boundary too rather than only scanning text.
    legacy_on_import_path = (ROOT / "src" / FORBIDDEN_ROOT).exists()
    if legacy_on_import_path:
        findings.append(
            f"src/{FORBIDDEN_ROOT} exists: the quarantined package is back on the "
            f"installable import path (expected location: legacy/{FORBIDDEN_ROOT})"
        )

    if missing or findings:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "check_class": "TRIPWIRE_NOT_A_COMPLETE_GATE",
                    "forbidden_findings": findings,
                    "missing_clean_package_directories": missing,
                    "scanned_python_files": scanned_files,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "status": "PASS",
                "check_class": "TRIPWIRE_NOT_A_COMPLETE_GATE",
                "clean_package_directories": [str(p.relative_to(ROOT)) for p in CLEAN_ROOTS],
                "forbidden_import_root": FORBIDDEN_ROOT,
                "primary_boundary": (
                    f"legacy/{FORBIDDEN_ROOT} is not an installed package; see "
                    f"[tool.hatch.build.targets.wheel] in pyproject.toml"
                ),
                "scanned_python_files": scanned_files,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
