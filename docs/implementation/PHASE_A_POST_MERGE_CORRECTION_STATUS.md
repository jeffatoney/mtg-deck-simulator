# Phase A Post-Merge Correction Status

**Status:** IMPLEMENTATION COMPLETE — EXACT-HEAD VALIDATION PENDING

**Branch:** `agent/phase-a-post-merge-corrections`

## Implemented corrections

1. Non-mana activated abilities require the activating player to hold priority; mana abilities retain their rules exception.
2. Stack resolution is entered only by the completed all-player priority-pass transition.
3. State-based actions and waiting-trigger placement are deferred until the current spell or ability finishes resolving.
4. Phase A PASS now depends on five exact, digest-bound, owner-approved golden transcripts.
5. Commit removes the pending action associated with a spell or spell copy that it removes from the stack.

## Evidence status

- Focused behavioral and golden-transcript tests passed in the corrective publication workflow.
- The five exact golden transcripts and their owner approval record are committed.
- Complete exact-head CI, renewed immutable Phase A verification, and durable certification remain pending on the current head.
- Review and explicit owner merge authorization remain required after all automated gates pass.

## Locks

The 500/200 pilot, policy discovery, and full study remain locked. Frozen identity V2.0.0 files were not edited.
