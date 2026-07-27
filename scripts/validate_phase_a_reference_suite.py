#!/usr/bin/env python3
"""Validate protected Phase A reference files and manifest without importing a kernel."""

from __future__ import annotations

import ast
import hashlib
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
SCENARIO_FIELDS = {
    "scenario_id",
    "scenario_version",
    "schema_version",
    "assertion_id",
    "acceptance_requirement",
    "number_of_players",
    "active_player",
    "priority_holder",
    "turn",
    "phase",
    "step",
    "life_totals",
    "card_instances",
    "objects",
    "initial_state",
    "library_constraints",
    "external_objects",
    "external_zone_ledger_expectations",
    "action_script",
    "legal_alternatives",
    "rng_streams",
    "prerequisites",
    "expected_state_transition_predicates",
    "expected_final_state_predicates",
    "requirement_text",
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
    reference = root / "tests/phase_a_acceptance"
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
    scenario_document = json.loads((root / "automation/reference-scenarios.json").read_text())
    scenarios = {item["scenario_id"]: item for item in scenario_document.get("scenarios", [])}
    for item in mappings:
        if (
            not item.get("referee_evaluator_id")
            or not item.get("raw_evidence_fields")
            or not item.get("expected_transition_or_invariant")
            or not item.get("required_production_entrypoint")
        ):
            errors.append(f"incomplete mapping: {item.get('acceptance_id')}")
            continue
        scenario = scenarios.get(item.get("scenario_id"))
        if scenario is None:
            errors.append(f"unknown mapping scenario: {item.get('acceptance_id')}")
            continue
        if set(scenario) != SCENARIO_FIELDS:
            errors.append(f"scenario schema mismatch: {scenario['scenario_id']}")
        if item["referee_evaluator_id"] != scenario["assertion_id"]:
            errors.append(f"evaluator mismatch: {item['acceptance_id']}")
        if scenario.get("schema_version") != 3 or not scenario.get("action_script"):
            errors.append(f"invalid frozen scenario input: {item['acceptance_id']}")
        player_ids = set(scenario.get("life_totals", {}))
        object_ids = [obj.get("object_id") for obj in scenario.get("objects", [])]
        card_ids = [card.get("card_instance_id") for card in scenario.get("card_instances", [])]
        zone_ids = [
            oid
            for zone in scenario.get("initial_state", {}).get("zones", {}).values()
            for oid in zone
        ]
        if (
            len(player_ids) != scenario.get("number_of_players")
            or scenario.get("active_player") not in player_ids
            or scenario.get("priority_holder") not in player_ids
            or len(object_ids) != len(set(object_ids))
            or len(card_ids) != len(set(card_ids))
            or not set(zone_ids) <= set(object_ids)
            or [a.get("script_index") for a in scenario["action_script"]]
            != list(range(1, len(scenario["action_script"]) + 1))
        ):
            errors.append(f"malformed frozen scenario identity/script: {item['acceptance_id']}")
        if any("expected" in action or "result" in action for action in scenario["action_script"]):
            errors.append(f"scenario script requests an outcome: {item['acceptance_id']}")
        evaluator_source = (reference / "reference_adapter.py").read_text(encoding="utf-8")
        if f"def {item['referee_evaluator_id']}(" not in evaluator_source:
            errors.append(f"missing referee evaluator: {item['acceptance_id']}")
        prerequisites = item.get("required_prerequisites", {})
        declared = scenario.get("prerequisites", {})
        if any(
            not set(values) <= set(declared.get(key, [])) for key, values in prerequisites.items()
        ):
            errors.append(f"scenario prerequisites missing: {item['acceptance_id']}")
        if item["acceptance_id"] not in declared.get("acceptance_ids", []):
            errors.append(f"unrelated scenario mapping: {item['acceptance_id']}")
    if len({(item["scenario_id"], item["referee_evaluator_id"]) for item in mappings}) != len(
        mappings
    ):
        errors.append("duplicate scenario/assertion mapping")
    fixtures = root / "tests/fixtures/golden-replays"
    approval_document = json.loads((root / "automation/golden-replay-approvals.json").read_text())
    approvals = {item["fixture_path"]: item for item in approval_document["approvals"]}
    core = {
        "sol-ring",
        "soul-guide-lantern-targeted-etb",
        "malcolm-counterspell-commit",
        "dualcaster-twinflame",
        "glint-horn-attack-cleanup",
    }
    for scenario_id in core:
        fixture = fixtures / f"{scenario_id}.json"
        if not fixture.is_file():
            errors.append(f"missing golden replay fixture: {fixture.name}")
        else:
            status = json.loads(fixture.read_text()).get("review_status")
            if status not in {
                "draft-unreviewed",
                "rules-reviewed",
                "independently-reviewed",
            }:
                errors.append(f"invalid golden replay provenance: {fixture.name}")
            if status == "independently-reviewed":
                relative = fixture.relative_to(root).as_posix()
                approval = approvals.get(relative)
                digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
                if (
                    not approval
                    or approval.get("sha256") != digest
                    or not all(
                        approval.get(field)
                        for field in ("reviewer", "approval_date", "approving_commit")
                    )
                ):
                    errors.append(f"missing matching human approval: {fixture.name}")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-ra",
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
    lowered = completed.stdout.lower()
    if " skipped" in lowered or " xfailed" in lowered or " xpassed" in lowered:
        errors.append("protected collection contains skipped or xfailed nodes")
    missing_nodes = sorted({item["reference_node_id"] for item in mappings} - set(nodes))
    if missing_nodes:
        errors.append(f"manifest nodes not collected: {missing_nodes}")
    node_ids = [item["reference_node_id"] for item in mappings]
    if len(node_ids) != len(set(node_ids)) or len(mappings) != len(expected):
        errors.append("acceptance mappings must have one unique protected node per requirement")
    for item in mappings:
        acceptance_id = item["acceptance_id"]
        prefix = f"tests/phase_a_acceptance/test_reference_contract.py::test_{acceptance_id}_"
        if not item["reference_node_id"].startswith(prefix):
            errors.append(f"invalid protected node prefix: {acceptance_id}")
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
