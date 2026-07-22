# ADR-0014: Complete rerun requirements after a repeated audit error

## Status

Accepted for Phase 2 interface design.

## Context

The simulator must measure deterministic table-win access for the frozen Malcolm and Breeches deck under the repository specifications. Phase 2 defines architecture only; it does not implement engine behavior or run simulations.

## Decision

A repeated audit error requires quarantine, regression test, engine correction, competency suite rerun, and complete pilot rerun with new run ID.

## Consequences

- Partial patching or selective rerun cannot support reported percentages.
- Implementations that violate this decision must fail tests or gates before pilot execution.
- Run reports must cite the module, test ID, and artifact proving compliance.
