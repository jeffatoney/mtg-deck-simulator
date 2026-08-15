"""Static tripwire and structural check for clean-engine boundary violations.

STRICT packages are production rules/card code and may not dynamically load code or
spawn processes. SUPPORT packages are installed tooling; process execution is allowed
only through an exact file-and-call allowlist, while dynamic imports and every reference
to the quarantined legacy package remain forbidden.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRICT_ROOTS = (
    ROOT / "src/mtg_kernel",
    ROOT / "src/mtg_cards",
    ROOT / "src/mtg_deck",
    ROOT / "src/mtg_policy",
    ROOT / "src/mtg_search",
    ROOT / "src/mtg_measure",
)
SUPPORT_ROOTS = (ROOT / "src/mtg_verify", ROOT / "src/mtg_sources", ROOT / "src/mtg_runs")
FORBIDDEN_ROOT = "mtg_sim"

CODE_LOADERS = {
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
    "os.system",
    "os.execv",
    "os.popen",
}
PROCESS_LOADERS = {
    "subprocess.run",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "subprocess.Popen",
}
DYNAMIC_MODULES = {"importlib", "pkgutil", "runpy", "subprocess", "os"}
SUPPORT_PROCESS_ALLOWLIST: dict[str, set[str]] = {
    "src/mtg_verify/phase_a.py": {"subprocess.run", "subprocess.check_output"},
    "src/mtg_verify/phase_b.py": {"subprocess.run", "subprocess.check_output"},
    "src/mtg_runs/manifests.py": {"subprocess.check_output"},
    "src/mtg_runs/replay_audit.py": {"subprocess.run"},
    # Phase C reads exact Git objects and performs a no-shell ancestry check before
    # any authorized shard can create an output directory or game result.
    "src/mtg_runs/phase_c.py": {"subprocess.check_output", "subprocess.run"},
    "src/mtg_runs/phase_c_runner.py": {"subprocess.run"},
    # Exploratory V2 uses one no-shell subprocess only to reproduce the same
    # diagnostic policy decision stream in a fresh interpreter. It cannot execute
    # pilot artifacts and remains in the SUPPORT tier.
    "src/mtg_runs/phase_c_exploratory_v2.py": {"subprocess.run"},
}
_FORBIDDEN_REFERENCE = re.compile(r"(?<![A-Za-z0-9_])mtg_sim(?![A-Za-z0-9_])")


def _is_forbidden_module(module_name: str) -> bool:
    return module_name == FORBIDDEN_ROOT or module_name.startswith(f"{FORBIDDEN_ROOT}.")


def _contains_forbidden_reference(value: str) -> bool:
    return _FORBIDDEN_REFERENCE.search(value) is not None


class _BoundaryVisitor(ast.NodeVisitor):
    def __init__(self, relative: str, tier: str) -> None:
        self.relative = relative
        self.tier = tier
        self.findings: list[str] = []
        self.bindings: dict[str, str] = {}

    def _flag(self, node: ast.AST, message: str) -> None:
        self.findings.append(f"{self.relative}:{getattr(node, 'lineno', 0)}: {message}")

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            if _is_forbidden_module(alias.name):
                self._flag(node, f"forbidden import {alias.name}")
            root = alias.name.split(".")[0]
            if root in DYNAMIC_MODULES:
                self.bindings[local] = alias.name if alias.asname else root
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if _is_forbidden_module(module):
            self._flag(node, f"forbidden import from {module}")
        if module.split(".")[0] in DYNAMIC_MODULES:
            for alias in node.names:
                self.bindings[alias.asname or alias.name] = f"{module}.{alias.name}"
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        canonical = self._canonical(node.value)
        if canonical is not None:
            if canonical in CODE_LOADERS | PROCESS_LOADERS | DYNAMIC_MODULES:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.bindings[target.id] = canonical
        self.generic_visit(node)

    @staticmethod
    def _dotted(node: ast.AST) -> str | None:
        parts: list[str] = []
        current = node
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
        return f"{bound}.{tail}" if bound and tail else bound or dotted

    def visit_Call(self, node: ast.Call) -> None:
        canonical = self._canonical(node.func)
        if canonical in CODE_LOADERS:
            self._flag(node, f"dynamic code loading via {canonical} is forbidden in {self.tier}")
        elif canonical in PROCESS_LOADERS:
            allowed = canonical in SUPPORT_PROCESS_ALLOWLIST.get(self.relative, set())
            if self.tier == "STRICT" or not allowed:
                self._flag(
                    node, f"process execution via {canonical} is not allowlisted in {self.tier}"
                )
        self.generic_visit(node)


def _scan_file(path: Path, tier: str) -> list[str]:
    relative = str(path.relative_to(ROOT))
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as error:
        return [f"{relative}:{error.lineno}: syntax error: {error.msg}"]
    visitor = _BoundaryVisitor(relative, tier)
    visitor.visit(tree)
    docstrings: set[ast.Constant] = set()
    for parent in ast.walk(tree):
        if isinstance(parent, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = parent.body
            if body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    docstrings.add(value)
    for node in ast.walk(tree):
        if node in docstrings:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _contains_forbidden_reference(node.value):
                visitor.findings.append(
                    f"{relative}:{node.lineno}: executable literal references quarantined package"
                )
    return sorted(set(visitor.findings))


def main() -> int:
    tiers = [(root, "STRICT") for root in STRICT_ROOTS] + [
        (root, "SUPPORT") for root in SUPPORT_ROOTS
    ]
    missing = [str(path.relative_to(ROOT)) for path, _ in tiers if not path.is_dir()]
    findings: list[str] = []
    scanned_files = 0
    for root, tier in tiers:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            scanned_files += 1
            findings.extend(_scan_file(path, tier))

    if (ROOT / "src" / FORBIDDEN_ROOT).exists():
        findings.append(
            f"src/{FORBIDDEN_ROOT} exists: the quarantined package is back on the "
            "installable import path"
        )

    payload = {
        "status": "FAIL" if missing or findings else "PASS",
        "check_class": "TRIPWIRE_NOT_A_COMPLETE_GATE",
        "strict_package_directories": [str(path.relative_to(ROOT)) for path in STRICT_ROOTS],
        "support_package_directories": [str(path.relative_to(ROOT)) for path in SUPPORT_ROOTS],
        "support_process_allowlist": {
            path: sorted(calls) for path, calls in SUPPORT_PROCESS_ALLOWLIST.items()
        },
        "forbidden_import_root": FORBIDDEN_ROOT,
        "forbidden_findings": findings,
        "missing_package_directories": missing,
        "primary_boundary": (
            f"legacy/{FORBIDDEN_ROOT} is not installed; see the wheel package list in pyproject.toml"
        ),
        "scanned_python_files": scanned_files,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if missing or findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
