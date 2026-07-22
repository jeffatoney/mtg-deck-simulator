# ADR-0013: Sharding and deterministic aggregation

## Status

Accepted for Phase 2 interface design.

## Context

The simulator must measure deterministic table-win access for the frozen Malcolm and Breeches deck under the repository specifications. Phase 2 defines architecture only; it does not implement engine behavior or run simulations.

## Decision

Shards receive explicit seed ranges and named stream IDs; aggregation rejects mixed commits/configs/sources, duplicates, and gaps.

## Consequences

- Parallel execution cannot change outcomes or denominators.
- Implementations that violate this decision must fail tests or gates before pilot execution.
- Run reports must cite the module, test ID, and artifact proving compliance.
