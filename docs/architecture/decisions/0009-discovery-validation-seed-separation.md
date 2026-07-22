# ADR-0009: Discovery-seed and validation-seed separation

## Status

Accepted for Phase 2 interface design.

## Context

The simulator must measure deterministic table-win access for the frozen Malcolm and Breeches deck under the repository specifications. Phase 2 defines architecture only; it does not implement engine behavior or run simulations.

## Decision

Seed splits are precommitted before policy results; discovery selects finalists and validation estimates held-out performance.

## Consequences

- Reduces post-result optimization and selective replay risk.
- Implementations that violate this decision must fail tests or gates before pilot execution.
- Run reports must cite the module, test ID, and artifact proving compliance.
