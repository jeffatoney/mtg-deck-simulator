# Repository Handoff Protocol

## Purpose

Current project state must come from the repository and GitHub machine state, not from chat memory.
The handoff is therefore generated from the exact `main` commit after CI completes and published to a
machine-owned branch.

## Canonical handoff

- Repository: `jeffatoney/mtg-deck-simulator`
- Machine-owned branch: `handoff/current`
- Human-readable record: `docs/audit/handoff/CURRENT_HANDOFF.md`
- Machine-readable record: `docs/audit/handoff/CURRENT_HANDOFF.json`
- Generator: `scripts/generate_current_handoff.py`
- Publisher: `.github/workflows/regenerate-handoff.yml`

The generated files must not be hand edited. The `handoff/current` branch may be force-updated by the
publisher because it is a derived audit branch, not a development branch.

## Authority order

When sources disagree, use this order:

1. GitHub repository and Actions machine state for the exact current commit.
2. Machine-readable governance, certification, and frozen study files in the repository.
3. The generated handoff, after independently verifying its subject commit is still current.
4. Owner decisions recorded in the designated GitHub issue or other frozen decision record.
5. PR descriptions and comments as explanatory evidence.
6. Chat summaries and manually written status prose only as historical context.

A chat summary never overrides current repository state.

## Generation model

The `Regenerate Repository Handoff` workflow runs after the `CI` workflow completes on `main` and may
also be dispatched manually. It checks out the exact CI subject SHA and generates the handoff from:

- Git commit and tree identity;
- Phase C pilot configuration and approval state;
- Phase A and Phase B durable certification records;
- SHA-256 digests of the frozen Phase C binding files;
- open pull requests and their exact heads;
- owner-review issue #51 and its latest comments; and
- GitHub Actions runs associated with the subject commit.

The workflow then recreates `handoff/current` from the exact subject commit and adds only the generated
handoff files. This avoids a self-referential commit problem: the record describes `main`, while the
machine-owned handoff branch is a one-commit derived view of that state.

If a required source is missing, governance state is internally inconsistent, or GitHub state cannot be
read when repository generation is required, generation must fail instead of filling the gap from memory.

## Independent-auditor requirements

An independent reviewer must begin by refreshing the repository rather than trusting the previous chat.
Before recommending work, the reviewer must verify:

- current `main` commit and tree;
- relevant open PR numbers, bases, exact heads, draft/merge state, and conflicts;
- exact-head CI results and any stale certification gates;
- Phase A and Phase B certification provenance and currentness;
- Phase C governance locks, including `execution_allowed`;
- frozen configuration, workflow, seed/pairing, evaluator, and policy bindings relevant to the decision;
- the latest non-authorized diagnostic evidence when diagnostic status matters; and
- owner decisions recorded in issue #51 or the designated successor record.

The reviewer must distinguish repository-verified facts, CI/artifact evidence, owner-approved policy or
study decisions, implementation inferences, and recommendations.

A successful test suite is not a substitute for a current durable certification. Certification renewals
must come only from the exact CI-produced candidate for the exact reviewed content and must not be hand
edited.

When policy behavior depends on a study assumption, the implementation must bind to the machine-readable
configuration rather than silently hardcoding the assumption.

Rules corrections and strategic-policy decisions must remain separate. Legal Magic actions must not be
made illegal merely to make a simulation pass. STANDARD must remain the authorized non-searching baseline,
and EXPLORATORY must retain only its authorized search behavior.

For every claimed diagnostic correction, verify permanent regression coverage. Representative seeds are
regression evidence; they are not a substitute for the complete acceptance diagnostic.

Before recommending another 700-seed diagnostic or any pilot execution, verify that prerequisite PRs are
merged, exact-head CI is green, affected certifications are current, the generated handoff describes the
current `main`, and governance remains in the expected locked state.

At the end of an independent audit, state:

1. the exact repository state verified;
2. whether the generated handoff was current or stale;
3. blockers or contradictions;
4. the single next permitted work stage; and
5. whether a human owner decision is required.

If repository state changes during the audit, refresh it before issuing the final verdict.

## Machine-state reconciliation checklist

A planned action is not complete because it was attempted or intended. Before any status prose
claims completion, the reviewer must read back the resulting machine state and reconcile it to
the exact subject state.

Required read-back evidence by claim:

- **PR merged:** read the PR after the merge operation and verify its merged state, merge commit,
  and expected head.
- **Exact `main` identified:** read the branch ref and the referenced commit; record the exact
  commit SHA and tree SHA.
- **CI green:** read the completed workflow run; record workflow run ID, conclusion, and exact
  head SHA. A run for a different SHA is not evidence.
- **Certification current:** read the durable certification record and its exact checker result;
  verify its certified content commit/tree and covered-content digest against the subject state.
- **Handoff current:** read the generated handoff after publication and verify its subject SHA/tree
  against current `main`.
- **Diagnostic completed:** read the completed workflow run and its produced summary/artifacts;
  verify run ID, head/implementation SHA, counts, replay status, error set, and prohibited pilot
  artifact count.
- **Audit completed:** read the committed audit record from GitHub and verify it names the exact
  audited SHA/tree and supporting run/artifact identities.
- **Report created:** read the committed report back from GitHub and verify its repository path,
  content, and digest.
- **Owner package ready:** reconcile every cited SHA, tree, workflow run, certification, diagnostic,
  handoff, and report to the same final repository state before presenting it.

For every claimed file artifact, record and verify the exact path, existence, a byte count greater
than zero, and a SHA-256 digest where practical. For GitHub state, record the exact commit SHA,
exact tree SHA when relevant, workflow run ID and head SHA for workflow claims, and the PR merged
state when claiming a merge.

Narrative state must never outrun machine state. If a read-back differs from the expected SHA,
status, artifact, digest, or count, the action remains incomplete until reconciled.

## Authorization boundary

The handoff is evidence only. It cannot authorize the 500 STANDARD / 200 paired EXPLORATORY pilot, cannot
create an activation commit, and cannot authorize the 20,000 / 5,000 full study. Those remain separate
owner decisions under the existing governance controls.

## Legacy status prose

`PROJECT_STATUS.md` is no longer a mutable handoff or dashboard. It points to this protocol and the
generated handoff so stale manually maintained SHAs and CI counts cannot be mistaken for current state.
