# ADR-0001: Deck-scoped fail-closed engine versus a general Magic engine

## Status

Accepted for Phase 2 interface design.

## Context

The simulator must measure deterministic table-win access for the frozen Malcolm and Breeches deck under the repository specifications. Phase 2 defines architecture only; it does not implement engine behavior or run simulations.

## Decision

Build only the Malcolm/Breeches deck-scoped engine. Any unsupported card, ambiguous rule, or unmodeled state is fatal.

## Consequences

- A general engine would encourage broad silent defaults; deck-scoped coverage supports source traceability and hard failure.
- Implementations that violate this decision must fail tests or gates before pilot execution.
- Run reports must cite the module, test ID, and artifact proving compliance.
