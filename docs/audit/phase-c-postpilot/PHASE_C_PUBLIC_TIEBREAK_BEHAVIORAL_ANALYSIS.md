# Phase C Public Tie-Break Behavioral Analysis

Date: 2026-08-16

## Status and evidence boundary

This is a targeted, observation-only analysis of two frozen STANDARD seeds. It is not a pilot, pilot reanalysis, certification, replacement 500/200 run, or full study.

The load-bearing source is the exact GitHub Actions artifact produced for PR #100 source commit `971f5567f47eb6f753a96a5809f72b5e9e23a404` and tree `002ee839864905fc4f3052776b72def6c9e86473`:

- Workflow run: `31929887660`
- Artifact ID: `9259087740`
- Artifact name: `pr100-corrected-behavior-971f5567f47eb6f753a96a5809f72b5e9e23a404`
- Artifact SHA-256: `7e314f859d1e774b232f1d3daeed146441553e8f31c9aa0615a428d37a8aad8a`
- Durable repository copy: `docs/audit/phase-c-postpilot/evidence/pr100-corrected-behavior-971f5567.zip`

All four member JSON files report `PASS`, name the same source commit and tree, and report fresh replay equality.

PR #100 remains draft and uncertified. Issue #52 remains the owner decision gate.

## Exact targeted results

| Execution | Total decisions | No substantive tie | Equivalent-representative-only tie | Distinct-public-key tie | Historical/repaired public-key preference differs |
|---|---:|---:|---:|---:|---:|
| Seed 101, legacy selector | 140 | 95 | 5 | 40 (28.6%) | 27 |
| Seed 101, repaired selector | 154 | 106 | 16 | 32 (20.8%) | 20 |
| Seed 391730338978874520, legacy selector | 363 | 282 | 5 | 76 (20.9%) | 52 |
| Seed 391730338978874520, repaired selector | 220 | 157 | 0 | 63 (28.6%) | 46 |

These percentages describe only the four targeted traces. They are not estimates of the historical 500-game pilot or of the simulator as a population.

## Outcomes

### Seed 101

Legacy-selector execution:

- Status: `ACTIVE` through controlled Turn 10
- Commands: 458
- First actual attempt: Turn 10
- Package: `malcolm_glint_horn`
- Final state hash: `374521aa0be341545d4b843026673d5ef16407c3322c379a27b64fb3839882ea`

Repaired-selector execution:

- Status: `ACTIVE` through controlled Turn 10
- Commands: 529
- First actual attempt: `None`
- Final state hash: `f282b014606ead2931f9819709e0becd9995051b4146e9f28e33a92100c7914c`

### Seed 391730338978874520

Legacy-selector execution:

- Status: `TERMINAL` after controlled Turn 10
- Commands: 1081
- Final state hash: `bb048044fa84fd7e1cb672e823a3f97696b67fb3fa79a1f9995e9ece01f35c55`
- Final life totals: P0 40, P1 0, P2 0, P3 0
- P1, P2, and P3 loss reason: `LIFE_TOTAL`
- Malcolm/Glint-Horn earliest legal access field: Turn 6

Repaired-selector execution:

- Status: `ACTIVE` through controlled Turn 10
- Commands: 733
- Final state hash: `c7befd46b2593322c77b67c4fa555e032ea4fdea5ccf037c158ee58f92b1b618`
- Malcolm/Glint-Horn earliest legal access field: Turn 5

## Selector divergences

The diagnostic computes both selector preferences at each observed state. The two selector modes are also executed separately, so a cross-run causal statement is valid only when the compared executions have the same pre-decision state and public observation.

### Seed 101

At decision 0, both executions choose the same **public** `PLAY_LAND Island` key, but the legacy and repaired paths resolve different opaque representatives of two otherwise equivalent Island actions. The resulting full-state and public-observation digests diverge after that point.

The first later point where the actual executions choose different **public action keys** is decision 9 on Turn 2. In each trace, the substantive prefix is `[1, 65, 0, 0, 0]`, and the per-state selector comparison prefers:

- Historical final ordering: activate Island for blue mana.
- Repaired public ordering: activate Mountain for red mana.

