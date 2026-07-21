## Exploratory Play and Nonstandard Win-Search Branch

Divide the 25,000 baseline simulations into two separately reported groups:

* **20,000 standard-policy simulations:** Follow the fixed pilot logic exactly.
* **5,000 exploratory simulations:** Use the same deck, shuffle rules, mulligan rules, mana rules, and Turn 8 limit, but allow structured searches for legal, nonstandard winning approaches.

Do not combine the exploratory results with the standard-policy percentages. Report them as a separate discovery analysis so experimental decisions do not distort the primary consistency measurements.

### Purpose of the Exploratory Branch

The exploratory branch should search for legal winning or takeover sequences that are not limited to the predefined primary combo packages.

It may investigate:

* Unusual combinations among cards already in the deck
* Alternate uses of tutors
* Sequencing that changes the effective mana requirement
* Using copied, bounced, phased, discarded, or flashed-back cards in unexpected ways
* Lines involving Breeches, Malcolm, Treasure production, Pirate damage, or card-copy effects
* Winning sequences that combine parts of two known packages
* Non-infinite sequences that still produce lethal damage by Turn 8
* Board-control sequences that create a near-certain winning position
* Cards that function as substitute combo pieces under a specific board state
* Unusual uses of opponents’ permanents only when those permanents are explicitly defined by the simulation

Do not assume access to unspecified cards from opponents’ decks. Breeches cards from unknown libraries may not be used to establish a deterministic line.

### Exploration Method

For each exploratory game:

1. Follow the normal league mulligan policy unless an alternate keep is being deliberately tested.
2. Generate all legal candidate actions available during each main phase, combat step, and relevant stack window.
3. Look ahead through multiple turns when computationally practical.
4. Compare candidate lines based on:

   * Earliest legal table elimination
   * Highest deterministic damage
   * Most cards or mana generated
   * Strongest recoverable board position
   * Number of independent future win paths created
   * Lowest exposure to a single removal effect
5. Allow the exploratory pilot to choose a slower line when it creates a substantially stronger Turn 6 through Turn 8 position.
6. Save the seed and complete action sequence whenever the exploratory policy finds a result the standard policy did not find.

### Search Boundaries

The exploratory branch must not:

* Add cards that are not in the exact decklist
* Change card text
* Ignore colored mana requirements
* Ignore timing restrictions
* Treat conditional loops as deterministic
* Assume opponents make favorable choices
* Assume Malcolm dealt damage when combat damage was prevented
* Assume Glint-Horn can activate when it is not attacking
* Count copied spells as cast spells
* Use one tutor to provide multiple cards simultaneously
* Treat Breeches as access to a specific opponent card unless that card was explicitly modeled
* Treat access to a combo as a win when the sequence cannot legally eliminate all opponents
* Describe a line as new to Magic, unprecedented, or undiscovered without independent verification

### Additional Exploratory Safeguards

#### No Future-Information Advantage

The exploratory pilot may use only information legally available at the moment of each decision.

It may not:

* Examine future draws
* Examine the order of the shuffled library
* Select actions based on future random events
* Use knowledge of a future board wipe, interaction event, or denied attack
* Choose a line because the simulator already knows which cards will be drawn later
* Use hidden information from an opponent’s hand, library, or face-down cards

When searching future game states, the exploratory pilot must treat unknown draws and random events as unknown. It may evaluate possible outcomes, but it may not select the current action using the actual future result assigned to that seed.

#### No Post-Result Optimization

The simulator may not repeatedly replay a failed seed with different decisions and report only the best result.

When branching or look-ahead search is used, record:

* The number of branches searched
* The maximum search depth
* Any limit on legal actions considered
* The evaluation method used to compare branches
* Whether the selected line used only information legally available at the decision point
* Whether all compared branches were evaluated under the same unknown-information assumptions

If the simulator searches several legal decisions, it must apply the same search procedure to every eligible exploratory game. It may not perform additional searches only after seeing that a particular game failed.

The report must distinguish between:

* The result produced by the first selected exploratory policy
* The best result found by a bounded branching search
* A result found only through later manual replay

Do not combine these categories.

#### Actionability Threshold

Do not recommend a discovered line for normal play unless it meets at least one of the following standards:

* It is found in at least 20 independent simulations
* It is intentionally accessible through tutors already in the deck
* It is reproducible from a clearly defined and reasonably common game state

A line found through an existing tutor must still be:

* Legal
* Mana-feasible
* Strategically preferable in a defined situation
* Reproducible without future information
* Independent of unspecified opponent resources

A line based on a common game state must clearly define that state, including:

* Cards required in hand
* Permanents required on the battlefield
* Available mana and colors
* Relevant cards in the graveyard or exile zone
* Number of opponents
* Combat or timing requirements
* Whether a commander must already be in play

Rare legal lines may still be reported, but they must be labeled as **low-frequency curiosities**, not practical strategy.

Do not recommend changing the deck, mulligan policy, tutor priorities, or normal play pattern based only on a low-frequency curiosity.

### Candidate-Line Discovery

When an unfamiliar sequence appears:

1. Save the exact game seed.
2. Save the battlefield, hand, graveyard, exile zone, library size, available mana, and number of opponents.
3. Record every action and trigger in order.
4. Replay the sequence using a stricter rules-validation routine.
5. Confirm:

   * Every target is legal
   * Every mana payment is legal
   * All timing restrictions are followed
   * Trigger ordering is valid
   * Required creatures can attack or tap
   * The loop remains sustainable as opponents are eliminated
   * The player does not draw from an empty library
   * The sequence actually produces lethal damage or a deterministic win
   * The pilot did not use future or hidden information
   * The sequence was not selected through post-result optimization
