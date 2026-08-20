# Phase C Glint-Horn Action Surface Diagnosis

**Date:** 2026-08-16 (America/Los_Angeles)  
**Branch:** `hardening/public-policy-noninterference`  
**Diagnostic source commit:** `ae61c12b7b78ac0da3eddc75616a45d815435747`  
**Diagnostic source tree:** `66c5883d7c93412fb02e3d238b47bf064f685391`  
**Diagnostic source parent:** `1927942f45d2a001bac8b10852800a4f85380660`  
**Classification:** `BROKER_COST_CHOICE_ENUMERATION_DEFECT`

The commit and tree above identify the exact Stage-1 source and test state on which this diagnosis was produced. The later evidence-publication commit is intentionally not self-referential; completion is established by GitHub read-back at the publication SHA and by `docs/audit/EVIDENCE_INDEX.json`.

## Executive finding

The production executor accepts Glint-Horn Buccaneer's `glint-horn:loot` activation when the source is attacking, P0 has priority, `{1}{R}` is payable, and an explicit legal discard object ID is supplied. In the same legal public state, the production broker does not expose a Glint-Horn `ACTIVATE` action.

The broker's battlefield activation enumeration supplies effect-choice variants. `DRAW` produces an empty choice mapping. It does not enumerate the non-mana discard cost choice, so the executor probe receives no `discard_ids` and rejects the probe with:

`activation requires explicit discard-cost choices`

The defect is therefore in production legal-action generation, not in the executor rule for this activation.

This diagnosis does **not** establish that every historical access-tracker witness was production-valid. The supported historical statement remains:

> The access tracker reported Malcolm/Glint-Horn access, while the corresponding Glint-Horn activation did not appear in the recorded production legal-action surface.

It is not supported to say that the policy had a legal deterministic table win and declined it.

## Raw evidence revalidation

Archive:

`docs/audit/phase-c-postpilot/evidence/pr100-corrected-behavior-971f5567.zip`

SHA-256:

`7e314f859d1e774b232f1d3daeed146441553e8f31c9aa0615a428d37a8aad8a`

The bounded independent CI scan opened the committed ZIP and recomputed counts directly from each member's `decisions` array. It did not use the Markdown behavioral report or JSON summary counts for these values.

| Member | Source commit | Source tree | Decisions | Glint-Horn candidates | Glint-Horn ACTIVATE candidates | Selected Glint-Horn casts | Glint-Horn attacking turns |
|---|---|---|---:|---:|---:|---:|---|
| `legacy-101.json` | `971f5567f47eb6f753a96a5809f72b5e9e23a404` | `002ee839864905fc4f3052776b72def6c9e86473` | 140 | 6 | 0 | 1 | 10 |
| `legacy-391730338978874520.json` | `971f5567f47eb6f753a96a5809f72b5e9e23a404` | `002ee839864905fc4f3052776b72def6c9e86473` | 363 | 2 | 0 | 1 | 6, 7, 8, 9, 10 |
| `repaired-101.json` | `971f5567f47eb6f753a96a5809f72b5e9e23a404` | `002ee839864905fc4f3052776b72def6c9e86473` | 154 | 0 | 0 | 0 | none |
| `repaired-391730338978874520.json` | `971f5567f47eb6f753a96a5809f72b5e9e23a404` | `002ee839864905fc4f3052776b72def6c9e86473` | 220 | 1 | 0 | 1 | 5, 6, 7, 8, 9, 10 |

Totals:

- Member count: 4
- Decisions: 877
- Seed-391 decisions: 583
- Glint-Horn candidate entries of any action kind: 9
- Glint-Horn `ACTIVATE` candidates: 0
- Selected Glint-Horn casts: 3
- Glint-Horn attacking turns across all four traces: 12
- Glint-Horn attacking turns across the two seed-391 traces: 11

Raw member SHA-256 values:

- `legacy-101.json`: `0c115d4c22b75395340ed2c7e3c9448ceb5d1f31baad8fd3635efe1f9d99b550`
- `legacy-391730338978874520.json`: `3140412e6d5a50a2eb6eead54e071e6168ac2dde2bad4cb0b2638c6259b5862f`
- `repaired-101.json`: `1658b0a76d3f35b4d3bac7cfe05d5d1277de2651fa2feb0e5809f3466e488d68`
- `repaired-391730338978874520.json`: `6db8c5bfe21a28a64924471e49be9feab2412936acb059add7ac6f6e1c61c5cd`

