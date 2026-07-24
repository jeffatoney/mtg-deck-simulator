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
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class Violation:
    path: str
    line: int
    code: str
    reason: str
    detail: str


@dataclass(slots=True)
class ScopeInfo:
    """Lexical-scope facts used for conservative alias tracking."""

    parent: int | None
    local_names: set[str] = field(default_factory=set)
    assignments: list[tuple[ast.AST, ast.AST]] = field(default_factory=list)


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _matches_path(relative: str, candidates: Iterable[str]) -> bool:
    for candidate in candidates:
        normalized = candidate.rstrip("/")
        if relative == normalized or relative.startswith(normalized + "/"):
            return True
    return False


def _attribute_names(node: ast.AST | None) -> tuple[str, ...]:
    """Return dotted name tokens in source order."""

    if node is None:
        return ()
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, ast.Attribute):
        return (*_attribute_names(node.value), node.attr)
    if isinstance(node, ast.Call):
        return _attribute_names(node.func)
    return ()


def _dotted(node: ast.AST | None) -> str:
    return ".".join(_attribute_names(node))


def _iter_targets(node: ast.AST) -> Iterable[ast.AST]:
    if isinstance(node, (ast.Tuple, ast.List)):
        for item in node.elts:
            yield from _iter_targets(item)
    elif isinstance(node, ast.Starred):
        yield from _iter_targets(node.value)
    else:
        yield node


def _target_keys(node: ast.AST) -> tuple[str, ...]:
    keys: list[str] = []
    for target in _iter_targets(node):
        if isinstance(target, (ast.Name, ast.Attribute)):
            dotted = _dotted(target)
            if dotted:
                keys.append(dotted)
    return tuple(keys)


def _local_target_names(node: ast.AST) -> set[str]:
    return {target.id for target in _iter_targets(node) if isinstance(target, ast.Name)}


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


