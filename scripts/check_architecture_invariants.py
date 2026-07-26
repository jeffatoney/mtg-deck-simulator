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
        relative == candidate.rstrip("/") or relative.startswith(candidate.rstrip("/") + "/")
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


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    """Return lexical import aliases suitable for resolving security-sensitive calls."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".", maxsplit=1)[0]] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.name != "*":
                    aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return aliases


def _resolved_dotted(node: ast.AST | None, aliases: dict[str, str]) -> str:
    dotted = _dotted(node)
    if not dotted:
        return ""
    head, separator, tail = dotted.partition(".")
    resolved = aliases.get(head, head)
    return f"{resolved}.{tail}" if separator else resolved


def _lexical_aliases(tree: ast.AST) -> dict[str, str]:
    """Resolve imports and simple, transitive assignment aliases fail-closed scanners use."""
    aliases = _import_aliases(tree)
    assignments: list[tuple[str, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if value is not None:
                assignments.extend(
                    (target.id, value) for target in targets if isinstance(target, ast.Name)
                )
    for _ in range(len(assignments) + 1):
        changed = False
        for target, value in assignments:
            resolved = _resolved_dotted(value, aliases)
            referenced = {_resolved_dotted(item, aliases) for item in ast.walk(value)}
            if any(
                item
                in {"exec", "eval", "compile", "builtins.exec", "builtins.eval", "builtins.compile"}
                for item in referenced
            ):
                resolved = "__dynamic_code_unresolved__"
            elif any(
                item.startswith(("unittest.mock.patch", "mock.patch", "mocker.patch"))
                or item == "monkeypatch"
                for item in referenced
            ):
                resolved = "__patch_unresolved__"
            if resolved and aliases.get(target) != resolved:
                aliases[target] = resolved
                changed = True
        if not changed:
            break
    return aliases


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
        self.zone_container_names = set(
            config.get("protected_zone_container_attributes", ["zones", "_zones"])
        )
        self.state_reference_names = set(
            config.get("state_reference_names", ["state", "game_state"])
        )
        self.import_aliases: dict[str, str] = {}
        self.function_stack: list[ast.FunctionDef | ast.AsyncFunctionDef] = []

    def scan(self, tree: ast.AST) -> None:
        self.import_aliases = _lexical_aliases(tree)
        self.visit(tree)

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

    def _zone_initialization_allowed(self) -> bool:
        functions = self.config.get("allowed_zone_initializers", {}).get(self.relative, [])
        return bool(self.function_stack and self.function_stack[-1].name in functions)

    def _is_state_reference(self, node: ast.AST | None) -> bool:
        dotted = _resolved_dotted(node, self.import_aliases)
        if not dotted:
            return False
        parts = dotted.split(".")
        return (
            dotted in self.state_reference_names
            or (len(parts) >= 2 and parts[-1] in self.state_reference_names)
            or (
                dotted == "self"
                and self.relative in self.config.get("allowed_zone_initializers", {})
            )
        )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_stack.append(node)
        self.generic_visit(node)
        self.function_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def _has_prior_real_trigger_push(self, event_node: ast.Call) -> bool:
        if not self.function_stack:
            return False
        function = self.function_stack[-1]
        trigger_names = {
            target.id
            for item in ast.walk(function)
            if isinstance(item, (ast.Assign, ast.AnnAssign))
            for target in (item.targets if isinstance(item, ast.Assign) else [item.target])
            if isinstance(target, ast.Name)
            and item.value is not None
            and _resolved_dotted(item.value, self.import_aliases).endswith("TriggeredAbilityObject")
            and getattr(item, "lineno", 0) < event_node.lineno
        }
        for item in ast.walk(function):
            if not isinstance(item, ast.Call) or getattr(item, "lineno", 0) >= event_node.lineno:
                continue
            if (
                not isinstance(item.func, ast.Attribute)
                or item.func.attr != "append"
                or not item.args
            ):
                continue
            receiver = item.func.value
            if not (
                isinstance(receiver, ast.Attribute)
                and receiver.attr == "stack"
                and self._is_state_reference(receiver.value)
            ):
                continue
            pushed = item.args[0]
            if _resolved_dotted(pushed, self.import_aliases).endswith("TriggeredAbilityObject"):
                return True
            if isinstance(pushed, ast.Name) and pushed.id in trigger_names:
                return True
        return False

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
        state_attribute = self._is_state_reference(node.value)
        if (
            state_attribute
            and node.attr in self.zone_container_names
            and not self._zone_allowed()
            and not self._zone_initialization_allowed()
        ):
            self.add(
                node,
                "ZONE_CONTAINER_ACCESS",
                "Only narrow GameState initialization and ZoneService may access zone containers.",
                ast.unparse(node),
            )
        elif state_attribute and node.attr in self.zone_names and not self._zone_allowed():
            self.add(
                node,
                "ZONE_ACCESS",
                "Only GameState initialization and ZoneService may access mutable zones.",
                ast.unparse(node),
            )
        elif state_attribute and node.attr == "stack" and not self._stack_allowed():
            self.add(
                node,
                "STACK_ACCESS",
                "Only GameState initialization and StackService may access the mutable stack.",
                ast.unparse(node),
            )
        elif isinstance(node.ctx, (ast.Store, ast.Del)):
            if (
                state_attribute
                and node.attr in self.phase_names
                and not self._phase_write_allowed()
            ):
                self.add(
                    node,
                    "PHASE_ASSIGNMENT",
                    "Only GameState initialization and TurnEngine may change phase or step.",
                    ast.unparse(node),
                )
            elif (
                state_attribute
                and node.attr in self.terminal_names
                and not self._terminal_write_allowed()
            ):
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
        name = _resolved_dotted(node.func, self.import_aliases)
        leaf = name.rsplit(".", maxsplit=1)[-1]

        dynamic_modules = set(self.config.get("forbidden_dynamic_import_modules", []))
        dynamic_importers: set[str] = set()
        if "importlib" in dynamic_modules:
            dynamic_importers.add("importlib.import_module")
        if "builtins" in dynamic_modules:
            dynamic_importers.update({"builtins.__import__", "__import__"})
        if name in dynamic_importers:
            module = _literal_string(node.args[0]) if node.args else None
            forbidden = module is None or any(
                module == prefix or module.startswith(prefix + ".")
                for prefix in self.config["forbidden_import_prefixes"]
            )
            if forbidden:
                self.add(
                    node,
                    "LEGACY_DYNAMIC_IMPORT",
                    "Dynamic imports must be literal and may not reach the legacy simulator.",
                    ast.unparse(node),
                )

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

        if leaf == "record_event":
            event_node = node.args[0] if node.args else None
            for keyword in node.keywords:
                if keyword.arg in {"event_type", "event", "name"}:
                    event_node = keyword.value
                    break
            event = _literal_string(event_node)
            allowed_file = _matches_path(
                self.relative, self.config["allowed_trigger_stack_event_files"]
            )
            if (
                event_node is not None
                and (event is None or event == "trigger_put_on_stack")
                and (not allowed_file or not self._has_prior_real_trigger_push(node))
            ):
                self.add(
                    node,
                    "FAKE_TRIGGER_EVENT",
                    "Only StackService may emit this event after adding a real trigger object.",
                    ast.unparse(node),
                )

        if name in {
            "exec",
            "eval",
            "compile",
            "builtins.exec",
            "builtins.eval",
            "builtins.compile",
            "__dynamic_code_unresolved__",
        }:
            self.add(
                node,
                "DYNAMIC_CODE_EXECUTION",
                "Dynamic code execution is prohibited in clean-kernel and gate paths.",
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


def _scan_test_invariants(
    path: Path, root: Path, forbidden_patch_tokens: Iterable[str]
) -> list[Violation]:
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
    aliases = _lexical_aliases(tree)
    patch_tokens = tuple(token.lower() for token in forbidden_patch_tokens)

    def protected_dotted_string(node: ast.AST | None) -> str | None:
        value = _literal_string(node)
        if value is None or "." not in value:
            return None
        lowered = value.lower()
        return value if any(token in lowered for token in patch_tokens) else None

    def protected_imported_object(node: ast.AST | None) -> bool:
        """Recognize a protected object only when lexical imports/aliases root it."""
        if not isinstance(node, (ast.Name, ast.Attribute)):
            return False
        original = _dotted(node)
        head = original.partition(".")[0]
        resolved = _resolved_dotted(node, aliases)
        if head not in aliases or resolved == original:
            return False
        lowered = resolved.lower()
        return any(token in lowered.split(".") for token in patch_tokens) or any(
            token == "mtg_kernel" and lowered.startswith("mtg_kernel.") for token in patch_tokens
        )

    def module_name_from_subscript(node: ast.AST | None) -> str | None:
        if not isinstance(node, ast.Subscript):
            return None
        if _resolved_dotted(node.value, aliases) != "sys.modules":
            return None
        return _literal_string(node.slice)

    def forbidden_module_name(value: str | None) -> bool:
        return (
            value is None
            or value == "mtg_sim"
            or value.startswith("mtg_sim.")
            or (value == "mtg_kernel" or value.startswith("mtg_kernel."))
        )

    def record(node: ast.AST, code: str, reason: str, detail: str | None = None) -> None:
        rendered = detail or ast.unparse(node)
        line = getattr(node, "lineno", 1)
        violations[(line, f"{code}:{rendered}")] = Violation(
            path=_relative(path, root),
            line=line,
            code=code,
            reason=reason,
            detail=rendered,
        )

    for node in ast.walk(tree):
        assignment_targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            assignment_targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            assignment_targets = [node.target]
        elif isinstance(node, ast.AugAssign):
            assignment_targets = [node.target]
        elif isinstance(node, ast.Delete):
            assignment_targets = list(node.targets)
        for target in assignment_targets:
            if isinstance(target, ast.Attribute) and protected_imported_object(target.value):
                record(
                    node,
                    "FORBIDDEN_TEST_REPLACEMENT",
                    "Acceptance tests may not replace members of imported kernel components.",
                )
            module_name = module_name_from_subscript(target)
            if module_name is not None and forbidden_module_name(module_name):
                record(
                    node,
                    "FORBIDDEN_MODULE_REPLACEMENT",
                    "Acceptance tests may not replace or delete protected sys.modules entries.",
                )

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
            if not isinstance(node, ast.Call):
                continue
        else:
            line = getattr(node, "lineno", 1)
            violations[(line, detail)] = Violation(
                path=_relative(path, root),
                line=line,
                code="SKIPPED_TEST",
                reason="Phase A gate and acceptance tests may not be skipped or xfailed.",
                detail=detail,
            )

        if not isinstance(node, ast.Call):
            continue
        call_name = _resolved_dotted(node.func, aliases)
        if call_name in {
            "exec",
            "eval",
            "compile",
            "builtins.exec",
            "builtins.eval",
            "builtins.compile",
            "__dynamic_code_unresolved__",
        }:
            dynamic_detail = ast.unparse(node)
            line = getattr(node, "lineno", 1)
            violations[(line, dynamic_detail)] = Violation(
                path=_relative(path, root),
                line=line,
                code="DYNAMIC_CODE_EXECUTION",
                reason="Dynamic code execution is prohibited in clean-kernel and gate paths.",
                detail=dynamic_detail,
            )
        target: ast.AST | None = next(
            (keyword.value for keyword in node.keywords if keyword.arg == "target"), None
        )
        is_patch = False
        if call_name in {"monkeypatch.setattr", "monkeypatch.delattr"}:
            is_patch = True
            target = node.args[0] if node.args else target
        elif call_name in {
            "unittest.mock.patch",
            "unittest.mock.patch.object",
            "unittest.mock.patch.dict",
            "unittest.mock.patch.multiple",
        }:
            is_patch = True
            target = node.args[0] if node.args else target
        elif call_name in {
            "mocker.patch",
            "mocker.patch.object",
            "mocker.patch.dict",
            "mocker.patch.multiple",
        }:
            is_patch = True
            target = node.args[0] if node.args else target
        elif call_name == "__patch_unresolved__" or call_name.startswith("__patch_unresolved__."):
            is_patch = True
            target = node.args[0] if node.args else target

        if call_name in {"sys.modules.update", "sys.modules.setdefault"}:
            module_names: list[str | None] = []
            if node.args:
                first = node.args[0]
                if isinstance(first, ast.Dict):
                    module_names.extend(_literal_string(key) for key in first.keys)
                else:
                    module_names.append(_literal_string(first))
            module_names.extend(keyword.arg for keyword in node.keywords)
            if any(forbidden_module_name(module_name) for module_name in module_names):
                record(
                    node,
                    "FORBIDDEN_MODULE_REPLACEMENT",
                    "Acceptance tests may not inject protected sys.modules entries.",
                )

        protected_arguments = [
            value
            for argument in node.args
            if (value := protected_dotted_string(argument)) is not None
        ]
        protected_arguments.extend(
            value
            for keyword in node.keywords
            if (value := protected_dotted_string(keyword.value)) is not None
        )
        if protected_arguments and not is_patch:
            record(
                node,
                "UNRESOLVED_PROTECTED_TARGET",
                "A protected dotted target may not be passed to an unresolved callable.",
            )

        if not is_patch:
            continue

        literal_target = _literal_string(target)
        target_name = (
            literal_target if literal_target is not None else _resolved_dotted(target, aliases)
        )
        # A dotted object is statically inspectable for object-form patching. Every
        # other non-literal expression fails closed in acceptance tests.
        unsafe = (
            any(token in target_name.lower() for token in patch_tokens) if target_name else True
        )
        if literal_target is None and "." not in target_name:
            unsafe = True
        if unsafe:
            patch_detail = ast.unparse(node)
            line = getattr(node, "lineno", 1)
            violations[(line, patch_detail)] = Violation(
                path=_relative(path, root),
                line=line,
                code="FORBIDDEN_TEST_PATCH",
                reason="Acceptance tests may not patch kernel components or dynamic targets.",
                detail=patch_detail,
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
        scanner.scan(tree)
        violations.extend(scanner.violations)

    if config.get("forbid_skipped_or_xfailed_tests", True):
        for path in _python_files(root, config.get("test_paths", [])):
            violations.extend(
                _scan_test_invariants(
                    path,
                    root,
                    config.get("forbidden_patch_target_tokens", []),
                )
            )

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