Because the separate executions are already in different internal/public-digest states by decision 9, this decision is evidence that the evaluator leaves the mana-color choice strategically unresolved, but it is **not** a matched-state cross-run causal isolation of the final seed-101 outcome.

### Seed 391730338978874520

The two executions remain equal in full pre-decision state and public observation through decision 9. At that matched state on Turn 2, the substantive prefix is `[1, 0, 0, -1, 0]`.

The tied top public actions include Siren Stormtamer and two public Opt variants. The historical final ordering prefers Opt with `scry_to_bottom=true`; the repaired public ordering prefers Siren Stormtamer. This is a matched-state selector divergence.

The later trajectories and final outcomes differ materially.

## What the current policy code establishes

At the analyzed source commit, STANDARD assigns broad value classes such as `+80` to `PLAY_LAND` and `+65` to mana abilities, then uses the canonical public action key as the final ordering element after the substantive score. This removes the opaque ActionBroker handle from strategic ranking.

Canonical public ordering is deterministic and hidden-information safe. It is not, by itself, a strategic reason to prefer Mountain over Island, Siren Stormtamer over Opt, one target over another, or one X value over another when the substantive score ties.

The targeted evidence therefore supports an `UNDER_SPECIFIED_STANDARD_SCORING` finding for the observed tie families.

## Independent Commander Rule 903.9a repair

The current branch also contains a separate engine repair for commander movement from graveyard or exile. Pending commander-return choices are now registered on the qualifying zone move using the successor object and stale pending entries are removed when the prior object moves.

That engine repair is independent of the methodology decision about how STANDARD should strategically rank otherwise tied public actions. The historical terminal regression test is intentionally **not** rewritten from the repaired selector's observed outcome.

## Corrections to prior chat-only claims

The preserved exact-head artifact does not support several claims previously repeated in chat:

1. **`23 of 78` and `113 of 170`: not reproduced.** Those ratios are not the exact counts in the four preserved runs. The table above is authoritative for this targeted artifact.
2. **Island/Mountain/Shivan Reef together at `[1, 80, 0, 0, 0]`: not reproduced.** The artifact contains 25 decisions whose top prefix is `[1, 80, 0, 0, 0]`, but an exhaustive scan of all four traces finds no top tied set containing all three cards.
3. **“Terminal on Turn 6”: incorrect.** Turn 6 is the legacy-selector Malcolm/Glint-Horn earliest-legal-access field. The preserved execution completes controlled Turn 10 and is terminal at the reported final outcome.
4. **Niv-Mizzet identity:** the preserved trace identifies `Niv-Mizzet, the Firemind`, not Niv-Mizzet, Parun.

These corrections are the reason the raw evidence is committed beside this report rather than leaving the findings dependent on a chat transcript.

## Classification

Overall classification: **MIXED**.

Supported:

- The public action boundary removes the opaque execution handle from STANDARD's final strategic ordering.
- The selected final ordering is load-bearing on both frozen diagnostic seeds.
- Strategically different public actions can tie under the substantive STANDARD score.
- The long-seed decision-9 divergence is matched-state evidence.
- The independent commander zone-transition defect has a general engine repair on the branch.

Not established:

- A population-wide tie frequency.
- How many historical 500-game pilot outcomes were affected.
- Whether the historical 16.4% Turn-8 figure was inflated, reduced, or unchanged.
- A strategically correct tie hierarchy for STANDARD.
- That the seed-101 decision-9 public-key divergence alone caused its changed final outcome.

## Owner decision required

A methodology decision remains required before PR #100 can be certified or a corrected pilot can be authorized.

The decision should be general rather than seed-specific: whether canonical public ordering is an accepted residual baseline, or whether STANDARD receives a documented public-semantic strategic hierarchy for otherwise tied actions.

No production scoring preference is introduced by this evidence-preservation work.

## Governance

- Corrected pilot authorized: `false`
- New small pilot authorized: `false`
- Replacement 500/200 pilot authorized: `false`
- Full study authorized: `false`
- Historical pilot artifacts modified: `false`
- PR #100 certified: `false`
- PR #100 ready for review: `false`
- PR #99 integrated: `false`
