#!/usr/bin/env python3
"""Prove no active workflow can reach the production pilot command."""

from __future__ import annotations

import argparse
import ast
import json
import re
import shlex
from pathlib import Path

SCRIPT_SUFFIXES = {".sh", ".bash", ".py"}
PILOT = re.compile(r"\bmtg-sim\s+pilot\s+--config\s+(?:\./)?configs/pilot\.toml\b")
LOCAL_PATH = re.compile(r"(?:^|\s)(?:bash|sh|python\d*|uv\s+run\s+python)\s+(\.?/?[\w./-]+)")
LOCAL_WORKFLOW = re.compile(r"uses:\s*(\./\.github/workflows/[\w./-]+)")


def _workflow_commands(text: str) -> list[str]:
    """Extract executable run scalars without treating comments as commands."""
    lines = text.splitlines()
    commands: list[str] = []
    index = 0
    while index < len(lines):
        match = re.match(r"^(\s*)run:\s*(.*)$", lines[index])
        if not match:
            index += 1
            continue
        indent, value = len(match.group(1)), match.group(2).strip()
        block: list[str] = []
        if value in {"|", "|-", "|+", ">", ">-", ">+"}:
            folded = value.startswith(">")
            index += 1
            while index < len(lines):
                line = lines[index]
                if line.strip() and len(line) - len(line.lstrip()) <= indent:
                    break
                block.append(line.strip())
                index += 1
            commands.append((" " if folded else "\n").join(block))
            continue
        commands.append(value)
        index += 1
    return commands


def _shell_commands(text: str) -> list[str]:
    commands: list[str] = []
    for line in text.splitlines():
        try:
            words = shlex.split(line, comments=True, posix=True)
        except ValueError:
            words = []
        if words:
            commands.append(" ".join(words))
    return commands


def _python_commands(text: str) -> list[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    commands: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        dotted = ast.unparse(node.func)
        if not (dotted.startswith("subprocess.") or dotted.startswith("os.system")):
            continue
        for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
            try:
                value = ast.literal_eval(argument)
            except (ValueError, TypeError):
                continue
            if isinstance(value, str):
                commands.append(value)
            elif isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
                commands.append(" ".join(value))
    return commands


def _commands(path: Path, text: str) -> list[str]:
    if path.suffix in {".yml", ".yaml"}:
        return [
            parsed for command in _workflow_commands(text) for parsed in _shell_commands(command)
        ]
    if path.suffix == ".py":
        return _python_commands(text)
    return _shell_commands(text)


def check(root: Path) -> dict[str, object]:
    root = root.resolve()
    queue = sorted((root / ".github/workflows").glob("*.y*ml"))
    seen: set[Path] = set()
    violations: list[dict[str, str]] = []
    while queue:
        path = queue.pop(0).resolve()
        if path in seen or not path.is_file() or root not in path.parents:
            continue
        seen.add(path)
        text = path.read_text(encoding="utf-8")
        commands = _commands(path, text)
        for command in commands:
            if match := PILOT.search(command):
                violations.append(
                    {"path": path.relative_to(root).as_posix(), "command": match.group(0)}
                )
            for reference in LOCAL_PATH.findall(command):
                candidate = (root / reference.removeprefix("./")).resolve()
                if candidate.suffix in SCRIPT_SUFFIXES:
                    queue.append(candidate)
        if path.suffix in {".yml", ".yaml"}:
            for reference in LOCAL_WORKFLOW.findall(text):
                queue.append((root / reference.removeprefix("./")).resolve())
    return {
        "status": "PASS" if not violations else "FAIL",
        "reachable_files": sorted(path.relative_to(root).as_posix() for path in seen),
        "violations": violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = check(args.root)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Production Pilot Lock: {result['status']}")
    for violation in result["violations"]:
        print(f"- {violation['path']}: {violation['command']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
