# Open decisions and required explicit assumptions

Resolve or encode these before the pilot. They are game-state assumptions, not pilot priorities.

## 1. Exotic Orchard and Fellwar Stone

Their colored mana depends on lands opponents control. The baseline specifies no interaction but does not define opponent lands or color identities.

Recommended implementation:

- Add an `OpponentManaProfile` configuration.
- Provide at least two sensitivity profiles: `no_known_colors` and `blue_red_available`.
- Select and document one primary pilot profile before running.
- Never silently treat these cards as Command Tower.

## 2. Opponent choices required by cards

Fact or Fiction and any other opponent-choice effect need a deterministic policy. Recommended baseline: enumerate legal choices and select the choice that minimizes this deck's frozen evaluation function. Record the chosen partition and score.

## 3. Opponent battlefield scope

Define whether opponent mana-profile lands are actual targetable permanents or abstract mana metadata. Recommended baseline: abstract metadata only, so they do not create unspecified targets for removal or bounce.

## 4. Recovery after losing a first line

No opponent interaction means natural disruption is absent. Measure independent second-line availability in baseline. If true recovery is desired, create a separate scripted perturbation study and never combine it with baseline percentages.

## 5. Oracle snapshot

Choose a retrieval date and source, commit the exact card data, record a hash, and disable live card-text refresh during simulations. Any later refresh creates a new simulation version.

## 6. Policy-run counts

Policy discovery requires replaying candidate policies on the same base seeds. The canonical pilot remains 500 standard plus 200 exploratory games, but total executions will be larger. The dry run must print all counts before execution.
