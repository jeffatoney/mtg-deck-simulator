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

## Authorization boundary

The handoff is evidence only. It cannot authorize the 500 STANDARD / 200 paired EXPLORATORY pilot, cannot
create an activation commit, and cannot authorize the 20,000 / 5,000 full study. Those remain separate
owner decisions under the existing governance controls.

## Legacy status prose

`PROJECT_STATUS.md` is no longer a mutable handoff or dashboard. It points to this protocol and the
generated handoff so stale manually maintained SHAs and CI counts cannot be mistaken for current state.