6. Reject the candidate if any part of the line depends on:

   * An unspecified opponent card
   * A favorable opponent decision
   * An illegal shortcut
   * Knowledge of a future draw
   * Knowledge of a future interaction event
   * Repeated seed replay that was not part of the defined search method

### Classification of Exploratory Findings

Classify each validated finding as one of the following:

* **Known-line variation:** A different route into an already defined combo
* **Hybrid line:** Uses pieces from two or more established packages
* **Tutor innovation:** A less obvious tutor target or tutor sequence
* **Mana innovation:** A sequencing change that accelerates a known line
* **Recovery line:** Produces a win after a primary package becomes unavailable
* **Conditional table kill:** Wins only with a defined number of opponents or board state
* **Value takeover:** Does not immediately win but creates a dominant measurable position
* **Candidate new interaction:** A legal card interaction not included in the original package definitions
* **Low-frequency curiosity:** A validated but rare line that does not meet the actionability threshold

Use “candidate new interaction,” not “new combo,” until the line has been independently rules-checked and compared with established combo databases or known deck resources.

### Noncombo Takeover Criteria

A line may be classified as a value takeover only when it produces at least one measurable result by Turn 8:

* At least six additional cards accessed
* At least eight net mana or Treasures generated beyond normal land production
* Removal of at least three significant opposing permanents while retaining a functional board
* Two independent deterministic win paths available for the next turn
* A board position that presents lethal damage to all opponents on the following turn
* A repeatable engine that continues without requiring an unknown opponent card

Do not count an ordinary favorable board as a takeover.

When reporting a value takeover, specify:

* The exact measurable threshold reached
* The cards responsible
* Whether the position depends on combat
* Whether the position survives a routine board wipe
* Whether the result depends on unknown opponent cards
* Whether the state was reached using the standard or alternative mulligan policy

### Exploratory Mulligan Analysis

In addition to using the standard keep policy, test a limited alternative policy in no more than half of the exploratory simulations.

The alternative policy may retain hands containing:

* Strong card-selection density without a predefined combo
* Unusual tutor combinations
* Breeches plus multiple reliable Pirate-damage sources
* Multiple cards that create a possible hybrid line
* A high-value interaction engine that the standard policy normally rejects

Report these experimental keeps separately.

Do not use them to revise the standard mulligan recommendation unless they:

* Outperform the standard policy across a sufficiently large paired sample
* Use the same shuffle seeds as the standard-policy comparison
* Do not rely on future-information advantage
* Produce a repeatable improvement rather than isolated successful outcomes
* Meet the actionability threshold

### Required Exploratory Reporting

Provide:

1. Number of exploratory simulations
2. Number that found a win missed by the standard pilot
3. Number that found an earlier win than the standard pilot
4. Number that found a stronger second-line recovery
5. Number of candidate interactions rejected during rules validation
6. Every validated nonstandard line found at least five times
7. Every line that meets the 20-simulation actionability threshold
8. Rare validated lines found fewer than five times, clearly labeled as low-sample findings
9. Validated lines found between five and nineteen times, clearly labeled as conditional or developing findings
10. Cards most frequently involved in unexpected successful sequences
11. Tutor targets that performed better than their conventional target in defined situations
12. Experimental opening hands that outperformed the standard mulligan policy
13. Full decoded replays for the ten most strategically useful findings
14. A separate list of apparent discoveries that failed validation and the rule that invalidated each one
15. Number of branches searched in each exploratory decision method
16. Maximum search depth
17. Number of findings rejected for using future information
18. Number of findings rejected as post-result optimization
19. Which findings are practical strategy and which are low-frequency curiosities

### Paired Comparison

Whenever possible, run the standard and exploratory policies on the same seeds.

For every seed where the results differ, record:

* Standard-policy result
* Exploratory-policy result
* First point where their decisions diverged
* Information legally available at that decision point
* Cards involved
* Change in win turn
* Whether the exploratory line remained protected
* Whether the result depended on a narrow or unlikely condition
* Number of branches searched
* Whether the line was selected before future draws were revealed
* Whether the result meets the actionability threshold

This paired comparison is the primary method for determining whether the exploratory policy found a genuinely useful line rather than benefiting from:

* A different random draw
* Future-information advantage
* A favorable hidden event
* Repeated post-result replay
* Selective reporting of only successful branches

### Final Interpretation

Keep the conclusions separated into:

* Reliable standard-policy tendencies
* Validated exploratory improvements that meet the actionability threshold
* Tutor-accessible conditional lines
* Common-state recovery or hybrid lines
* Conditional or low-frequency discoveries
* Low-frequency curiosities
* Rejected apparent combinations
* Findings affected by future-information concerns
* Findings affected by branching or post-result optimization
* Questions requiring human tabletop testing

Do not recommend changing the deck or mulligan policy based on a single unusual simulation.

A nonstandard line should be considered strategically actionable only when:

* It is legal
* It occurs repeatedly, is intentionally tutor-accessible, or arises from a reasonably common defined state
* It improves the result compared with the standard policy
* Its setup requirements can be clearly explained
* It does not depend on hidden or unspecified opponent resources
* It does not use future information
* It was not selected through unreported post-result optimization
* It meets the actionability threshold

Rare legal lines that do not meet these standards may still be documented, but they must be presented as low-frequency curiosities rather than normal play recommendations.
