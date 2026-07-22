# ADR-0004: Named deterministic random-number streams

## Status

Accepted for Phase 2 interface design.

## Context

The simulator must measure deterministic table-win access for the frozen Malcolm and Breeches deck under the repository specifications. Phase 2 defines architecture only; it does not implement engine behavior or run simulations.

## Decision

ScenarioSeed derives named streams for library shuffles, mulligan schedules, search samples, tie-breaks, sharding, and audits.

## Consequences

- Worker count and unrelated feature additions must not perturb existing streams.
- Implementations that violate this decision must fail tests or gates before pilot execution.
- Run reports must cite the module, test ID, and artifact proving compliance.
