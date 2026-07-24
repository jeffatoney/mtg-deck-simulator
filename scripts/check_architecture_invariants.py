#!/usr/bin/env python3
"""Fail-closed architecture gate for the clean Phase A rules kernel.

The legacy ``mtg_sim`` package remains outside this gate during Phase A. The
new ``mtg_kernel`` and ``mtg_cards`` packages must communicate through explicit
services rather than touching mutable game containers directly.
"""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class Violation:
    path: str
    line: int
    code: str
    reason: str
    detail: str


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _matches_path(relative: str, candidates: Iterable[str]) -> bool:
    return any(
        relative == candidate.rstrip("/")
        or relative.startswith(candidate.rstrip("/") + "/")
        for candidate in candidates
    )


def _dotted(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    return ""


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


class ArchitectureScanner(ast.NodeVisitor):
    """Apply deliberately strict, service-boundary checks.

    Mutable zones and the stack may not even be read directly outside their
    owning services. This is stronger than following aliases after the fact:
    ``cards = state.hand`` is itself rejected, so ``cards.append(...)`` cannot
    bypass the service boundary.
    """

    def __init__(self, *, path: Path, root: Path, config: dict[str, Any]) -> None:
        self.relative = _relative(path, root)
        self.config = config
        self.violations: list[Violation] = []
        self.zone_names = set(config["zone_attributes"])
        self.phase_names = set(config["phase_attributes"])
        self.terminal_names = set(config["terminal_attributes"])

    def add(self, node: ast.AST, code: str, reason: str, detail: str) -> None:
        self.violations.append(
            Violation(
                path=self.relative,
                line=getattr(node, "lineno", 1),
                code=code,
                reason=reason,
                detail=detail,
            )
        )

    def _zone_allowed(self) -> bool:
        return _matches_path(self.relative, self.config["allowed_zone_mutation_files"])

    def _stack_allowed(self) -> bool:
        return _matches_path(self.relative, self.config["allowed_stack_mutation_files"])

    def _phase_write_allowed(self) -> bool:
        return _matches_path(self.relative, self.config["allowed_phase_assignment_files"])

    def _terminal_write_allowed(self) -> bool:
        return _matches_path(self.relative, self.config["allowed_terminal_assignment_files"])

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_import(node, alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        base = f"{'.' * node.level}{node.module or ''}".lstrip(".")
        if base:
            self._check_import(node, base)
        for alias in node.names:
            if alias.name == "*":
                continue
            candidate = f"{base}.{alias.name}" if base else alias.name
            self._check_import(node, candidate)
        self.generic_visit(node)

    def _check_import(self, node: ast.AST, module: str) -> None:
        for prefix in self.config["forbidden_import_prefixes"]:
            if module == prefix or module.startswith(prefix + "."):
                self.add(
                    node,
                    "LEGACY_IMPORT",
                    "The clean kernel may not import the legacy simulator.",
                    module,
                )

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in self.zone_names and not self._zone_allowed():
            self.add(
                node,
                "ZONE_ACCESS",
                "Only GameState initialization and ZoneService may access mutable zones.",
                ast.unparse(node),
            )
        elif node.attr == "stack" and not self._stack_allowed():
            self.add(
                node,
                "STACK_ACCESS",
                "Only GameState initialization and StackService may access the mutable stack.",
                ast.unparse(node),
            )
        elif isinstance(node.ctx, (ast.Store, ast.Del)):
            if node.attr in self.phase_names and not self._phase_write_allowed():
                self.add(
                    node,
                    "PHASE_ASSIGNMENT",
                    "Only GameState initialization and TurnEngine may change phase or step.",
                    ast.unparse(node),
                )
            elif node.attr in self.terminal_names and not self._terminal_write_allowed():
                self.add(
                    node,
                    "TERMINAL_ASSIGNMENT",
                    "Only GameState initialization and state-based actions may set results.",
                    ast.unparse(node),
                )
        if node.attr == "__dict__":
            self.add(
                node,
                "STATE_REFLECTION",
                "Direct __dict__ access is prohibited in the clean kernel.",
                ast.unparse(node),
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _dotted(node.func)
        leaf = name.rsplit(".", maxsplit=1)[-1]

        if leaf in {"setattr", "__setattr__", "delattr", "__delattr__"}:
            self.add(
                node,
                "REFLECTIVE_MUTATION",
                "Reflective mutation is prohibited; use the owning service.",
                ast.unparse(node),
            )

        if leaf in {"getattr", "hasattr"}:
            attribute_node = node.args[1] if len(node.args) >= 2 else None
            attribute = _literal_string(attribute_node)
            if attribute is None:
                self.add(
                    node,
                    "DYNAMIC_REFLECTION",
                    "Dynamic attribute access is prohibited in the clean kernel.",
                    ast.unparse(node),
                )
            elif attribute in self.zone_names and not self._zone_allowed():
                self.add(
                    node,
                    "ZONE_ACCESS",
                    "Only GameState initialization and ZoneService may access mutable zones.",
                    ast.unparse(node),
                )
            elif attribute == "stack" and not self._stack_allowed():
                self.add(
                    node,
                    "STACK_ACCESS",
                    "Only GameState initialization and StackService may access the mutable stack.",
                    ast.unparse(node),
                )

        if leaf in {"vars", "dir"}:
            self.add(
                node,
                "STATE_REFLECTION",
                "Reflective state inspection is prohibited in the clean kernel.",
                ast.unparse(node),
            )

        if leaf == "record_event" and node.args:
            event = _literal_string(node.args[0])
            if event == "trigger_put_on_stack" and not _matches_path(
                self.relative, self.config["allowed_trigger_stack_event_files"]
            ):
                self.add(
                    node,
                    "FAKE_TRIGGER_EVENT",
                    "Only StackService may emit this event after adding a real trigger object.",
                    ast.unparse(node),
                )

        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if _matches_path(self.relative, self.config["kernel_paths"]):
            if isinstance(node.value, str) and node.value in set(
                self.config["prohibited_kernel_card_names"]
            ):
                self.add(
                    node,
                    "CARD_NAME_IN_KERNEL",
                    "The rules kernel must be card-agnostic.",
                    node.value,
                )


def _python_files(root: Path, paths: Iterable[str]) -> list[Path]:
    files: set[Path] = set()
    for entry in paths:
        candidate = root / entry
        if candidate.is_file() and candidate.suffix == ".py":
            files.add(candidate)
        elif candidate.is_dir():
            files.update(
                path for path in candidate.rglob("*.py") if "__pycache__" not in path.parts
            )
    return sorted(files)


def _scan_test_suppression(path: Path, root: Path) -> list[Violation]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [
            Violation(
                path=_relative(path, root),
                line=exc.lineno or 1,
                code="SYNTAX_ERROR",
                reason="Tests must parse before suppression validation.",
                detail=str(exc),
            )
        ]

    forbidden_tokens = {
        "skip",
        "skipif",
        "skipunless",
        "xfail",
        "importorskip",
        "expectedfailure",
        "skiptest",
    }
    violations: dict[tuple[int, str], Violation] = {}

    for node in ast.walk(tree):
        detail: str | None = None
        if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
            if (node.module or "").lstrip(".") in {"pytest", "unittest"}:
                detail = ast.unparse(node)
        elif isinstance(node, ast.Attribute) and node.attr.lower() in forbidden_tokens:
            detail = ast.unparse(node)
        elif isinstance(node, ast.Name) and node.id.lower() in forbidden_tokens:
            detail = node.id
        elif isinstance(node, ast.alias) and node.name.lower() in forbidden_tokens:
            detail = node.name
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.lower() in forbidden_tokens:
                detail = node.value
        elif isinstance(node, ast.Call) and _dotted(node.func).endswith("getattr"):
            detail = ast.unparse(node)

        if detail is None:
            continue
        line = getattr(node, "lineno", 1)
        violations[(line, detail)] = Violation(
            path=_relative(path, root),
            line=line,
            code="SKIPPED_TEST",
            reason="Phase A gate and acceptance tests may not be skipped or xfailed.",
            detail=detail,
        )
    return list(violations.values())


def run_gate(root: Path, config_path: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    exempt = set(config.get("exempt_files", []))
    violations: list[Violation] = []

    for required in config.get("required_paths", []):
        if not (root / required).exists():
            violations.append(
                Violation(
                    path=required,
                    line=1,
                    code="MISSING_REQUIRED_PATH",
                    reason="A required Phase A architecture file is missing.",
                    detail=required,
                )
            )

    source_files = _python_files(root, config.get("enforced_paths", []))
    for path in source_files:
        relative = _relative(path, root)
        if relative in exempt:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            violations.append(
                Violation(
                    path=relative,
                    line=exc.lineno or 1,
                    code="SYNTAX_ERROR",
                    reason="Source file does not parse.",
                    detail=str(exc),
                )
            )
            continue
        scanner = ArchitectureScanner(path=path, root=root, config=config)
        scanner.visit(tree)
        violations.extend(scanner.violations)

    if config.get("forbid_skipped_or_xfailed_tests", True):
        for path in _python_files(root, config.get("test_paths", [])):
            violations.extend(_scan_test_suppression(path, root))

    unique = {(item.path, item.line, item.code, item.detail): item for item in violations}
    ordered = sorted(unique.values(), key=lambda item: (item.path, item.line, item.code))
    return {
        "status": "PASS" if not ordered else "FAIL",
        "source_files_scanned": len(source_files),
        "violation_count": len(ordered),
        "violations": [asdict(item) for item in ordered],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("automation/architecture-invariants.json"),
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    config_path = args.config if args.config.is_absolute() else root / args.config
    result = run_gate(root, config_path)

    if args.report:
        report_path = args.report if args.report.is_absolute() else root / args.report
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    if result["status"] == "PASS":
        print(
            f"Architecture invariants: PASS ({result['source_files_scanned']} source files scanned)"
        )
        return 0

    print(f"Architecture invariants: FAIL — {result['violation_count']} violation(s)")
    for violation in result["violations"]:
        print(f"- {violation['path']}:{violation['line']} [{violation['code']}]")
        print(f"  {violation['reason']}")
        print(f"  {violation['detail']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
