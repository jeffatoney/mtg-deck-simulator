# ADR-0002: Event-sourced game transitions and replay

## Status

Accepted for Phase 2 interface design.

## Context

The simulator must measure deterministic table-win access for the frozen Malcolm and Breeches deck under the repository specifications. Phase 2 defines architecture only; it does not implement engine behavior or run simulations.

## Decision

Every accepted transition emits ordered typed Events with before/after state hashes sufficient for independent replay.

## Consequences

- Replay can validate outcomes without policy reruns and preserves immutable audit evidence.
- Implementations that violate this decision must fail tests or gates before pilot execution.
- Run reports must cite the module, test ID, and artifact proving compliance.
