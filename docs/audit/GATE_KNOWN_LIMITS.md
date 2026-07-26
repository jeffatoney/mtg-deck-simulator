# Gate v2 known limits and stopping rule

The AST scanner is defense in depth, not a claim of completeness against
arbitrary syntax obfuscation. New static-only limitations are recorded here
unless they defeat an authoritative boundary: the physical production-pilot
lock, protected-main referee provenance, closed-world staging, runtime imports,
causal liveness, frozen scenarios, or golden-replay semantics. A defeat of an
authoritative boundary is a blocking defect and must not be documented away.

## Required Phase A recovery checks

- `Control Plane / immutable-referee`
- `Architecture / static-invariants`
- `Acceptance / isolated-reference-suite`
- `Production Pilot / locked`
- `CI / checks`

Ordinary green CI alone is not a GO decision.

## Setup bootstrap audit record

PR #31 (`recovery/phase-a-setup`) creates the protected-main examiner, so that
examiner cannot be authoritative while PR #31 is still unmerged. The three
future recovery jobs are therefore branch-gated and expected to skip on the
setup PR: `immutable-referee`, `invariants`, and `isolated-reference-suite`.
PR #31 is instead audited by ordinary CI, the Production Pilot Lock, and the
committed setup/control-plane regression tests.

Once PR #31 merges, the protected-main workflow and scripts are authoritative
for the `recovery/phase-a-rules-kernel` pull request into `main`. Their frozen
definitions are compared against the candidate as part of `immutable-referee`;
there is no candidate-owned runner fallback. A skipped future-kernel acceptance
job on PR #31 is expected bootstrap behavior. A failed job is not a pass and
must not be summarized as one.
