# ADR-0006: One shared legality validator for standard policy, exploratory search, and replay

## Status

Accepted for Phase 2 interface design.

## Context

The simulator must measure deterministic table-win access for the frozen Malcolm and Breeches deck under the repository specifications. Phase 2 defines architecture only; it does not implement engine behavior or run simulations.

## Decision

All Action execution paths must call engine.validator before state mutation.

## Consequences

- Prevents bypasses in search or replay and makes legality defects regression-testable.
- Implementations that violate this decision must fail tests or gates before pilot execution.
- Run reports must cite the module, test ID, and artifact proving compliance.
