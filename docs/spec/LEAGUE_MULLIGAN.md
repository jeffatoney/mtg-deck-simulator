# League mulligan override

This procedure replaces the normal Commander/London mulligan procedure. All other rules remain normal.

1. Draw an initial hand of seven cards.
2. The first mulligan returns and shuffles the rejected hand into the library, then draws seven cards.
3. Subsequent mulligans draw six, then five, then four cards.
4. The simulator never mulligans below four; a four-card hand is kept.
5. After a hand is kept, draw random cards from the remaining library until the hand contains seven cards.
6. Refill cards are unknown when the keep decision is made.
7. No cards are placed on the bottom as part of the London mulligan.
8. Every mulligan shuffle is driven by the trial's committed shuffle schedule so paired policies receive the same random process when they make the same mulligan decisions.
