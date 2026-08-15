#!/usr/bin/env python3
"""Enforce the public-policy information boundary for broker actions."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (ROOT / "src/mtg_policy", ROOT / "src/mtg_runs")
BROKER_IMPLEMENTATIONS = {
    "src/mtg_policy/broker.py",
    "src/mtg_policy/broker_core.py",
}
HANDLE_ADAPTER = (
    "src/mtg_policy/public_actions.py",
    "resolve_selected_action_handle",
)


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _imports_observed_action(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(
            alias.name == "ObservedAction" for alias in node.names
        ):
            return True
    return False


def _containing_function(tree: ast.AST, target: ast.AST) -> str | None:
    result: str | None = None

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            nonlocal result
            self.stack.append(node.name)
            if target in ast.walk(node):
                result = self.stack[-1]
            self.generic_visit(node)
            self.stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

    Visitor().visit(tree)
    return result


def find_policy_boundary_violations(path: Path, source: str) -> list[str]:
    """Return structural information-boundary violations for one Python module."""

    relative = _relative(path) if path.is_absolute() else path.as_posix()
    try:
        tree = ast.parse(source, filename=relative)
    except SyntaxError as exc:
        return [f"{relative}:{exc.lineno}: syntax error prevents boundary analysis"]

    violations: list[str] = []
    observed_action_module = _imports_observed_action(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "_InternalAction":
            if relative not in BROKER_IMPLEMENTATIONS:
                violations.append(
                    f"{relative}:{node.lineno}: private broker type _InternalAction escaped broker modules"
                )
        if isinstance(node, ast.Attribute) and node.attr == "_actions":
            if relative not in BROKER_IMPLEMENTATIONS:
                violations.append(
                    f"{relative}:{node.lineno}: private ActionBroker._actions escaped broker modules"
                )
        if isinstance(node, ast.Attribute) and node.attr == "handle" and observed_action_module:
            containing = _containing_function(tree, node)
            allowed = (relative, containing) == HANDLE_ADAPTER or relative in BROKER_IMPLEMENTATIONS
            if not allowed:
                violations.append(
                    f"{relative}:{node.lineno}: ObservedAction capability handle used outside post-selection adapter"
                )
    return violations


def main() -> int:
    violations: list[str] = []
    for root in SOURCE_ROOTS:
        for path in sorted(root.rglob("*.py")):
            violations.extend(
                find_policy_boundary_violations(path, path.read_text(encoding="utf-8"))
            )

    standard = ROOT / "src/mtg_policy/standard.py"
    standard_source = standard.read_text(encoding="utf-8")
    required_markers = (
        "PolicyActionView",
        "PublicActionKey",
        "public_action_classes",
        "select_public_action_key",
        "resolve_selected_action_handle",
    )
    for marker in required_markers:
        if marker not in standard_source:
            violations.append(f"src/mtg_policy/standard.py: missing positive-boundary marker {marker}")

    public_actions = ROOT / "src/mtg_policy/public_actions.py"
    if not public_actions.is_file():
        violations.append("src/mtg_policy/public_actions.py: handle-free policy boundary is missing")

    if violations:
        print("Policy information-boundary check failed:")
        for violation in sorted(set(violations)):
            print(f"- {violation}")
        return 1
    print(
        "PASS: policy ranking consumes handle-free public action views; "
        "opaque action handles are confined to broker execution and the post-selection adapter"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
