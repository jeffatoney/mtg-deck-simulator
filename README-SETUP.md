# Phase A recovery bootstrap

This bundle starts the optimized three-phase recovery:

1. Phase A — clean rules kernel and vertical slice
2. Phase B — complete 98-card migration and policy reconnection
3. Phase C — readiness audit and corrected 500/200 pilot

## What this setup changes

It adds only specifications, a static architecture gate, gate tests, the Phase A
Codex prompt, and the recovery roadmap. It does not modify the simulator engine
and does not run the pilot.

The original bundle was revised before use:

- no new dependency is required; configuration is JSON, not PyYAML
- the frozen file is the specification only, so Codex can add acceptance tests
- the new gate scans only the clean `mtg_kernel` and `mtg_cards` packages during
  Phase A, allowing the legacy engine to remain quarantined until Phase B
- the workflow runs only on the Phase A recovery branch
- the external-opponent boundary records public objects without building full
  opponent decks or hands

## Repository process

1. Merge the small setup pull request after ordinary CI passes.
2. Create `recovery/phase-a-rules-kernel` from the updated `main`.
3. Open one draft PR titled `Phase A: Clean rules kernel and vertical slice`.
4. In its Conversation box, comment:

   `@codex implement prompts/recovery/PHASE_A_KERNEL.md exactly. Work only on this branch and PR.`

5. Wait for Codex commits and CI.
6. Request `@codex review` only after the implementation and gates pass.
7. Do not merge with any current-head P1 or P2 finding.
8. Do not close or merge PR #29 until the Phase A draft PR exists; then close it
   as superseded without merging.

## User-only settings

After the setup PR is merged, open repository Settings → Branches or Rulesets and
add the following required checks for recovery branches when available:

- `CI / checks`
- `Architecture Invariant Gate / invariants`

Do not make the production Pilot Simulation workflow runnable during Phase A or
Phase B.

## Phase A bootstrap boundary

The setup PR on `recovery/phase-a-setup` introduces the protected-main referee
and closed-world reference runner. It cannot be examined by a protected-main
referee that does not exist on `main` until this setup PR merges. Consequently,
the recovery-only referee, static architecture gate, and isolated reference
suite are intentionally dormant on the setup branch. Ordinary CI, the physical
Production Pilot Lock, and the committed setup/control-plane tests validate the
setup PR itself.

After the setup merges, those protected-main checks become authoritative only
for a pull request from `recovery/phase-a-rules-kernel` into `main`. Candidate
copies of the referee scripts and workflows never replace the copies checked
out from protected `main`. An `isolated-reference-suite` skip on the setup PR is
expected; a failed future-kernel acceptance job is not equivalent to that
expected bootstrap skip.

## Control Plane Bootstrap Self-Test

Ordinary setup CI executes the real protected reference runner against a
temporary protected referee and minimal candidate. This proves collection,
execution, standard-library and pytest access, exact candidate-SHA recording,
unique artifacts, and exclusion of candidate-controlled packages and helpers.
Each protected layer must retain a malicious failing fixture, a minimal valid
passing fixture, and an end-to-end test; static inspection alone is not proof
that a workflow is installed.
