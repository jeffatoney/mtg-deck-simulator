#!/usr/bin/env python3
"""Validate protected Phase A reference files and manifest without importing a kernel."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

EXPECTED_FILES = {
    "test_reference_contract.py",
    "test_forced_scenarios.py",
    "test_trace_invariants.py",
    "test_replay_contract.py",
    "test_analytics_contract.py",
}
BANNED_NAMES = {"skip", "skipif", "xfail", "importorskip", "monkeypatch", "mock", "patch"}


def acceptance_ids(specification: Path) -> set[str]:
    return set(re.findall(r"^- ([A-G]\d+)\.", specification.read_text(), flags=re.MULTILINE))


def static_errors(reference: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted(reference.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents: dict[ast.AST, ast.AST] = {
            child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                modules = [alias.name for alias in node.names]
                if isinstance(node, ast.ImportFrom) and node.module:
                    modules.append(node.module)
                top_level = not any(
                    isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef))
                    for parent in _ancestors(node, parents)
                )
                if top_level and any(
                    name == "mtg_kernel" or name.startswith("mtg_kernel.") for name in modules
                ):
                    errors.append(f"candidate import at module collection time: {path}")
            if isinstance(node, ast.Name) and node.id.lower() in BANNED_NAMES:
                errors.append(f"banned test replacement/suppression name {node.id}: {path}")
            if isinstance(node, ast.Attribute) and node.attr.lower() in BANNED_NAMES:
                errors.append(f"banned test replacement/suppression attribute {node.attr}: {path}")
    return errors


def _ancestors(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> list[ast.AST]:
    result: list[ast.AST] = []
    while node in parents:
        node = parents[node]
        result.append(node)
    return result


def validate(root: Path) -> tuple[list[str], list[str]]:
    reference = root / "tests/phase_a_reference"
    manifest_path = root / "automation/phase-a-reference-manifest.json"
    errors = [
        f"missing reference file: {name}"
        for name in sorted(EXPECTED_FILES)
        if not (reference / name).is_file()
    ]
    if not manifest_path.is_file():
        return [*errors, "missing protected reference manifest"], []
    errors.extend(static_errors(reference))
    manifest = json.loads(manifest_path.read_text())
    mappings = manifest.get("mappings", [])
    expected = acceptance_ids(root / "tests/acceptance/PHASE_A_ACCEPTANCE_SPEC.md")
    mapped = {item.get("acceptance_id") for item in mappings}
    if mapped != expected:
        errors.append(
            f"acceptance mapping mismatch: missing={sorted(expected - mapped)} extra={sorted(mapped - expected)}"
        )
    for item in mappings:
        if (
            not item.get("expected_postconditions")
            or item.get("required_production_entrypoint") != "mtg_kernel.executor.GameExecutor.run"
        ):
            errors.append(f"incomplete mapping: {item.get('acceptance_id')}")
    scenarios = json.loads((root / "automation/reference-scenarios.json").read_text())
    fixtures = root / "tests/fixtures/golden-replays"
    for scenario in scenarios.get("forced_scenarios", []):
        fixture = fixtures / f"{scenario['scenario_id']}.json"
        if not fixture.is_file():
            errors.append(f"missing golden replay fixture: {fixture.name}")
        elif json.loads(fixture.read_text()).get("review_status") != "independently-reviewed":
            errors.append(f"unreviewed golden replay fixture: {fixture.name}")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            f"--confcutdir={reference}",
            str(reference),
        ],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    nodes = [line for line in completed.stdout.splitlines() if "::" in line]
    if completed.returncode != 0:
        errors.append("protected reference collection failed:\n" + completed.stdout)
    missing_nodes = sorted({item["reference_node_id"] for item in mappings} - set(nodes))
    if missing_nodes:
        errors.append(f"manifest nodes not collected: {missing_nodes}")
    return errors, nodes


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    errors, nodes = validate(root)
    print(f"Protected reference suite: {'PASS' if not errors else 'FAIL'} ({len(nodes)} nodes)")
    for error in errors:
        print(f"- {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
