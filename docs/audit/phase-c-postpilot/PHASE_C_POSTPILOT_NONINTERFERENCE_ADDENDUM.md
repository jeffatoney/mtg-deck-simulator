# Phase C Post-Pilot Hidden-Information Noninterference Addendum

Date: 2026-08-15

## Status and scope

This addendum records a newly identified information-boundary limitation in the historical Phase C pilot implementation. It does not alter, replace, recompute, or reinterpret any historical pilot artifact bytes. It does not authorize a corrected pilot, a new small pilot, post-result reanalysis, or the 20,000 STANDARD / 5,000 EXPLORATORY full study.

Issue #52 remains the owner decision gate for any future study authorization.

## Historical implementation boundary

The historical pilot remains an exact, replay-valid record of implementation:

`150671a8e7a78e5fa14b6b3aca2308f6af647df3`

That implementation used the opaque `ActionBroker.handle` as the final STANDARD tie-break in both the interactive and no-opponent ranking branches. The capability handle is bound to the complete broker state and enumeration position, while the policy observation intentionally excludes hidden library order, private object identity, and future random outcomes.

The historical pilot did not include a standing hidden-information noninterference gate proving that hidden-only state changes could not alter a final tied STANDARD choice.

This is a limitation statement, not a numerical correction. The number of historical policy decisions that reached the final handle tie-break was not measured. The effect, if any, on Turn-5, Turn-6, Turn-8, Turn-10, actual-attempt, package, mulligan, or paired statistics was not measured. This addendum does **not** claim that hidden library order definitely changed any historical numerical result.

The correct statement is:

> The historical STANDARD policy contained an untested hidden-state-dependent final tie-break path. Its historical numerical effect, if any, is unknown.

Accordingly, the historical 16.4% Turn-8 result, the historical Turn-10 result, and the historical McNemar result are not revised by this addendum. Future results from the repaired public-policy implementation are results from a different STANDARD policy implementation and must not be presented as directly interchangeable with the historical pilot without an explicit comparison design.

## Determinism distinction

Replay validity does not close this limitation. A replay can deterministically reconstruct the same complete state and therefore the same capability handle. Fresh-process recomputation can likewise be deterministic for a fixed complete state. Neither property proves that a policy decision is invariant when only hidden state changes while the public observation and public legal-action semantics remain the same.

The repaired architecture therefore treats replay determinism, fresh-process deterministic recomputation, and hidden-information noninterference as separate requirements.

## Historical combo-kill field boundary

The historical `combo_kill_counts` field measures resolved terminal full-table kills. It is not the numerator for deterministic checkpoint access.

A zero resolved-terminal kill count does not contradict legal deterministic checkpoint access or actual-attempt counts. No terminal kill rate is inferred from that field. A future terminal-resolution study would require a separately reviewed measurement design and separate authorization.

## Artifact preservation

All historical pilot artifacts remain unchanged and continue to serve as provenance for the exact implementation that produced them. No historical pilot artifact is deleted, rewritten, relabeled in place, or replaced by this addendum.

The Phase C Exploratory V2 diagnostic artifacts produced at implementation `084240f7bc7c6db9b18eb86c991ddadfe914d3c8` also remain immutable historical evidence for that exact implementation. For final Exploratory V2 closeout they are classified `SUPERSEDED_FOR_FINAL_CLOSEOUT`; that classification does not mean their bytes are invalid or disposable.

## Authorization state

- Corrected pilot authorized: **FALSE**
- New small pilot authorized: **FALSE**
- Full study authorized: **FALSE**
- Historical artifacts modified: **FALSE**
- Technical policy hardening and non-authorized diagnostic validation permitted: **TRUE**, subject to the existing repository locks and certification gates
