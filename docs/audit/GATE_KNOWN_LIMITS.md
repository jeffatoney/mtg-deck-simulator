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
bindings and assignment aliases; executable string references to the quarantined package;
and `src/mtg_sim` reappearing on the installable import path.

The scanner has two tiers:

- **STRICT** — `src/mtg_kernel` and `src/mtg_cards`. Dynamic code loading and process
  execution are forbidden.
- **SUPPORT** — `src/mtg_verify` and `src/mtg_sources`. Dynamic code loading is still
  forbidden. Process execution is permitted only through the exact file-and-call allowlist
  recorded by the scanner; the current allowlist is limited to the verifier's reviewed
  `subprocess.run` and `subprocess.check_output` calls.

Explanatory docstrings may name `legacy/mtg_sim`; executable literals may not.

**Does not cover.** `sys.modules` lookups, `getattr` on a module object, names assembled at
runtime from arithmetic or decoding, C extensions, or behavior reached through a
third-party package's own dynamic loading. The set of ways one Python module can reach
another is unbounded. Assurance therefore still depends primarily on the structural wheel
boundary and the test-session audit hook.

## `tests/conftest.py` (audit hook)

**Covers.** Any import of `mtg_sim` or a submodule, from anywhere in the process,
including imports written inside function bodies. Any read of a file under `artifacts/`
or `legacy/` that is not under an allowlisted root.

**Does not cover.** Reads performed by a subprocess — the hook is per-interpreter, and a
subprocess gets a fresh one. Data already loaded into memory before the hook installs.
Network reads. Writes are not audited, only reads, because the concern is contamination
of clean results by legacy input.

## `scripts/check_identity_lock.py`

**Covers.** Any change to `IDENTITY_MODEL_V2.0.0.md`, because the expected digest is a
constant in the script rather than a value read from the approval record. It also checks
the approval record, frozen status, approval statement, blob identity, and cited commit.
The repository variable `IDENTITY_MODEL_V2_SHA256` is the external anchor.

**Does not cover.** Whether the named approver actually approved anything; the approval
record is not a cryptographic signature. Changing the identity model requires a new
version and approval process.

## `scripts/check_phase_a_authority.py`

**Covers.** ACTIVE_BINDING files exist; required archival files exist; forbidden active
paths are absent; no file is both active and archival; the frozen evidence-label set is
intact; and the Phase A contract documents cross-reference the authority map.

**Does not cover.** Whether an arbitrary result artifact actually carries an acceptable
evidence label. The standing Phase A verifier and durable certification record cover the
specific accepted production result; this authority-map check remains a classification
and cross-reference gate.

## Standing Phase A verifier

`mtg-engine verify-phase-a` runs on every pull request and every push to `main`. It reruns
the production-path acceptance suite, identity and authority gates, boundary check,
requirement mapping, source hashes, replay/hash result, and pilot lock.

**Does not cover.** The uploaded artifact is retained for 90 days and is therefore not a
permanent repository record. Durability is provided separately by the certification gate.

## Durable Phase A certification

`scripts/check_phase_a_certification.py` requires
`docs/audit/phase-a-certification/CERTIFICATION.json` to match path-and-content digests of
the complete certified surface. The surface includes the engine, cards, verifier, source
validator, Phase A acceptance suite, audit hook, negative gate tests, mapping, critical
certification and boundary scripts, packaging, CI workflow, and frozen Oracle inventory.
Path names are hashed, so a rename is a change.

The authoritative record must be produced by GitHub Actions and must contain a valid run
ID, run URL, result-artifact name, clean-tree assertion, passing counts, all blocking
requirements, source hashes, evidence classification, legacy-evidence prohibition, and
pilot lock. Local reproduction cannot create the authoritative record.

**Does not cover.** A single-owner repository cannot obtain independent human approval
from itself. A sufficiently privileged owner could change the checker, recorder, covered
path list, tests, and certification together. The covered-surface digest makes such a
change visible and forces recertification, while protected-branch CI prevents accidental
or partial weakening; it is not a substitute for an independent signer.

## The channel no gate covers

None of the above prevents the highest-likelihood contamination: **transcription**.
An agent reading `legacy/mtg_sim` and hand-writing equivalent logic into `mtg_kernel`
produces no import and can pass linkage-oriented checks. Available mitigations are
review-time source citations, golden transcripts, and similarity reports that are advisory
rather than merge-blocking.

Treat all-green gates as evidence that the declared production path, linkage, sources,
identity contract, and certified content are consistent. They do not prove authorship or
eliminate every possible semantic defect.

## CODEOWNERS and protected-branch rules

`CODEOWNERS` is ownership metadata only. This single-owner repository cannot require an
independent approving reviewer without deadlocking normal work. The practical controls are
required pull requests, required CI, blocked force pushes and deletions, the external
identity digest anchor, standing Phase A verification, and durable content certification.