### Legacy long-seed Turn 6, decisions 63 through 71

| Decision | Phase / step | Selected public action |
|---:|---|---|
| 63 | PRECOMBAT_MAIN / PRECOMBAT_MAIN | Cast Glint-Horn Buccaneer |
| 64 | PRECOMBAT_MAIN / PRECOMBAT_MAIN | Pass priority |
| 65 | PRECOMBAT_MAIN / PRECOMBAT_MAIN | Pass priority |
| 66 | COMBAT / DECLARE_ATTACKERS | Declare Glint-Horn Buccaneer, Malcolm, Keen-Eyed Navigator, and Siren Stormtamer as attackers |
| 67 | COMBAT / DECLARE_ATTACKERS | Pass priority |
| 68 | COMBAT / DECLARE_BLOCKERS | Pass priority |
| 69 | COMBAT / COMBAT_DAMAGE | Pass priority |
| 70 | COMBAT / COMBAT_DAMAGE | Activate Treasure for black mana |
| 71 | COMBAT / COMBAT_DAMAGE | Pass priority |

No Glint-Horn activation appears in this sequence.

## Oracle and Magic rules authority

The frozen Oracle text for Glint-Horn Buccaneer includes:

`{1}{R}, Discard a card: Draw a card. Activate only if Glint-Horn Buccaneer is attacking.`

The exact card specification uses ability ID `glint-horn:loot`, effect `DRAW`, mana cost `{1}{R}`, discard count 1, and restriction `SOURCE_ATTACKING`.

The frozen Comprehensive Rules source has SHA-256:

`e99cd70eb64ca854acb6420ebbf06e369e3f258e0cfba4f03f70bd881386f79b`

Relevant authority includes rules 602.1, 602.2, 602.3, 602.5d, 601.2h, 118.1, 118.3, 508.1n, and 508.2. Together they support the arranged positive state: the activated ability can be activated while Glint-Horn is attacking, after attackers are declared when P0 has priority, provided the mana and discard costs are payable.

## Direct executor result

Arranged production state:

- P0 controls Glint-Horn Buccaneer on the battlefield.
- Glint-Horn is attacking.
- P0 has priority in combat after attackers are declared.
- P0's mana pool contains exactly one red and one colorless mana for the `{1}{R}` cost.
- P0 has exactly one otherwise legal discardable card in hand.
- The game is active.
- No unrelated pending choice blocks the activation.

The production executor was called with ability `glint-horn:loot`, no targets, and the exact one-card `discard_ids` choice.

Command:

`uv run pytest -q tests/phase_b/test_glint_horn_action_surface.py::test_direct_executor_accepts_legal_glint_horn_loot_activation -vv`

Result: **PASS, 1 passed.**

The transition records:

- `ACTIVATE` with `ability_id = glint-horn:loot`;
- cost `{GENERIC: 1, R: 1}`;
- mana payment `{R: 1, C: 1}`;
- the discard moving from hand to graveyard;
- a `CARD_DISCARDED` event; and
- the mandatory `glint-horn:discard` trigger.

There is no executor rejection in the legal positive case.

A second direct test calls the executor with the broker-shaped empty choice mapping in the otherwise identical legal state. It passes by proving the expected rejection:

`activation requires explicit discard-cost choices`

## Broker result

Command:

`uv run pytest -q tests/phase_b/test_glint_horn_action_surface.py::test_broker_exposes_and_executes_legal_glint_horn_loot_activation -vv`

Result: **EXPECTED REGRESSION.**

The broker's production legal-action set contained no action with all of:

- action kind `ACTIVATE`;
- public identity `Glint-Horn Buccaneer`;
- public metadata ability ID `glint-horn:loot`.

Because no such broker action existed, there was no broker-selected handle to resolve through the executor.

