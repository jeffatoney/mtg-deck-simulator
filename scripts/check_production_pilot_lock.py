#!/usr/bin/env python3
"""Prove no active workflow can reach the production pilot command.

This scanner treats workflows as data.  It follows repository-local workflow,
shell, and Python references and normalizes YAML scalar whitespace before
looking for a pilot invocation.  It deliberately does not execute candidate
content.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
from pathlib import Path

SCRIPT_SUFFIXES = {".sh", ".bash", ".py"}
PILOT = re.compile(r"\bmtg-sim\s+pilot\s+--config\s+(?:\./)?configs/pilot\.toml\b")
LOCAL_REF = re.compile(r"(?:uses:\s*|(?:bash|sh|python\d*|uv\s+run\s+python)\s+)(\.?/?[\w./-]+)")


def _normalized(text: str) -> str:
    text = re.sub(r"\\\s*\n\s*", " ", text)
    text = re.sub(r"[>|]-?\s*\n(?:[ \t]+)", " ", text)
    return re.sub(r"\s+", " ", text)


def _is_dry(command: str) -> bool:
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    return "--dry-run" in words


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
        normalized = _normalized(text)
        for match in PILOT.finditer(normalized):
            window = normalized[max(0, match.start() - 120) : match.end() + 120]
            if not _is_dry(window):
                violations.append(
                    {"path": path.relative_to(root).as_posix(), "command": match.group(0)}
                )
        for reference in LOCAL_REF.findall(text):
            relative = reference.removeprefix("./")
            candidate = (root / relative).resolve()
            if candidate.suffix in SCRIPT_SUFFIXES or ".github/workflows" in candidate.as_posix():
                queue.append(candidate)
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
