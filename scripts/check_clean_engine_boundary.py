"""Fail if clean engine packages import or dynamically load the legacy package."""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLEAN_ROOTS = (ROOT / "src/mtg_kernel", ROOT / "src/mtg_cards")
FORBIDDEN_ROOT = "mtg_sim"


def _is_forbidden_module(module_name: str) -> bool:
    return module_name == FORBIDDEN_ROOT or module_name.startswith(f"{FORBIDDEN_ROOT}.")


def _constant_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _scan_file(path: Path) -> list[str]:
    findings: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as error:
        return [f"{path.relative_to(ROOT)}:{error.lineno}: syntax error: {error.msg}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden_module(alias.name):
                    findings.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: forbidden import {alias.name}"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module and _is_forbidden_module(node.module):
                findings.append(
                    f"{path.relative_to(ROOT)}:{node.lineno}: forbidden import from {node.module}"
                )
        elif isinstance(node, ast.Call) and node.args:
            function_name: str | None = None
            if isinstance(node.func, ast.Name):
                function_name = node.func.id
            elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                function_name = f"{node.func.value.id}.{node.func.attr}"

            if function_name in {"__import__", "importlib.import_module"}:
                module_name = _constant_string(node.args[0])
                if module_name and _is_forbidden_module(module_name):
                    findings.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: "
                        f"forbidden dynamic import {module_name}"
                    )

    return findings


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

    if missing or findings:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "missing_clean_package_directories": missing,
                    "forbidden_findings": findings,
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
                "forbidden_import_root": FORBIDDEN_ROOT,
                "clean_package_directories": [str(path.relative_to(ROOT)) for path in CLEAN_ROOTS],
                "scanned_python_files": scanned_files,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
