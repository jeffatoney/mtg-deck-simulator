#!/usr/bin/env python3
"""Fail-closed architecture gate for the clean rules-kernel implementation.

The current legacy simulator is intentionally outside this gate during Phase A.
Only the new ``mtg_kernel`` and structured ``mtg_cards`` packages are scanned.
Phase B expands the gate when the new kernel becomes the canonical simulator.

Usage:
    uv run python scripts/check_architecture_invariants.py
    uv run python scripts/check_architecture_invariants.py --root /tmp/fixture
    uv run python scripts/check_architecture_invariants.py --report result.json
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
    for candidate in candidates:
        normalized = candidate.rstrip("/")
        if relative == normalized or relative.startswith(normalized + "/"):
            return True
    return False


def _attribute_names(node: ast.AST | None) -> tuple[str, ...]:
    """Return attribute/name tokens in source order, ignoring subscripts/calls."""

    if node is None:
        return ()
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, ast.Attribute):
        return (*_attribute_names(node.value), node.attr)
    if isinstance(node, ast.Subscript):
        return _attribute_names(node.value)
    if isinstance(node, ast.Call):
        return _attribute_names(node.func)
    return ()


def _contains_attribute(node: ast.AST, names: set[str]) -> bool:
    return any(token in names for token in _attribute_names(node))


def _iter_targets(node: ast.AST) -> Iterable[ast.AST]:
    if isinstance(node, (ast.Tuple, ast.List)):
        for item in node.elts:
            yield from _iter_targets(item)
    else:
        yield node


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


class ArchitectureScanner(ast.NodeVisitor):
    def __init__(self, *, path: Path, root: Path, config: dict[str, Any]) -> None:
        self.path = path
        self.root = root
        self.relative = _relative(path, root)
        self.config = config
        self.violations: list[Violation] = []
        self.zone_names = set(config["zone_attributes"])
        self.zone_mutators = set(config["zone_mutator_methods"])
        self.stack_mutators = set(config["stack_mutator_methods"])
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

    def _zone_mutation_allowed(self) -> bool:
        return _matches_path(self.relative, self.config["allowed_zone_mutation_files"])

    def _stack_mutation_allowed(self) -> bool:
        return _matches_path(self.relative, self.config["allowed_stack_mutation_files"])

    def _phase_assignment_allowed(self) -> bool:
        return _matches_path(self.relative, self.config["allowed_phase_assignment_files"])

    def _terminal_assignment_allowed(self) -> bool:
        return _matches_path(self.relative, self.config["allowed_terminal_assignment_files"])

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_forbidden_import(node, alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self._check_forbidden_import(node, node.module)
        self.generic_visit(node)

    def _check_forbidden_import(self, node: ast.AST, module: str) -> None:
        for prefix in self.config["forbidden_import_prefixes"]:
            if module == prefix or module.startswith(prefix + "."):
                self.add(
                    node,
                    "LEGACY_IMPORT",
                    "The clean kernel may not depend on the legacy engine or pilot.",
                    module,
                )

    def visit_Call(self, node: ast.Call) -> None:
        chain = _attribute_names(node.func)
        method = chain[-1] if chain else ""
        receiver = node.func.value if isinstance(node.func, ast.Attribute) else None

        if method in self.zone_mutators and receiver is not None and _contains_attribute(
            receiver, self.zone_names
        ):
            if not self._zone_mutation_allowed():
                self.add(
                    node,
                    "ZONE_MUTATION",
                    "Only state initialization and ZoneService may mutate game zones.",
                    ".".join(chain),
                )

        if method in self.stack_mutators and receiver is not None and _contains_attribute(
            receiver, {"stack"}
        ):
            if not self._stack_mutation_allowed():
                self.add(
                    node,
                    "STACK_MUTATION",
                    "Only the stack service may mutate the stack.",
                    ".".join(chain),
                )

        if method == "insert" and receiver is not None and _contains_attribute(
            receiver, {"library"}
        ):
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Attribute):
                if node.args[1].attr == "name":
                    self.add(
                        node,
                        "NAME_IN_LIBRARY",
                        "Libraries store CardInstance IDs, never display-name strings.",
                        ast.unparse(node),
                    )

        if isinstance(node.func, ast.Name) and node.func.id == "setattr" and node.args:
            target = ast.unparse(node.args[0]).lower()
            if any(token in target for token in self.config["forbidden_patch_target_tokens"]):
                self.add(
                    node,
                    "IMPORT_TIME_PATCH",
                    "Replacing engine functions with setattr is prohibited.",
                    ast.unparse(node),
                )

        if method == "record_event" and node.args:
            event_name = _literal_string(node.args[0])
            if event_name == "trigger_put_on_stack" and not _matches_path(
                self.relative, self.config["allowed_trigger_stack_event_files"]
            ):
                self.add(
                    node,
                    "FAKE_TRIGGER_EVENT",
                    (
                        "Only the stack service may emit trigger_put_on_stack "
                        "after placing a real object."
                    ),
                    ast.unparse(node),
                )

        self.generic_visit(node)

    def _check_assignment_target(self, node: ast.AST, target: ast.AST) -> None:
        for item in _iter_targets(target):
            names = _attribute_names(item)
            name_set = set(names)
            if name_set.intersection(self.zone_names) and not self._zone_mutation_allowed():
                self.add(
                    node,
                    "ZONE_ASSIGNMENT",
                    "Only state initialization and ZoneService may assign game zones.",
                    ast.unparse(item),
                )
            if "stack" in name_set and not self._stack_mutation_allowed():
                self.add(
                    node,
                    "STACK_ASSIGNMENT",
                    "Only state initialization and the stack service may assign the stack.",
                    ast.unparse(item),
                )
            if name_set.intersection(self.phase_names) and not self._phase_assignment_allowed():
                self.add(
                    node,
                    "PHASE_ASSIGNMENT",
                    "Only TurnEngine may change phase or step.",
                    ast.unparse(item),
                )
            if (
                name_set.intersection(self.terminal_names)
                and not self._terminal_assignment_allowed()
            ):
                self.add(
                    node,
                    "TERMINAL_ASSIGNMENT",
                    "Only the state-based-action service may set terminal results.",
                    ast.unparse(item),
                )

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._check_assignment_target(node, target)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._check_assignment_target(node, node.target)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._check_assignment_target(node, node.target)
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            self._check_assignment_target(node, target)
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if not _matches_path(self.relative, self.config["kernel_paths"]):
            return
        if isinstance(node.value, str) and node.value in set(
            self.config["prohibited_kernel_card_names"]
        ):
            self.add(
                node,
                "CARD_NAME_IN_KERNEL",
                "The rules kernel must be card-agnostic; card names belong in structured specs.",
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
                path
                for path in candidate.rglob("*.py")
                if "__pycache__" not in path.parts
            )
    return sorted(files)


def _scan_skips(path: Path, root: Path) -> list[Violation]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [
            Violation(
                path=_relative(path, root),
                line=exc.lineno or 1,
                code="SYNTAX_ERROR",
                reason="Tests must parse before skip/xfail validation.",
                detail=str(exc),
            )
        ]
    violations: dict[tuple[int, str], Violation] = {}
    prohibited = {
        "pytest.skip",
        "pytest.xfail",
        "pytest.mark.skip",
        "pytest.mark.skipif",
        "pytest.mark.xfail",
    }
    for node in ast.walk(tree):
        target: ast.AST | None = None
        if isinstance(node, ast.Call):
            target = node.func
        elif isinstance(node, ast.Attribute):
            target = node
        if target is None:
            continue
        dotted = ".".join(_attribute_names(target))
        if dotted not in prohibited:
            continue
        line = getattr(node, "lineno", 1)
        violations[(line, dotted)] = Violation(
            path=_relative(path, root),
            line=line,
            code="SKIPPED_TEST",
            reason="Phase A acceptance and gate tests may not be skipped or xfailed.",
            detail=dotted,
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
            violations.extend(_scan_skips(path, root))

    unique = {
        (item.path, item.line, item.code, item.detail): item for item in violations
    }
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
            "Architecture invariants: PASS "
            f"({result['source_files_scanned']} source files scanned)"
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
