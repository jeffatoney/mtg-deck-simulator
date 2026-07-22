# ADR-0008: Composable policy configuration

## Status

Accepted for Phase 2 interface design.

## Context

The simulator must measure deterministic table-win access for the frozen Malcolm and Breeches deck under the repository specifications. Phase 2 defines architecture only; it does not implement engine behavior or run simulations.

## Decision

Policies are versioned data bundles of named knobs, evaluators, and priority tables rather than ad hoc code edits.

## Consequences

- Candidate comparisons remain reproducible and can be frozen before discovery results.
- Implementations that violate this decision must fail tests or gates before pilot execution.
- Run reports must cite the module, test ID, and artifact proving compliance.
