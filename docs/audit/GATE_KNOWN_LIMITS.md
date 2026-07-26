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
