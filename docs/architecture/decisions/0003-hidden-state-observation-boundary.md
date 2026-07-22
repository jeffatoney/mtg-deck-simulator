# ADR-0003: Internal hidden state versus policy-visible Observation

## Status

Accepted for Phase 2 interface design.

## Context

The simulator must measure deterministic table-win access for the frozen Malcolm and Breeches deck under the repository specifications. Phase 2 defines architecture only; it does not implement engine behavior or run simulations.

## Decision

GameState may contain ordered hidden zones and executor RNG state; policies receive only Observation plus legal belief summaries.

## Consequences

- Prevents future-library leakage and makes policy decisions auditable.
- Implementations that violate this decision must fail tests or gates before pilot execution.
- Run reports must cite the module, test ID, and artifact proving compliance.
