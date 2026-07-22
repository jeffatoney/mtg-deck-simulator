# ADR-0011: Independent replay and invariant validation

## Status

Accepted for Phase 2 interface design.

## Context

The simulator must measure deterministic table-win access for the frozen Malcolm and Breeches deck under the repository specifications. Phase 2 defines architecture only; it does not implement engine behavior or run simulations.

## Decision

Audit replay consumes events/results and checks invariants without calling policy decision code.

## Consequences

- Separates producing results from validating legality, conservation, and terminal-state behavior.
- Implementations that violate this decision must fail tests or gates before pilot execution.
- Run reports must cite the module, test ID, and artifact proving compliance.
