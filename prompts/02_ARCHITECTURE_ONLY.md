Design the simulator architecture from the repository specifications. Do not implement the engine and do not run simulations.

Create architecture decision records covering:

- Deck-scoped fail-closed engine versus a general Magic engine
- Event-sourced game transitions and replay
- Hidden internal state versus policy-visible `Observation`
- Named deterministic RNG streams and paired mulligan shuffle schedules
- One shared legality validator for standard, exploratory, and replay paths
- Card implementation registry and coverage gate
- Composable policy configuration and discovery/validation separation
- Bounded exploratory search without actual-future access
- Independent replay and invariant validation
- Run manifests, sharding, immutable artifacts, and rerun policy

Also produce:

- Module/API diagram
- Data schemas for GameState, Observation, Action, Event, PolicyConfig, ScenarioSeed, RunManifest, and GameResult
- Exact phase gates from source freeze through full-study authorization
- Threat model for fabricated results, hidden-information leakage, selective replay, stale tests, and mixed-run aggregation

Update the traceability matrix. Do not move to implementation until every required behavior has an owning module and test ID.
