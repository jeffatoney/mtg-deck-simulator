# Repository Evidence Preservation Policy

## Purpose

A repository deliverable must be a durable, verifiable repository object. Chat text, a local working file, a GitHub Actions workspace file, an expiring Actions artifact, generated source text, or a script that could create a report is not a committed report.

This policy closes the recurring failure mode in which work was described as saved or complete even though the claimed report bytes were not present in the repository.

## Completion vocabulary

The words **saved**, **committed**, **published**, **durable**, and **complete** may be used for a repository report or artifact only after all of the following are true:

1. The final exact Git commit SHA is identified.
2. The claimed path exists in the repository tree at that SHA.
3. The actual file bytes are fetched or otherwise content-address verified from GitHub at that SHA.
4. The file is nonempty when its format requires content and parses in its native format.
5. Its SHA-256 digest matches the durable repository evidence index.
6. Any load-bearing source evidence required to reproduce or audit the report is itself committed or content-addressed by an immutable durable source.

A generated-but-uncommitted file is **provisional**. An Actions artifact that has not been copied into durable repository evidence is **ephemeral evidence**. Neither may be described as a repository deliverable.

## Evidence index

`docs/audit/EVIDENCE_INDEX.json` is the standing catalog for durable audit evidence.

Every file under a tracked evidence root must be listed in the index. Each indexed entry records at least:

- repository-relative path,
- artifact kind,
- byte size,
- SHA-256 digest.

Raw ZIP evidence additionally records the exact member set, member sizes and digests, source commit/tree, selector, seed, and diagnostic status.

The index does not hash itself to avoid a recursive digest dependency.

Standing CI runs:

`uv run python scripts/check_repository_evidence.py`

The check fails closed if an indexed artifact is missing, changed without an index update, empty, malformed, inconsistent with its raw evidence, or if a tracked evidence file is present but unindexed.

## No self-manufactured certification evidence

Committed tooling must not generate or overwrite the contents of a certification-covered gate, regression test, assertion, authority map, test map, certification record, or expected value from the same observed run output that the generated content is supposed to check.

In particular:

- Investigation output may produce diagnostic data and draft analysis.
- It may not turn the observed result into a regression expectation and then claim that expectation independently validates the result.
- If a covered expected value must change, the change is a human-authored, reviewable diff that states what changed, why the prior expectation is no longer authoritative, and which independent authority supports the new expectation.
- Investigation scaffolding is removed before a branch is proposed for certification.
- A test or gate that remains intentionally red because methodology is unresolved must stay red until the owner decision or authority chain resolves the expected behavior.

This prohibition applies even if the generated assertion would be deterministic.

## Investigation scaffolding

PR-scoped diagnostic and source-mutation mechanisms are temporary. Before certification, the repository must not retain:

- `.github/diagnostics/**`,
- PR-numbered workflows such as `.github/workflows/pr123-*.yml`,
- PR-numbered source-mutating scripts such as `scripts/pr123_*.py`,
- explicitly identified one-off diagnostic workflows recorded by the evidence gate.

The permanent evidence gate checks these final-tree constraints. Temporary investigation branches may be red while scaffolding exists; certification may not proceed until cleanup is complete.

## Raw evidence preservation

Load-bearing quantitative claims must retain the raw evidence needed to audit them.

When GitHub Actions produces the source evidence:

1. Record the workflow run ID, artifact ID, source commit, and source tree.
2. Verify the downloaded archive digest against GitHub's artifact digest when GitHub supplies one.
3. Record each archive member's digest and identity.
4. Commit the exact archive bytes or another approved immutable equivalent before the ephemeral artifact expires.
5. Derive human-readable reports from those preserved bytes, not from chat summaries.

Historical pilot artifacts remain immutable. A new audit record supplements them; it does not rewrite them.

## Reporting rule

Every implementation completion report must distinguish:

- **repository-verified:** fetched/content-addressed at the stated Git SHA;
- **ephemeral evidence:** exists only in Actions or another temporary store;
- **local/provisional:** generated locally but not committed;
- **reported only:** stated in chat without durable evidence.

If repository verification has not happened, the response must say so explicitly.

## Governance

This policy is an evidence-integrity guardrail. It does not authorize a pilot, a corrected pilot, a full study, a methodology change, certification, merge, or readiness transition.
