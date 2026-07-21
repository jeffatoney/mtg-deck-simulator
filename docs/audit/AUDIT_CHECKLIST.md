# Manual decoded-game audit checklist

For each audited game, record PASS/FAIL/NOT APPLICABLE and cite the event numbers.

- Opening library and mulligan shuffle schedule match the manifest
- Keep decision used only visible hand information
- Refill cards were unseen at keep time
- One legal land play per turn
- Enter-tapped, reveal, bounce, fetch, filter, and chosen-color land rules
- Mana source, color, amount, restrictions, and payment timing
- Commander tax and command-zone choices
- Spell and ability timing
- Targets legal when selected and on resolution
- Costs paid before triggers are put on the stack
- Stack order and trigger order
- State-based actions checked at correct times and not during resolution
- Combat declaration legal; attackers not summoning sick unless they have haste
- Malcolm counts unique damaged opponents for each damage event
- Glint-Horn attacking restriction and finite-resource sequence
- Copied spells not counted as cast
- Tutor target legal and tutor consumed once
- No hidden library order or future event exposed to policy
- Unknown Breeches cards excluded
- Conditional line not labeled deterministic
- Game stops immediately at terminal state
- Checkpoint metrics match decoded state
- No materially better legal action was obviously available under the policy's frozen objective

A repeated failure pattern is systemic even if the overall pass percentage is high. Add a regression test and rerun the entire pilot.
