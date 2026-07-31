# Phase A Post-Merge Correction Status

**Status:** FINAL REVIEW CORRECTIONS IN PROGRESS

**Branch:** `agent/phase-a-post-merge-corrections`

## Implemented corrections

1. Activated abilities require a legal activation window; standalone mana abilities cannot be activated while another player holds priority.
2. Stack resolution is entered only by the completed all-player priority-pass transition; callers cannot supply an authorization flag.
3. State-based actions and waiting-trigger placement are deferred until the current spell or ability finishes resolving.
4. Phase A PASS depends on five exact, digest-bound, owner-approved golden transcripts.
5. Commit removes the pending action associated with a spell or spell copy that it removes from the stack.

## Final review corrections

- Prevent waiting triggers from being put on the stack after a direct-damage terminal event.
- Anchor the golden-transcript approval document to the exact repository-owner-approved canonical digest and exact owner identity.

## Evidence status

- Earlier focused behavioral and golden-transcript tests passed.
- The five exact golden transcripts and their owner approval record are committed.
- Complete exact-head CI, renewed immutable Phase A verification, durable certification, and final Codex review remain required after the final review corrections land.
- Explicit owner merge authorization remains required after all automated and review gates pass.

## Locks

The 500/200 pilot, policy discovery, and full study remain locked. Frozen identity V2.0.0 files were not edited.