The exact missing internal executor argument is `choices.discard_ids`. The battlefield broker enumerates effect choices, and the `DRAW` effect contributes `{}`. It does not add the required discard-cost choice before probing the executor.

The discard object ID is hidden hand information. A future repair must bind the exact private discard choice for execution and replay without placing the hidden object ID in the public action key or public metadata. With exactly one discardable card in the test state, no arbitrary strategic discard preference is needed to prove action availability.

## Negative controls

The same production legality surface was used for all controls.

| Control | Broker activation | Direct executor | Result |
|---|---|---|---|
| Glint-Horn not attacking | absent | rejects | PASS |
| P0 lacks `{1}{R}` | absent | rejects | PASS |
| P0 has no discardable card | absent | rejects | PASS |
| P0 does not have priority | absent | rejects | PASS |

Negative-control command:

`uv run pytest -q tests/phase_b/test_glint_horn_action_surface.py -k 'omits or isolated_negative' -vv`

Result: **PASS, 5 passed, 3 deselected.**

The complete focused module command:

`uv run pytest -q tests/phase_b/test_glint_horn_action_surface.py -vv`

Result: **EXPECTED REGRESSION, 1 failed and 7 passed.** The sole failure is the positive broker-availability assertion.

## Scope inventory

The exact deck's activated abilities with non-mana discard-style additional costs include:

- Ash Barrens basic-landcycling, hand-zone discard-self cost
- Dizzy Spell transmute, hand-zone discard-self cost
- Drift of Phantasms transmute, hand-zone discard-self cost
- Glint-Horn Buccaneer `glint-horn:loot`, battlefield discard-one-card cost
- Muddle the Mixture transmute, hand-zone discard-self cost
- Rebuild cycling, hand-zone discard-self cost
- Step Through wizardcycling, hand-zone discard-self cost
- Vedalken Aethermage wizardcycling, hand-zone discard-self cost

Within the exact deck, Glint-Horn is the battlefield activated discard-cost case. The mechanism is structurally broader than this card: any battlefield activated ability that requires an explicit discard choice would reach the same incomplete battlefield enumeration path unless it has separate handling.

No additional card was repaired in Stage 1.

## Attempt semantics review

The Phase C written measurement authorities require an `actual_first_attempt_turn` and package reporting, but they do not define whether an attempt begins with:

- casting the final permanent;
- selecting the first action in an executable witness;
- activating the combo engine; or
- another event.

The production implementation is more specific. When the current access snapshot says the package is `legally_executable`, `_GameMeasurementCapture.observe_selected_action` records an attempt when `_action_commits_to_package` returns true. For Malcolm/Glint-Horn, declaring Glint-Horn as an attacker counts, and a non-pass action whose public identity is a package piece also counts. Therefore, **casting Glint-Horn alone can count as an attempt when the access snapshot already marks the package legally executable.**

That implementation behavior is consistent with the legacy seed-101 record where the Turn-10 package-completing action is the Glint-Horn cast even though no Glint-Horn activation appears later in the trace.

The written specification does not clearly adopt or reject that boundary. Classification for this part is therefore **AMBIGUOUS_WRITTEN_SPEC**, and an owner methodology decision is required. Stage 1 does not change attempt semantics.

## Standing access property

Stage 1 does not impose a same-decision requirement that the final combo activation be visible during precombat main.

The standing property is sequential:

Every reported access result must contain or be reproducible as a finite production-valid witness. The first action must be in the production legal-action set at the reported state. After each witness action executes through the production executor, the next witness action must appear in the resulting legal-action set. The sequence must reach the metric's defined success condition without hidden information, favorable opponent assumptions, alternate legality, or a measurement-only shortcut.

For Malcolm/Glint-Horn, the witness may legitimately include casting a component, resolving it, moving to combat, declaring Glint-Horn as an attacker, receiving priority, activating `glint-horn:loot` with payable mana and an explicit discard, and continuing through production legality.

## Classification

**`BROKER_COST_CHOICE_ENUMERATION_DEFECT`**

Basis:

1. The direct production executor accepts the Oracle- and rules-legal activation when supplied the required explicit discard object ID.
2. The production broker omits the same activation from the legal-action set in the same legal public state.
3. A direct executor call shaped like the broker probe, with `choices={}`, is rejected specifically because explicit discard-cost choices are absent.
4. All four negative controls remain correctly unavailable.

