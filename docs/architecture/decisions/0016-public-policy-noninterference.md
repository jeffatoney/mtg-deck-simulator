# ADR 0016: Public-policy hidden-information noninterference

## Status

Accepted for Phase B hardening.

## Context

The legal-action broker exposes an `ObservedAction` with a revocable `handle` used only to execute an action that is legal in the current broker generation. That capability token is derived from the broker generation, enumeration position, operation, and a token for the complete engine state. It is therefore appropriate for execution binding but not for strategic ranking.

A deterministic replay can reproduce the same capability token when it reconstructs the same complete state. That property does not establish that the policy is independent of information intentionally excluded from its observation.

**Same-state determinism is not the same as hidden-information noninterference.**

Three properties must remain separate:

1. **Replay determinism:** the same recorded commands and RNG streams reconstruct the same rules execution.
2. **Fresh-process deterministic recomputation:** the same public inputs and frozen policy configuration recompute the same strategic decision in another process.
3. **Hidden-information noninterference:** changing only hidden state, while preserving the policy-visible observation and public legal-action semantics, cannot change the selected public strategic action.

## Decision

Strategic policy ranking operates on a handle-free `PolicyActionView` and selects a `PublicActionKey` equivalence class. The public key contains the complete policy-visible semantic action record: action kind, card or ability identity where exposed, mana value, public tags and classifications, target count, public target/source handles or semantics supplied by the broker, modes, public choices, cast permission, X value, attacker composition, commander/public-source status when present, and any other broker metadata that is part of the public action surface.

The public key rejects private object IDs, card-instance IDs, hidden-zone order, full-state hashes, hidden RNG state, private broker arguments, and other non-observation identity.

Opaque `ObservedAction.handle` values are execution capabilities, not policy features. Ranking, scoring, sorting, candidate eligibility, equivalence windows, and preference rules may not consume them. Only after a public class has been selected may the execution adapter resolve that class to one opaque handle and execute it.

Distinct public keys use a canonical deterministic total order over the public semantic record for the final tie resolution. Publicly identical candidates are one equivalence class. A public total order must not pretend to distinguish representatives that have the same complete public key.

For the supported rules surface, duplicate representatives are acceptable only when representative choice is execution-equivalent after public-handle renaming: normalized public successor state, legal public continuation, combo-access observations, evaluator/measurement-relevant results, and future public policy choices must remain the same. If a test demonstrates a difference, the broker must expose the missing publicly visible strategically relevant distinction in the public action key instead of resolving it with hidden identity or enumeration order.

## Enforcement

Static enforcement is provided by `scripts/check_policy_information_boundary.py`. It rejects strategic access to `ObservedAction.handle`, direct runner access to `ActionBroker._actions`, and `_InternalAction` outside broker implementation modules. It also requires the positive public-action boundary to remain present in STANDARD.

Dynamic tests cover both `opponent_interaction_modeled=true` and the pilot-relevant `opponent_interaction_modeled=false` branches, hidden-only library-order mutation, broker enumeration permutation, changed action capability handles, and a duplicate public action class with alternate representatives.

The duplicate-class test executes different representatives and requires equal normalized public successor observations, equal combo-access records, and equal next STANDARD public action selection.

The gate runs in normal CI, is mapped into Phase B hidden-information and policy requirements, and is part of the Phase B covered certification surface. Phase C diagnostic integrity must run the same gate before producing replacement diagnostic evidence.

## Consequences

- Existing non-tie STANDARD scores and preference classes are unchanged.
- Any strategic code that needs an opaque action handle must first select a public class and then use the execution adapter.
- A new private identity or broker argument cannot be added to policy-visible metadata without failing closed.
- A covered implementation change invalidates the prior durable Phase B certification and requires the normal CI-produced candidate and exact-byte certification promotion process.
- Historical Phase C pilot artifacts are not rewritten. Their information-boundary limitation is recorded separately in the post-pilot addendum.