class ScopeCollector(ast.NodeVisitor):
    """Collect lexical scopes and assignments without losing branch aliases."""

    def __init__(self) -> None:
        self.scopes: dict[int, ScopeInfo] = {0: ScopeInfo(parent=None)}
        self.node_scope: dict[int, int] = {}
        self.current_scope = 0
        self.next_scope = 1

    def visit(self, node: ast.AST) -> Any:
        self.node_scope[id(node)] = self.current_scope
        return super().visit(node)

    def _bind_local(self, name: str) -> None:
        self.scopes[self.current_scope].local_names.add(name)

    def _record_assignment(self, target: ast.AST, value: ast.AST) -> None:
        self.scopes[self.current_scope].assignments.append((target, value))
        self.scopes[self.current_scope].local_names.update(_local_target_names(target))

    def _visit_function_common(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        self._bind_local(node.name)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if default is not None:
                self.visit(default)
        if node.returns is not None:
            self.visit(node.returns)

        parent = self.current_scope
        child = self.next_scope
        self.next_scope += 1
        self.scopes[child] = ScopeInfo(parent=parent)
        self.current_scope = child
        argument_names = {
            argument.arg
            for argument in (
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            )
        }
        if node.args.vararg is not None:
            argument_names.add(node.args.vararg.arg)
        if node.args.kwarg is not None:
            argument_names.add(node.args.kwarg.arg)
        self.scopes[child].local_names.update(argument_names)
        for statement in node.body:
            self.visit(statement)
        self.current_scope = parent

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function_common(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function_common(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if default is not None:
                self.visit(default)
        parent = self.current_scope
        child = self.next_scope
        self.next_scope += 1
        self.scopes[child] = ScopeInfo(parent=parent)
        self.current_scope = child
        argument_names = {
            argument.arg
            for argument in (
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            )
        }
        if node.args.vararg is not None:
            argument_names.add(node.args.vararg.arg)
        if node.args.kwarg is not None:
            argument_names.add(node.args.kwarg.arg)
        self.scopes[child].local_names.update(argument_names)
        self.visit(node.body)
        self.current_scope = parent

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._bind_local(node.name)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)
        parent = self.current_scope
        child = self.next_scope
        self.next_scope += 1
        self.scopes[child] = ScopeInfo(parent=parent)
        self.current_scope = child
        for statement in node.body:
            self.visit(statement)
        self.current_scope = parent

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._bind_local(alias.asname or alias.name.split(".", maxsplit=1)[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name != "*":
                self._bind_local(alias.asname or alias.name)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        for target in node.targets:
            self._record_assignment(target, node.value)
            self.visit(target)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.annotation is not None:
            self.visit(node.annotation)
        if node.value is not None:
            self.visit(node.value)
            self._record_assignment(node.target, node.value)
        else:
            self.scopes[self.current_scope].local_names.update(_local_target_names(node.target))
        self.visit(node.target)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        self._record_assignment(node.target, node.value)
        self.visit(node.target)


OriginSet = frozenset[str]


def _expression_origins(
    node: ast.AST | None,
    aliases: dict[str, OriginSet],
    zone_names: set[str],
) -> OriginSet:
    """Return the mutable game-container origins represented by an expression."""

    if node is None:
        return frozenset()
    if isinstance(node, ast.Name):
        return aliases.get(node.id, frozenset())
    if isinstance(node, ast.Attribute):
        dotted = _dotted(node)
        if dotted in aliases:
            return aliases[dotted]
        if node.attr in zone_names:
            return frozenset({f"zone:{node.attr}"})
        if node.attr == "stack":
            return frozenset({"stack"})
        return frozenset()
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "getattr" and len(node.args) >= 2:
            attribute = _literal_string(node.args[1])
            if attribute in zone_names:
                return frozenset({f"zone:{attribute}"})
            if attribute == "stack":
                return frozenset({"stack"})
        return frozenset()
    if isinstance(node, ast.NamedExpr):
        return _expression_origins(node.value, aliases, zone_names)
    if isinstance(node, ast.IfExp):
        return _expression_origins(node.body, aliases, zone_names).union(
            _expression_origins(node.orelse, aliases, zone_names)
        )
    if isinstance(node, ast.BoolOp):
        result: set[str] = set()
        for value in node.values:
            result.update(_expression_origins(value, aliases, zone_names))
        return frozenset(result)
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        result = set()
        for value in node.elts:
            result.update(_expression_origins(value, aliases, zone_names))
        return frozenset(result)
    if isinstance(node, ast.Dict):
        result = set()
        for value in node.values:
            result.update(_expression_origins(value, aliases, zone_names))
        return frozenset(result)
    return frozenset()


def _assignment_bindings(
    target: ast.AST,
    value: ast.AST,
    aliases: dict[str, OriginSet],
    zone_names: set[str],
) -> list[tuple[str, OriginSet]]:
    if isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, (ast.Tuple, ast.List)):
        if len(target.elts) == len(value.elts):
            bindings: list[tuple[str, OriginSet]] = []
            for child_target, child_value in zip(target.elts, value.elts, strict=True):
                bindings.extend(
                    _assignment_bindings(child_target, child_value, aliases, zone_names)
                )
            return bindings
    origins = _expression_origins(value, aliases, zone_names)
    return [(key, origins) for key in _target_keys(target)]


def _build_alias_index(
    tree: ast.AST,
    zone_names: set[str],
) -> tuple[dict[int, dict[str, OriginSet]], dict[int, int]]:
    collector = ScopeCollector()
    collector.visit(tree)
    resolved: dict[int, dict[str, OriginSet]] = {}

    def solve(scope_id: int) -> dict[str, OriginSet]:
        if scope_id in resolved:
            return resolved[scope_id]
        scope = collector.scopes[scope_id]
        inherited: dict[str, OriginSet] = {}
        if scope.parent is not None:
            inherited = {
                key: value
                for key, value in solve(scope.parent).items()
                if key.split(".", maxsplit=1)[0] not in scope.local_names
            }
        aliases = dict(inherited)
        changed = True
        while changed:
            changed = False
            for target, value in scope.assignments:
                for key, origins in _assignment_bindings(target, value, aliases, zone_names):
                    if not origins:
                        continue
                    merged = aliases.get(key, frozenset()).union(origins)
                    if merged != aliases.get(key, frozenset()):
                        aliases[key] = frozenset(merged)
                        changed = True
        resolved[scope_id] = aliases
        return aliases

    for scope_id in collector.scopes:
        solve(scope_id)
    return resolved, collector.node_scope


class ArchitectureScanner(ast.NodeVisitor):
    def __init__(
        self,
        *,
        path: Path,
        root: Path,
        config: dict[str, Any],
        tree: ast.AST,
    ) -> None:
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
        self.aliases_by_scope, self.node_scope = _build_alias_index(tree, self.zone_names)

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

    def _aliases(self, node: ast.AST) -> dict[str, OriginSet]:
        scope_id = self.node_scope.get(id(node), 0)
        return self.aliases_by_scope.get(scope_id, {})

    def _origins(self, node: ast.AST | None, context: ast.AST) -> OriginSet:
        return _expression_origins(node, self._aliases(context), self.zone_names)

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
        base = f"{'.' * node.level}{node.module or ''}".rstrip(".")
        if base:
            self._check_forbidden_import(node, base)
        for alias in node.names:
            candidate = base
            if alias.name != "*":
                separator = "" if not base or base.endswith(".") else "."
                candidate = f"{base}{separator}{alias.name}"
            if candidate:
                self._check_forbidden_import(node, candidate)
        self.generic_visit(node)

    def _check_forbidden_import(self, node: ast.AST, module: str) -> None:
        normalized = module.lstrip(".")
        for prefix in self.config["forbidden_import_prefixes"]:
            if normalized == prefix or normalized.startswith(prefix + "."):
                self.add(
                    node,
                    "LEGACY_IMPORT",
                    "The clean kernel may not depend on the legacy engine or pilot.",
                    normalized,
                )

    def _add_container_mutation(
        self,
        node: ast.AST,
        origins: OriginSet,
        detail: str,
    ) -> None:
        if any(origin.startswith("zone:") for origin in origins):
            if not self._zone_mutation_allowed():
                self.add(
                    node,
                    "ZONE_MUTATION",
                    "Only state initialization and ZoneService may mutate game zones.",
                    detail,
                )
        if "stack" in origins and not self._stack_mutation_allowed():
            self.add(
                node,
                "STACK_MUTATION",
                "Only the stack service may mutate the stack.",
                detail,
            )

    def visit_Call(self, node: ast.Call) -> None:
        chain = _attribute_names(node.func)
        method = chain[-1] if chain else ""
        receiver = node.func.value if isinstance(node.func, ast.Attribute) else None
        origins = self._origins(receiver, node) if receiver is not None else frozenset()

        if method in self.zone_mutators.union(self.stack_mutators) and receiver is not None:
            self._add_container_mutation(node, origins, ast.unparse(node))

        if (
            len(chain) == 2
            and chain[0] in {"list", "set", "dict"}
            and chain[1] in self.zone_mutators.union(self.stack_mutators)
            and node.args
        ):
            self._add_container_mutation(
                node,
                self._origins(node.args[0], node),
                ast.unparse(node),
            )

        if method == "insert" and "zone:library" in origins:
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

    def _check_assignment_target(
        self,
        node: ast.AST,
        target: ast.AST,
        *,
        augmented: bool = False,
    ) -> None:
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

            mutation_receiver: ast.AST | None = None
            if isinstance(item, ast.Subscript):
                mutation_receiver = item.value
            elif isinstance(item, ast.Attribute):
                mutation_receiver = item.value
            elif augmented:
                mutation_receiver = item
            if mutation_receiver is not None:
                self._add_container_mutation(
                    node,
                    self._origins(mutation_receiver, node),
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
        self._check_assignment_target(node, node.target, augmented=True)
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            self._check_assignment_target(node, target, augmented=True)
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
                path for path in candidate.rglob("*.py") if "__pycache__" not in path.parts
            )
    return sorted(files)


def _canonical_import_aliases(tree: ast.AST) -> tuple[dict[str, str], list[ast.ImportFrom]]:
    aliases: dict[str, str] = {}
    star_imports: list[ast.ImportFrom] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".", maxsplit=1)[0]
                canonical = alias.name if alias.asname else local
                aliases[local] = canonical
        elif isinstance(node, ast.ImportFrom):
            base = f"{'.' * node.level}{node.module or ''}".lstrip(".")
            for alias in node.names:
                if alias.name == "*":
                    if base in {"pytest", "unittest"}:
                        star_imports.append(node)
                    continue
                local = alias.asname or alias.name
                canonical = f"{base}.{alias.name}" if base else alias.name
                aliases[local] = canonical

    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            values: list[tuple[ast.AST, ast.AST]] = []
            if isinstance(node, ast.Assign):
                values.extend((target, node.value) for target in node.targets)
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                values.append((node.target, node.value))
            elif isinstance(node, ast.NamedExpr):
                values.append((node.target, node.value))
            for target, value in values:
                if not isinstance(target, ast.Name):
                    continue
                canonical = _resolve_imported_dotted(value, aliases)
                if not canonical.startswith(("pytest", "unittest")):
                    continue
                if aliases.get(target.id) != canonical:
                    aliases[target.id] = canonical
                    changed = True
    return aliases, star_imports


def _resolve_imported_dotted(node: ast.AST | None, aliases: dict[str, str]) -> str:
    tokens = list(_attribute_names(node))
    if not tokens:
        return ""
    replacement = aliases.get(tokens[0])
    if replacement:
        tokens = [*replacement.split("."), *tokens[1:]]
    return ".".join(tokens)


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

    aliases, star_imports = _canonical_import_aliases(tree)
    violations: dict[tuple[int, str], Violation] = {}
    prohibited = {
        "pytest.importorskip",
        "pytest.skip",
        "pytest.xfail",
        "pytest.mark.skip",
        "pytest.mark.skipif",
        "pytest.mark.xfail",
        "unittest.SkipTest",
        "unittest.expectedFailure",
        "unittest.skip",
        "unittest.skipIf",
        "unittest.skipUnless",
    }

    for node in star_imports:
        line = getattr(node, "lineno", 1)
        detail = ast.unparse(node)
        violations[(line, detail)] = Violation(
            path=_relative(path, root),
            line=line,
            code="SKIPPED_TEST_IMPORT",
            reason="Star imports from test frameworks prevent fail-closed skip detection.",
            detail=detail,
        )

    for node in ast.walk(tree):
        target: ast.AST | None = None
        if isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
            ):
                base = _resolve_imported_dotted(node.args[0], aliases)
                attribute = _literal_string(node.args[1])
                dotted = f"{base}.{attribute}" if base and attribute else ""
            else:
                target = node.func
                dotted = _resolve_imported_dotted(target, aliases)
        elif isinstance(node, (ast.Attribute, ast.Name)):
            target = node
            dotted = _resolve_imported_dotted(target, aliases)
        else:
            continue
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
        scanner = ArchitectureScanner(path=path, root=root, config=config, tree=tree)
        scanner.visit(tree)
        violations.extend(scanner.violations)

    if config.get("forbid_skipped_or_xfailed_tests", True):
        for path in _python_files(root, config.get("test_paths", [])):
            violations.extend(_scan_skips(path, root))

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