This Stage-1 result does not require an executor rule repair.

## Historical metric consequence and dated erratum

**Dated erratum: 2026-08-16**

Historical artifacts and percentages remain unchanged.

The production action surface could not expose at least one required Malcolm/Glint-Horn combo activation even though the production executor supports that rules-legal activation when given the required discard choice. Therefore actual-attempt, never-attempted, package-attempt, combo-resolution, and terminal behavior may be affected.

The population magnitude is unmeasured. No population inference is made from the two frozen seeds.

Stage 1 does not prove that every historical access-tracker witness was production-valid, so it does not separately conclude that the historical 16.4% Turn-8 or 22.6% Turn-10 access figures were overcounted. Those historical figures remain attached to the prior measurement implementation and are not rewritten here.

## Recommended next repair boundary

The next implementation stage should change only the production battlefield activated-ability cost-choice enumeration needed to construct explicit non-mana cost choices, beginning with `discard_ids`.

That repair must:

1. construct the required private discard-cost choice before the production executor probe;
2. preserve the public-information boundary by keeping hidden hand object IDs out of the public semantic action key and public metadata;
3. bind the exact private choice needed for deterministic execution and replay;
4. retain the direct positive and all negative regression tests; and
5. revalidate any claimed Malcolm/Glint-Horn access as a stepwise production-valid witness before any corrected-pilot authorization.

The next stage must **not** change, absent separate evidence:

- executor activation rules;
- `combo_access.py`;
- attempt detection;
- STANDARD scoring;
- canonical public ordering;
- land-development logic;
- combo priority;
- witness-search behavior;
- terminal regressions; or
- historical pilot artifacts.

No substantive repair is implemented by this Stage-1 diagnosis.

## Validation

Dedicated Stage-1 diagnostic workflow run: `31992473444`

Normal PR CI on the same diagnostic source head: `31992475694`

Exact Stage-1 commands and results:

- `uv run pytest -q tests/phase_b/test_glint_horn_action_surface.py::test_direct_executor_accepts_legal_glint_horn_loot_activation -vv`  
  PASS: 1 passed.
- `uv run pytest -q tests/phase_b/test_glint_horn_action_surface.py::test_broker_exposes_and_executes_legal_glint_horn_loot_activation -vv`  
  EXPECTED FAIL: no matching broker activation.
- `uv run pytest -q tests/phase_b/test_glint_horn_action_surface.py -k 'omits or isolated_negative' -vv`  
  PASS: 5 passed, 3 deselected.
- `uv run pytest -q tests/phase_b/test_glint_horn_action_surface.py -vv`  
  EXPECTED REGRESSION: 1 failed, 7 passed.
- `uv run pytest -q tests/phase_b/transcripts/test_pb_t06_glint_curiosity.py`  
  PASS: 1 passed.
- `uv run ruff format --check --diff .`  
  PASS: 234 files already formatted.
- `uv run ruff check .`  
  PASS: all checks passed.
- `uv run python scripts/check_repository_evidence.py`  
  PASS: repository evidence integrity.
- `uv run pytest -q tests/test_repository_evidence_gate.py`  
  PASS: 7 passed.
- `uv run pytest -q tests/phase_b/test_policy_information_boundary.py`  
  PASS: 4 passed.
- `uv run python scripts/check_policy_information_boundary.py`  
  PASS: policy ranking remains handle-free and opaque action handles remain confined to execution/post-selection resolution.

The focused existing Glint-Horn transcript also passed: 1 passed.

No full-pytest pass is claimed. No new certification candidate is claimed as a Stage-1 deliverable.

## Governance

- Corrected pilot authorized: **false**
- Replacement 500/200 pilot authorized: **false**
- Full study authorized: **false**
- Historical pilot artifacts modified: **false**
- PR #100 certified: **false**
- PR #100 ready for review: **false**
- PR #100 merged: **false**
- PR #99 modified or integrated: **false**

Stage 1 stops at this classification. No substantive broker, executor, measurement, scoring, ordering, witness-search, or pilot-execution repair is included.
