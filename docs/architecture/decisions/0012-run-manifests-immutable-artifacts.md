# ADR-0012: Run manifests and immutable artifacts

## Status

Accepted for Phase 2 interface design.

## Context

The simulator must measure deterministic table-win access for the frozen Malcolm and Breeches deck under the repository specifications. Phase 2 defines architecture only; it does not implement engine behavior or run simulations.

## Decision

Each run directory is content-addressed by manifest metadata; raw artifacts are append-only and failed runs are quarantined.

## Consequences

- Supports reproducibility and prevents fabricated or overwritten results.
- Implementations that violate this decision must fail tests or gates before pilot execution.
- Run reports must cite the module, test ID, and artifact proving compliance.
