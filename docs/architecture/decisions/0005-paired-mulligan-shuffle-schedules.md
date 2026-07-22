# ADR-0005: Paired mulligan shuffle schedules

## Status

Accepted for Phase 2 interface design.

## Context

The simulator must measure deterministic table-win access for the frozen Malcolm and Breeches deck under the repository specifications. Phase 2 defines architecture only; it does not implement engine behavior or run simulations.

## Decision

Precompute per-round random-key shuffle schedules keyed by base seed and mulligan round.

## Consequences

- Policies that reach the same mulligan decision consume the same shuffle process; divergence is measurable.
- Implementations that violate this decision must fail tests or gates before pilot execution.
- Run reports must cite the module, test ID, and artifact proving compliance.
