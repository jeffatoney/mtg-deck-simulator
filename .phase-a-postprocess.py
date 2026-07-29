from __future__ import annotations

import hashlib
import json
from pathlib import Path

root = Path.cwd()

def replace_required(path: str, old: str, new: str) -> None:
    target = root / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"required text not found in {path}: {old!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")

# The legacy command is removed by the patch. Active instructions must use
# the source-only CLI, and Phase A must create a clean-engine CLI of its own.
for path in (
    "AGENTS.md",
    "README.md",
    "prompts/recovery/PHASE_A_ENGINE_BUILD.md",
):
    target = root / path
    value = target.read_text(encoding="utf-8")
    value = value.replace(
        "uv run mtg-sim validate-sources",
        "uv run mtg-sources validate-sources",
    )
    value = value.replace(
        "uv run mtg-sim engine verify-phase-a",
        "uv run mtg-engine verify-phase-a",
    )
    target.write_text(value, encoding="utf-8")

prompt = root / "prompts/recovery/PHASE_A_ENGINE_BUILD.md"
prompt_text = prompt.read_text(encoding="utf-8")
marker = "Add a dedicated command:\n\n```bash\nuv run mtg-engine verify-phase-a\n```"
if marker not in prompt_text:
    raise SystemExit("Phase A prompt does not define the clean mtg-engine command")
prompt_text = prompt_text.replace(
    marker,
    marker
    + "\n\nPhase A must add the `mtg-engine` project entry point and its clean "
      "`mtg_kernel` CLI implementation. The source-only `mtg-sources` command "
      "must remain separate and must never execute rules or simulations.",
)
prompt.write_text(prompt_text, encoding="utf-8")

# CODEOWNERS is review metadata, not self-enforcing protection.
codeowners = root / ".github/CODEOWNERS"
value = codeowners.read_text(encoding="utf-8")
old = '''# CODEOWNERS is the out-of-band anchor for the Phase A gates.
#
# GitHub evaluates this file from the BASE branch, so a pull request cannot grant
# itself ownership by editing it. That property is what makes the entries below
# meaningful: everything a pull request would have to touch in order to weaken a gate
# requires review from someone who is not the pull request.
#
# Verifying the identity document harder is pointless if the verification step can be
# deleted in the same diff, so the checkers and their invocation are covered too --
# not just the documents they check.
'''
new = '''# CODEOWNERS identifies the owner for Phase A gate files.
#
# This file does not enforce review by itself. It becomes a merge control only when a
# protected-branch rule or repository ruleset requires code-owner review and prevents
# the pull-request author from satisfying that review alone. The repository variable
# IDENTITY_MODEL_V2_SHA256 is the external digest anchor; CODEOWNERS is review metadata.
#
# The checkers, CI invocation, packaging boundary, identity files, governance map, and
# session audit hook are covered so a ruleset can protect the whole gate surface.
'''
if old not in value:
    raise SystemExit("CODEOWNERS review preamble did not match expected patch text")
codeowners.write_text(value.replace(old, new), encoding="utf-8")

# Correct claims that branch protection already exists or that ordinary package
# isolation defeats arbitrary file execution.
identity_checker = root / "scripts/check_identity_lock.py"
value = identity_checker.read_text(encoding="utf-8")
old = '''Two residual holes, both closed by branch protection rather than by code, and both
recorded in docs/audit/GATE_KNOWN_LIMITS.md:

* this script could be edited in the same pull request to skip its own check;
* the workflow step invoking it could be deleted, or made non-required.

CODEOWNERS covers ``scripts/`` and ``.github/workflows/`` for exactly this reason, and
GitHub evaluates CODEOWNERS from the base branch, so a pull request cannot grant itself
ownership. That is the genuine out-of-band anchor.
'''
new = '''Two residual holes require repository controls outside this script:

* this script could be edited in the same pull request to skip its own check;
* the workflow step invoking it could be deleted, or made non-required.

CODEOWNERS identifies the affected paths but does not enforce review by itself.
A protected-branch rule or repository ruleset must require the CI job and an
independent approval for gate changes. The repository variable is the external
digest anchor; branch protection is a separate human-configured control.
'''
if old not in value:
    raise SystemExit("identity checker governance paragraph did not match")
identity_checker.write_text(value.replace(old, new), encoding="utf-8")

