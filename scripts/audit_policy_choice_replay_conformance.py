#!/usr/bin/env python3
"""Audit exact-deck policy, choice legality, and replay conformance.

This is a proof/audit lane. It does not change game or card behavior. The checker
fails closed when the interaction surface requires a strategic choice with no
reviewed policy route, when a runtime purpose has no production policy handler,
or when the policy/replay protocol drifts.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "automation/strategic-choice-conformance.json"
LOCK_PATH = ROOT / "automation/interaction-coverage-lock.json"


@dataclass(frozen=True)
class PurposeEmission:
    pattern: str
    path: str
    function: str


@dataclass(frozen=True)
class UnresolvedPurpose:
    path: str
    function: str
    parameter: str | None


@dataclass(frozen=True)
class SourceInvariantResult:
    name: str
    path: str
    missing_tokens: tuple[str, ...]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _parse(path: str) -> ast.Module:
    return ast.parse(_read(path), filename=path)


def _call_tail(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _purpose_expr_pattern(node: ast.AST | None, env: dict[str, str] | None = None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Name) and env is not None:
        return env.get(node.id)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                parts.append("*")
            else:
                return None
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _purpose_expr_pattern(node.left, env)
        right = _purpose_expr_pattern(node.right, env)
        if left is not None and right is not None:
            return left + right
    return None


class _PurposeEmissionVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.functions: list[str] = []
        self.parameters: list[set[str]] = []
        self.environments: list[dict[str, str]] = []
        self.emissions: list[PurposeEmission] = []
        self.unresolved: list[UnresolvedPurpose] = []

    @property
    def _function(self) -> str:
        return self.functions[-1] if self.functions else "<module>"

    @property
    def _env(self) -> dict[str, str]:
        return self.environments[-1] if self.environments else {}

    def _enter_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        args = {
            item.arg
            for item in (
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            )
        }
        if node.args.vararg is not None:
            args.add(node.args.vararg.arg)
        if node.args.kwarg is not None:
            args.add(node.args.kwarg.arg)
        self.functions.append(node.name)
        self.parameters.append(args)
        self.environments.append({})
        for child in node.body:
            self.visit(child)
        self.environments.pop()
        self.parameters.pop()
        self.functions.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._enter_function(node)
        return None

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._enter_function(node)
        return None

    def visit_Assign(self, node: ast.Assign) -> Any:
        pattern = _purpose_expr_pattern(node.value, self._env)
        if pattern is not None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._env[target.id] = pattern
        self.generic_visit(node)
        return None

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
        pattern = _purpose_expr_pattern(node.value, self._env)
        if pattern is not None and isinstance(node.target, ast.Name):
            self._env[node.target.id] = pattern
        self.generic_visit(node)
        return None

    def visit_Call(self, node: ast.Call) -> Any:
        if _call_tail(node.func) == "CardSelectionRequest":
            purpose = next((kw.value for kw in node.keywords if kw.arg == "purpose"), None)
            pattern = _purpose_expr_pattern(purpose, self._env)
            if pattern is not None:
                self.emissions.append(PurposeEmission(pattern, self.path, self._function))
            else:
                parameter: str | None = None
                if (
                    isinstance(purpose, ast.Name)
                    and self.parameters
                    and purpose.id in self.parameters[-1]
                ):
                    parameter = purpose.id
                self.unresolved.append(UnresolvedPurpose(self.path, self._function, parameter))
        self.generic_visit(node)
        return None


def _source_trees() -> list[tuple[str, ast.Module]]:
    result: list[tuple[str, ast.Module]] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        result.append((relative, ast.parse(path.read_text(encoding="utf-8"), filename=relative)))
    return result


def _helper_callsite_patterns(
    trees: list[tuple[str, ast.Module]], helper: UnresolvedPurpose
) -> tuple[set[str], bool]:
    if helper.parameter is None:
        return set(), True
    patterns: set[str] = set()
    saw_unresolved = False
    for _, tree in trees:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _call_tail(node.func) != helper.function:
                continue
            keyword = next(
                (kw.value for kw in node.keywords if kw.arg == helper.parameter),
                None,
            )
            if keyword is None:
                continue
            pattern = _purpose_expr_pattern(keyword)
            if pattern is None:
                saw_unresolved = True
            else:
                patterns.add(pattern)
    if not patterns:
        saw_unresolved = True
    return patterns, saw_unresolved


def _runtime_purpose_emissions() -> tuple[list[PurposeEmission], list[str]]:
    trees = _source_trees()
    emissions: list[PurposeEmission] = []
    unresolved_helpers: list[UnresolvedPurpose] = []
    for path, tree in trees:
        visitor = _PurposeEmissionVisitor(path)
        visitor.visit(tree)
        emissions.extend(visitor.emissions)
        unresolved_helpers.extend(visitor.unresolved)

    unresolved: list[str] = []
    for helper in unresolved_helpers:
        patterns, saw_unresolved = _helper_callsite_patterns(trees, helper)
        for pattern in patterns:
            emissions.append(PurposeEmission(pattern, helper.path, helper.function))
        if saw_unresolved:
            suffix = f":{helper.parameter}" if helper.parameter else ""
            unresolved.append(f"{helper.path}:{helper.function}{suffix}")

    deduped = {(item.pattern, item.path, item.function): item for item in emissions}
    return (
        sorted(
            deduped.values(),
            key=lambda item: (item.pattern, item.path, item.function),
        ),
        sorted(set(unresolved)),
    )


def _is_request_purpose(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "purpose"
        and isinstance(node.value, ast.Name)
        and node.value.id == "request"
    )


def _string_values(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        values: set[str] = set()
        for item in node.elts:
            if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
                return set()
            values.add(item.value)
        return values
    return set()


def _production_policy_patterns() -> set[str]:
    patterns: set[str] = set()
    for path in ("src/mtg_policy/choices.py", "src/mtg_policy/trigger_choices.py"):
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
                left = node.left
                right = node.comparators[0]
                op = node.ops[0]
                if isinstance(op, ast.Eq):
                    if _is_request_purpose(left):
                        patterns.update(_string_values(right))
                    elif _is_request_purpose(right):
                        patterns.update(_string_values(left))
                elif isinstance(op, ast.In) and _is_request_purpose(left):
                    patterns.update(_string_values(right))
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "startswith"
                and _is_request_purpose(node.func.value)
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                patterns.add(str(node.args[0].value) + "*")
    return patterns


def _matches(pattern: str, supported: str) -> bool:
    if supported.endswith("*"):
        prefix = supported[:-1]
        if pattern.endswith("*"):
            return pattern[:-1].startswith(prefix) or prefix.startswith(pattern[:-1])
        return pattern.startswith(prefix)
    if pattern.endswith("*"):
        return False
    return pattern == supported


def _class_methods(path: str, class_name: str) -> set[str]:
    for node in _parse(path).body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                child.name
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    return set()


def _trigger_policy_effect_kinds() -> set[str]:
    tree = _parse("src/mtg_policy/trigger_choices.py")
    kinds: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or len(node.ops) != 1 or len(node.comparators) != 1:
            continue
        left, right, op = node.left, node.comparators[0], node.ops[0]
        if not isinstance(left, ast.Name) or left.id != "effect_kind":
            continue
        if isinstance(op, ast.Eq):
            kinds.update(_string_values(right))
        elif isinstance(op, ast.In):
            kinds.update(_string_values(right))
    return kinds


def _source_invariants(registry: dict[str, Any]) -> list[SourceInvariantResult]:
    results: list[SourceInvariantResult] = []
    for raw in registry.get("source_invariants", []):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "unnamed"))
        path = str(raw.get("path", ""))
        required = tuple(str(value) for value in raw.get("must_contain", []))
        try:
            text = _read(path)
            missing = tuple(token for token in required if token not in text)
        except OSError:
            missing = required or ("<missing file>",)
        results.append(SourceInvariantResult(name, path, missing))
    return results


def _load_manifest() -> dict[str, Any]:
    try:
        from scripts.build_interaction_coverage_manifest import build_manifest
    except ModuleNotFoundError:
        from build_interaction_coverage_manifest import build_manifest  # type: ignore[no-redef]
    return build_manifest()


def _surface_is_frozen(manifest: dict[str, Any]) -> bool:
    try:
        lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    zero = "sha256:" + ("0" * 64)
    return bool(
        lock.get("manifest_sha256") == manifest.get("manifest_sha256")
        and lock.get("manifest_sha256") != zero
        and int(lock.get("record_count", 0)) == int(manifest.get("record_count", -1))
    )


def _strategic_surface_choices(manifest: dict[str, Any]) -> list[dict[str, str]]:
    choices: dict[tuple[str, str, str], dict[str, str]] = {}
    for record in manifest.get("records", []):
        if not isinstance(record, dict):
            continue
        record_id = str(record.get("record_id", ""))
        for raw in record.get("choices", []):
            if not isinstance(raw, dict):
                continue
            policy_class = str(raw.get("policy_class", ""))
            if policy_class in {"NONE", "MANDATORY_DETERMINISTIC"}:
                continue
            item = {
                "timing": str(raw.get("timing", "")),
                "purpose": str(raw.get("purpose", "")),
                "policy_class": policy_class,
                "record_id": record_id,
            }
            choices.setdefault((item["timing"], item["purpose"], item["policy_class"]), item)
    return sorted(
        choices.values(),
        key=lambda item: (item["timing"], item["purpose"], item["policy_class"]),
    )


def _route_matches(choice: dict[str, str], route: dict[str, Any]) -> bool:
    if str(route.get("timing", "")) != choice["timing"]:
        return False
    route_purpose = str(route.get("purpose", ""))
    if route_purpose.endswith("*"):
        if not choice["purpose"].startswith(route_purpose[:-1]):
            return False
    elif route_purpose != choice["purpose"]:
        return False
    policy_class = route.get("policy_class")
    return policy_class in {None, "*", choice["policy_class"]}


def _targeted_trigger_effects(manifest: dict[str, Any]) -> set[str]:
    kinds: set[str] = set()
    for record in manifest.get("records", []):
        if not isinstance(record, dict) or record.get("record_class") != "CARD_EFFECT":
            continue
        for choice in record.get("choices", []):
            if not isinstance(choice, dict):
                continue
            if (
                choice.get("purpose") == "TARGET_SELECTION"
                and choice.get("timing") == "TRIGGER_STACKING"
            ):
                effect = record.get("effect", {})
                if isinstance(effect, dict):
                    kinds.add(str(effect.get("kind", "")))
    return {kind for kind in kinds if kind}


def audit_conformance() -> dict[str, Any]:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    violations: list[str] = []
    warnings: list[str] = []

    if registry.get("schema_version") != "strategic-choice-conformance-v1":
        violations.append("unsupported strategic choice conformance registry schema")

    emissions, unresolved = _runtime_purpose_emissions()
    emitted_patterns = sorted({item.pattern for item in emissions})
    policy_patterns = sorted(_production_policy_patterns())
    registry_patterns = [
        str(item.get("runtime_purpose"))
        for item in registry.get("runtime_purpose_contracts", [])
        if isinstance(item, dict) and item.get("runtime_purpose")
    ]

    for location in unresolved:
        violations.append(
            f"runtime CardSelectionRequest purpose is not statically auditable: {location}"
        )
    for pattern in emitted_patterns:
        if not any(_matches(pattern, value) for value in policy_patterns):
            violations.append(f"runtime purpose has no production policy handler: {pattern}")
        if not any(
            _matches(pattern, value) or _matches(value, pattern) for value in registry_patterns
        ):
            violations.append(f"runtime purpose is absent from the conformance registry: {pattern}")
    for pattern in registry_patterns:
        if not any(
            _matches(value, pattern) or _matches(pattern, value) for value in emitted_patterns
        ):
            warnings.append(f"registered runtime purpose is not currently emitted: {pattern}")

    protocol_methods = _class_methods(
        "src/mtg_kernel/strategic_choices.py", "StrategicChoiceProvider"
    )
    replay_methods = _class_methods(
        "src/mtg_kernel/strategic_choices.py", "RecordedStrategicChoiceProvider"
    )
    base_policy_methods = _class_methods(
        "src/mtg_policy/choices.py", "PolicyStrategicChoiceProvider"
    )
    missing_policy_methods = sorted(protocol_methods - base_policy_methods)
    missing_replay_methods = sorted(protocol_methods - replay_methods)
    if missing_policy_methods:
        violations.append(
            "production policy provider omits protocol methods: "
            + ", ".join(missing_policy_methods)
        )
    if missing_replay_methods:
        violations.append(
            "recorded replay provider omits protocol methods: " + ", ".join(missing_replay_methods)
        )

    invariant_results = _source_invariants(registry)
    for result in invariant_results:
        if result.missing_tokens:
            violations.append(
                f"source invariant {result.name!r} is incomplete in {result.path}: "
                + ", ".join(result.missing_tokens)
            )

    try:
        manifest = _load_manifest()
    except Exception as exc:
        manifest = {}
        violations.append(f"interaction surface cannot be built: {exc}")

    surface_frozen = _surface_is_frozen(manifest) if manifest else False
    strategic_choices = _strategic_surface_choices(manifest) if manifest else []
    routes = [item for item in registry.get("canonical_routes", []) if isinstance(item, dict)]
    unrouted: list[dict[str, str]] = []
    for choice in strategic_choices:
        if not any(_route_matches(choice, route) for route in routes):
            unrouted.append(choice)
            violations.append(
                "interaction choice has no reviewed policy/replay route: "
                f"{choice['timing']}:{choice['purpose']} [{choice['policy_class']}]"
            )

    for route in routes:
        mechanism = str(route.get("mechanism", ""))
        protocol_method = route.get("protocol_method")
        if mechanism == "PROTOCOL_METHOD":
            method = str(protocol_method or "")
            if not method:
                violations.append("protocol route omits protocol_method")
            else:
                if method not in protocol_methods:
                    violations.append(f"canonical route names unknown protocol method: {method}")
                if method not in base_policy_methods:
                    violations.append(
                        f"canonical route protocol method lacks production policy support: {method}"
                    )
                if method not in replay_methods:
                    violations.append(
                        f"canonical route protocol method lacks recorded replay support: {method}"
                    )

        runtime_purpose = route.get("runtime_purpose")
        if runtime_purpose:
            runtime_pattern = str(runtime_purpose)
            if not any(
                _matches(value, runtime_pattern) or _matches(runtime_pattern, value)
                for value in emitted_patterns
            ):
                violations.append(
                    "canonical route names a runtime purpose that production does not emit: "
                    + runtime_pattern
                )
            if not any(_matches(runtime_pattern, value) for value in policy_patterns):
                violations.append(
                    "canonical route runtime purpose lacks production policy support: "
                    + runtime_pattern
                )

    targeted_effects = _targeted_trigger_effects(manifest) if manifest else set()
    supported_trigger_effects = _trigger_policy_effect_kinds()
    missing_trigger_effects = sorted(targeted_effects - supported_trigger_effects)
    for effect in missing_trigger_effects:
        violations.append(
            "triggered target effect requires a policy provider but is unsupported: " + effect
        )

    violations = list(dict.fromkeys(violations))
    warnings = list(dict.fromkeys(warnings))
    return {
        "schema_version": "policy-choice-replay-conformance-report-v1",
        "status": "PASS" if not violations else "FAIL",
        "proof_status": (
            "FROZEN_SURFACE" if surface_frozen else "PROVISIONAL_UNTIL_COORDINATOR_FREEZE"
        ),
        "surface_frozen": surface_frozen,
        "surface_sha256": manifest.get("manifest_sha256") if manifest else None,
        "surface_record_count": manifest.get("record_count") if manifest else None,
        "runtime_purpose_emissions": [asdict(item) for item in emissions],
        "runtime_purpose_patterns": emitted_patterns,
        "production_policy_patterns": policy_patterns,
        "protocol_methods": sorted(protocol_methods),
        "production_policy_methods": sorted(base_policy_methods),
        "recorded_replay_methods": sorted(replay_methods),
        "strategic_surface_choice_count": len(strategic_choices),
        "strategic_surface_choices": strategic_choices,
        "unrouted_surface_choices": unrouted,
        "targeted_trigger_effects": sorted(targeted_effects),
        "trigger_policy_effects": sorted(supported_trigger_effects),
        "missing_trigger_policy_effects": missing_trigger_effects,
        "source_invariants": [asdict(item) for item in invariant_results],
        "warnings": warnings,
        "violations": violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-frozen-surface", action="store_true")
    args = parser.parse_args()

    report = audit_conformance()
    if args.require_frozen_surface and not report["surface_frozen"]:
        report["violations"].append("coordinator interaction surface is not frozen")
        report["status"] = "FAIL"
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
