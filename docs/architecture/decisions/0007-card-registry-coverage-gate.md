# ADR-0007: Card implementation registry and coverage gate

## Status

Accepted for Phase 2 interface design.

## Context

The simulator must measure deterministic table-win access for the frozen Malcolm and Breeches deck under the repository specifications. Phase 2 defines architecture only; it does not implement engine behavior or run simulations.

## Decision

Every deck and commander card must have a registry entry with coverage status, reviewed handler, source references, and tests.

## Consequences

- No generic no-op fallback is allowed; blocked or missing coverage prevents pilots.
- Implementations that violate this decision must fail tests or gates before pilot execution.
- Run reports must cite the module, test ID, and artifact proving compliance.
