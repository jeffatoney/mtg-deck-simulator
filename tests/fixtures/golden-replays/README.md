# Golden transcript drafts

These fixtures are **draft-needs-human-review** expected-transition documents. They are
not evidence that a game ran and do not claim approval by an independent
reviewer. Before Phase A may merge, a separate human approval record must move
all five core transcripts through `rules-reviewed` to `independently-reviewed`.
That review must verify the complete ordered actions, priority passes, stack
objects, targets, mana payments, triggers, zone changes, state-based actions,
cleanup, external-ledger changes, and final state.

An authoritative transcript must also have a matching entry in
`automation/golden-replay-approvals.json` containing the fixture path, exact
SHA-256, reviewer, approval date, and approving commit. That manifest is
intentionally empty in this setup PR; no human review is implied.
