# Known limits of the Phase A gates

Every merge-blocking check in this repository is listed here with what it does *not*
cover. A gate whose limits are undocumented gets trusted for things it never did — which
is how two non-functional checks reached `main` in `f7639ce` reporting PASS.

## Layering

The clean-engine boundary is enforced at three levels, strongest first.

| Level | Mechanism | Defeats |
|---|---|---|
| 1 — structural | `legacy/mtg_sim` is not in `[tool.hatch.build.targets.wheel]`, so it is not an installed package | ordinary package-resolution imports; it does not prevent arbitrary file execution or every custom loader |
| 2 — runtime | `sys.addaudithook` in `tests/conftest.py`, active for the whole session | function-local imports, and legacy-artifact reads; converts a bare import error into a named violation |
| 3 — static | `scripts/check_clean_engine_boundary.py` | honest mistakes, at review time, before CI runs |

Level 3 is the weakest and is labeled `TRIPWIRE_NOT_A_COMPLETE_GATE` in its own output.
It exists for fast feedback, not for assurance. If levels 1 and 2 were removed, level 3
alone would not hold the boundary.

## `scripts/check_clean_engine_boundary.py`

**Covers.** Direct and from-imports of `mtg_sim`; dynamic loading through resolved
bindings (`import importlib as il`, `from importlib import import_module [as f]`, and
assignment aliases of either); literal concatenation and f-string module names;
non-constant arguments to any dynamic loader; the dynamic-loading and
process-execution APIs themselves regardless of argument; a literal `"mtg_sim"` string
anywhere in a clean package; `src/mtg_sim` reappearing on the installable import path.

**Does not cover.** `sys.modules["mtg_sim"]` lookups, which perform no import at all;
`getattr` on a module object; names assembled at runtime from `chr()` arithmetic,
`bytes.decode`, `base64`, or `str.join` over computed parts; C extensions; anything
reached through a third-party package's own dynamic loading. This list is not
exhaustive and cannot be made exhaustive — the set of ways one Python module can reach
another is unbounded. Do not add a "final" round of hardening here; add coverage at
level 1 or 2 instead.

**Scope.** Only `src/mtg_kernel` and `src/mtg_cards` are scanned. Nothing outside the
clean packages is examined, by design.

## `tests/conftest.py` (audit hook)

**Covers.** Any import of `mtg_sim` or a submodule, from anywhere in the process,
including imports written inside function bodies. Any read of a file under `artifacts/`
or `legacy/` that is not under an allowlisted root.

**Does not cover.** Reads performed by a subprocess — the hook is per-interpreter, and a
subprocess gets a fresh one. Data already loaded into memory before the hook installs.
Network reads. Writes are not audited, only reads, because the concern is contamination
of clean results by legacy input.

**Why an audit hook.** `sys.addaudithook` cannot be uninstalled once registered; a
`sys.meta_path` finder or a patched `__import__` can be removed by the code under test.
The mechanism was chosen for that property specifically.

## `scripts/check_identity_lock.py`

**Covers.** Any change to `IDENTITY_MODEL_V2.0.0.md`, because the expected digest is a
constant in the script rather than a value read from the approval record. Also: the
approval record pointing at a different document, disagreeing with the anchor, losing
its frozen status, dropping its approver or timestamp, carrying an approval statement
that does not bind the anchored digest, recording a blob id that does not match the
bytes on disk, or citing a commit absent from this repository.

**Does not cover.** Whether the human named in `approved_by` actually approved anything
— that is a claim in a data file, not a signature. Cryptographic signing would close
this; it is not currently in scope. `qa_checks` are self-declared booleans and are
deliberately not treated as evidence.

**Rotation.** Changing the identity model requires editing the document, its two
companions, *and* `EXPECTED_DOCUMENT_SHA256` in the script, in one reviewed commit. This
is intended friction.

## `scripts/check_phase_a_authority.py`

**Covers.** ACTIVE_BINDING files exist; required archival files exist; forbidden active
paths are absent (currently the pilot workflow and `src/mtg_sim`); no file is classified
both active and archival; the frozen evidence-label set is intact; the two Phase A
contract documents cross-reference the authority map.

**Does not cover.** Whether any artifact actually carries a `CLEAN_ENGINE_PRODUCTION_PATH`
label. Nothing inspects evidence for labels. The `prohibited_as_phase_a_evidence` list is
a classification binding on human reviewers, not a machine check. Stating this plainly
because the merge report for `f7639ce` described this check as "CI enforcement requiring
CLEAN_ENGINE_PRODUCTION_PATH evidence," which it is not.

## The channel no gate covers

None of the above prevents the highest-likelihood contamination: **transcription**.
Codex reading `legacy/mtg_sim/engine.py` and hand-writing equivalent logic into
`mtg_kernel` produces no import, opens no artifact, and passes every check here. It is
the path of least resistance for an agent asked to build an engine while a working-ish
one sits in the tree.

There is no gate for this. The available mitigations are review-time and advisory:

- a similarity report comparing normalized `mtg_kernel` function bodies against
  `legacy/mtg_sim` (never merge-blocking — it will have false positives on any correct
  implementation of the same rule);
- requiring each `mtg_kernel` rules behavior to cite a Comprehensive Rules paragraph
  rather than a legacy code location;
- the golden-transcript workstream, where ground truth is human-approved rather than
  inherited.

Treat "all gates green" as meaning the linkage and provenance channels are clean. It
says nothing about the transcription channel.


## CODEOWNERS and protected-branch rules

`CODEOWNERS` is ownership metadata only. It does not make review mandatory and is not
the digest anchor. The repository variable `IDENTITY_MODEL_V2_SHA256` is the external
digest anchor. To protect the checker and workflow from same-change weakening, `main`
must also require the CI check and an independent approval through branch protection
or a repository ruleset. That repository setting is outside the committed code and is
intentionally reported as a human-configured prerequisite.
