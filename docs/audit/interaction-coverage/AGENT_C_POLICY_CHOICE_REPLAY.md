# Agent C — Policy + Choice + Replay Conformance

**Status:** STACKED_CANDIDATE

**Base:** the coordinator interaction-coverage branch. This lane does not advance any interaction record to `PROVEN` until the coordinator surface is frozen and its nonzero manifest SHA matches the generated surface.

## Scope

Agent C is a fail-closed conformance lane for rules-defined strategic decisions. It does not change card behavior to make games pass and it does not execute an authorized Phase C pilot.

The lane verifies four links:

1. every strategic choice purpose in the coordinator interaction surface has an explicit production route;
2. every runtime `CardSelectionRequest` purpose has a production policy handler;
3. returned selections are constrained by engine-created legal candidates or legal sets; and
4. replay consumes recorded decisions and revalidates them instead of rerunning strategic policy.

The machine-readable routing contract is `automation/strategic-choice-conformance.json`. The audit is `scripts/audit_policy_choice_replay_conformance.py`.

## Purpose completeness

The audit builds the coordinator interaction surface and inspects every choice whose `policy_class` requires an actor or strategic policy. A `(timing, purpose)` pair is blocking until it has a reviewed route in the Agent C registry.

Separately, the audit walks all production Python under `src/` with the AST and inventories every `CardSelectionRequest` purpose. Literal purposes and stable prefix forms such as `TRIGGER_TARGET:*` are supported. A dynamically constructed purpose that cannot be reduced to a stable auditable pattern is blocking rather than accepted as an implicit default.

A runtime purpose must appear in both:

- the production policy implementation; and
- the Agent C runtime-purpose registry.

Unknown purposes therefore fail before a random game has to discover them.

## Policy-provider coverage

The audit verifies method parity between:

- `StrategicChoiceProvider`;
- the production `PolicyStrategicChoiceProvider`; and
- `RecordedStrategicChoiceProvider`.

It also verifies that the package-level production binding exports the trigger-aware provider rather than the older base provider.

Canonical interaction choices use one of the reviewed mechanisms recorded in the registry, including broker-selected legal actions, injected strategic choice providers, or explicit production-runner decisions. A choice with no reviewed route is reported as `interaction choice has no reviewed policy/replay route`.

## Legality boundary

Policy may choose only from candidate sets already established by the engine. Agent C locks the current legality boundaries, including:

- trigger targets: engine `_legal_candidates` -> opaque policy candidates -> explicit returned-handle membership/count validation -> normal engine trigger-target validation;
- spell-copy retargeting: legal target sets are produced by the engine and provider output must equal one of those sets;
- cleanup discard: returned opaque handles are checked against the exact hand candidate map and required count;
- tutor, Fact or Fiction, and replay selections: recorded selections are checked against the request's current eligible identities, legal splits, candidates, and counts; and
- broker actions: candidates are production-probed rather than assumed legal from policy metadata.

Removing any locked legality check causes the Agent C source-invariant tests to fail.

## Exact replay

Replay must not rerun strategic policy. The lane verifies that every `StrategicChoiceProvider` method has a corresponding `RecordedStrategicChoiceProvider` method and that recorded choices are legality-checked during replay.

It also locks the production replay boundary:

- replay creates the production `GameExecutor` with `RecordedStrategicChoiceProvider`;
- recorded commands are executed through the production engine; and
- the reconstructed transcript must equal the expected transcript exactly.

Some decisions, such as Phase C cleanup discard identity, are persisted as explicit production command arguments rather than as a `CARD_SELECTION` choice record. The routing registry names that distinction instead of treating all decisions as if they shared one replay format.

## Why this catches the trigger-target failure

The coordinator surface classifies a mandatory triggered target as `TARGET_SELECTION` at `TRIGGER_STACKING`. Agent C derives every effect kind that reaches that choice and independently derives the effect kinds supported by `mtg_policy.trigger_choices`.

If a targeted trigger exists in the surface but lacks production policy support, the audit fails with:

`triggered target effect requires a policy provider but is unsupported`

The lane also requires the explicit kernel bridge, returned-handle legality validation, `CARD_SELECTION` recording, replay purpose equality, replay handle/count legality, and the production trigger-aware binding. The pre-fix state that produced `IllegalAction: explicit trigger target choice is required` would therefore have failed Agent C before a 700-seed or pilot run encountered the seed.

## Fail-closed findings

Agent C intentionally distinguishes an implementation gap from an audit success. Examples that remain blocking until verified include a rules-defined choice with no route, a choice made at a different timing than the coordinator contract, a policy result that is not revalidated against legal candidates, a new strategic provider method without replay support, or an unknown runtime purpose.

The audit may therefore be red while the coordinator surface is still being completed. That is a diagnostic result, not permission to change card behavior merely to make the check green.

## Commands

Candidate-surface diagnostic:

```bash
python scripts/audit_policy_choice_replay_conformance.py --output agent-c-conformance.json
```

After the coordinator is frozen, certification can additionally require the frozen surface identity:

```bash
python scripts/audit_policy_choice_replay_conformance.py \
  --require-frozen-surface \
  --output agent-c-conformance.json
```

Focused structural tests:

```bash
pytest -q tests/interaction_coverage/test_policy_choice_replay_conformance.py
```

The GitHub workflow always uploads `agent-c-conformance.json`, including on an audit failure, so distinct gaps can be reviewed without converting them into card-behavior patches.
