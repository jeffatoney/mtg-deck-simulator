# Phase A Post-Merge Correction Status

**Status:** EXACT-HEAD VALIDATION AND RECERTIFICATION PENDING

**Branch:** `agent/phase-a-post-merge-corrections`

## Implemented corrections

1. Activated abilities require a legal activation window; standalone mana abilities cannot be activated while another player holds priority.
2. Stack resolution is entered only by the completed all-player priority-pass transition; callers cannot supply an authorization flag.
3. State-based actions and waiting-trigger placement are deferred until the current spell or ability finishes resolving.
4. Phase A PASS depends on five exact, digest-bound, owner-approved golden transcripts.
5. Commit removes the pending action associated with a spell or spell copy that it removes from the stack.
6. Waiting triggers are not put on the stack after a direct-damage terminal event.
7. The golden-transcript approval document is anchored to the exact repository-owner-approved canonical digest and owner identity.
8. The approved `priority-gated-sol-ring-resolution` transcript is bound to a test that executes the exact Sol Ring scenario: direct and replay resolution bypasses are rejected; resolution occurs only after all active players pass; the spell object retires; a fresh Sol Ring permanent enters the battlefield; and the cast action leaves `pending_actions`.

## Evidence status

- The exact Sol Ring transcript test and golden-transcript checker passed in the publication workflow.
- Complete exact-head CI, renewed immutable Phase A verification, durable certification, and another exact-head Codex review remain required on the current head.
- Explicit owner merge authorization remains required after all automated and review gates pass.

## Locks

The 500/200 pilot, policy discovery, and full study remain locked. Frozen identity V2.0.0 files were not edited.