boundary = root / "scripts/check_clean_engine_boundary.py"
value = boundary.read_text(encoding="utf-8")
value = value.replace(
    '''The actual boundary is that ``legacy/mtg_sim`` is not an installed package, so it is
not importable from any environment built from ``pyproject.toml``. Every bypass this
scanner misses still fails at runtime with ``ModuleNotFoundError``. The session-wide
audit hook in ``tests/conftest.py`` is the second layer, and turns such a failure into
a named boundary violation.
''',
    '''The primary structural boundary is that ``legacy/mtg_sim`` is not an installed
package, so ordinary imports through Python's package resolver fail. That does not
prevent arbitrary file execution or every custom loader. The session-wide audit hook
in ``tests/conftest.py`` and this tripwire provide additional reviewed/tested layers.
''',
)
boundary.write_text(value, encoding="utf-8")

conftest = root / "tests/conftest.py"
value = conftest.read_text(encoding="utf-8")
value = value.replace(
    '''The guard is defence in depth, not the primary boundary. The primary boundary is
that ``legacy/mtg_sim`` is not an installed package and therefore is not importable
at all (see ``[tool.hatch.build.targets.wheel]`` in ``pyproject.toml``). This hook
exists so that a violation is reported as a named, actionable failure instead of a
bare ``ModuleNotFoundError``, and so the provenance channel is covered too.
''',
    '''The guard is defence in depth. The structural boundary is that
``legacy/mtg_sim`` is not an installed package and therefore is unavailable through
ordinary package resolution (see ``[tool.hatch.build.targets.wheel]`` in
``pyproject.toml``). Arbitrary file execution remains possible in Python; this hook
makes tested import and provenance violations explicit.
''',
)
conftest.write_text(value, encoding="utf-8")

known = root / "docs/audit/GATE_KNOWN_LIMITS.md"
value = known.read_text(encoding="utf-8")
value = value.replace(
    "| 1 — structural | `legacy/mtg_sim` is not in `[tool.hatch.build.targets.wheel]`, so it is not an installed package | every import route, including ones nobody has thought of; failure is `ModuleNotFoundError` |",
    "| 1 — structural | `legacy/mtg_sim` is not in `[tool.hatch.build.targets.wheel]`, so it is not an installed package | ordinary package-resolution imports; it does not prevent arbitrary file execution or every custom loader |",
)
value += '''\n
## CODEOWNERS and protected-branch rules

`CODEOWNERS` is ownership metadata only. It does not make review mandatory and is not
the digest anchor. The repository variable `IDENTITY_MODEL_V2_SHA256` is the external
digest anchor. To protect the checker and workflow from same-change weakening, `main`
must also require the CI check and an independent approval through branch protection
or a repository ruleset. That repository setting is outside the committed code and is
intentionally reported as a human-configured prerequisite.
'''
known.write_text(value, encoding="utf-8")

# The authority checker enforces declarations and path constraints, not labels on
# result artifacts. Keep the records precise.
governance = root / "docs/governance/PHASE_A_AUTHORITY_MAP.md"
value = governance.read_text(encoding="utf-8")
value += '''\n
## Machine-enforcement boundary

CI verifies this classification's structure, required references, and forbidden or
required paths. CI does not yet inspect Phase A result artifacts for evidence labels.
Artifact-level enforcement belongs to the future `mtg-engine verify-phase-a` result
validator. Until that exists, evidence labels are a binding review requirement rather
than an artifact-level machine check.
'''
governance.write_text(value, encoding="utf-8")

# No active instruction may call the removed legacy command.
for path in (
    root / "AGENTS.md",
    root / "README.md",
    root / "prompts/recovery/PHASE_A_ENGINE_BUILD.md",
    root / "docs/spec/ENGINE_BUILD_PHASE_A.md",
):
    if "uv run mtg-sim" in path.read_text(encoding="utf-8"):
        raise SystemExit(f"active legacy CLI reference remains in {path}")

# Refresh every existing handoff-manifest entry after intentional edits.
manifest_path = root / "HANDOFF_MANIFEST.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
for relative, metadata in manifest.items():
    path = root / relative
    if not path.is_file():
        continue
    data = path.read_bytes()
    metadata["bytes"] = len(data)
    metadata["sha256"] = hashlib.sha256(data).hexdigest()
manifest_path.write_text(
    json.dumps(manifest, indent=2, sort_keys=False) + "\n",
    encoding="utf-8",
)
