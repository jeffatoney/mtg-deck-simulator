# ADR-0010: Bounded exploratory search without actual-future information

## Status

Accepted for Phase 2 interface design.

## Context

The simulator must measure deterministic table-win access for the frozen Malcolm and Breeches deck under the repository specifications. Phase 2 defines architecture only; it does not implement engine behavior or run simulations.

## Decision

Exploratory search expands legal actions from Observations and samples unknown draws from belief-state streams, never actual future library order.

## Consequences

- Search can discover lines while preserving legal information boundaries.
- Implementations that violate this decision must fail tests or gates before pilot execution.
- Run reports must cite the module, test ID, and artifact proving compliance.
