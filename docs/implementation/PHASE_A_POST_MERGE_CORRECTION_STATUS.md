# Phase A Post-Merge Correction Status

**Status:** EXACT SOL RING TRANSCRIPT CORRECTION IN PROGRESS

**Branch:** `agent/phase-a-post-merge-corrections`

## Implemented corrections

1. Activated abilities require a legal activation window; standalone mana abilities cannot be activated while another player holds priority.
2. Stack resolution is entered only by the completed all-player priority-pass transition; callers cannot supply an authorization flag.
3. State-based actions and waiting-trigger placement are deferred until the current spell or ability finishes resolving.
4. Phase A PASS depends on five exact, digest-bound, owner-approved golden transcripts.
5. Commit removes the pending action associated with a spell or spell copy that it removes from the stack.
6. Waiting triggers are not put on the stack after a direct-damage terminal event.
7. The golden-transcript approval document is anchored to the exact repository-owner-approved canonical digest and owner identity.

## Final review correction

The approved `priority-gated-sol-ring-resolution` transcript must execute the exact Sol Ring scenario rather than an analogous Opt scenario. Its named Phase A test is being corrected to cast Sol Ring, reject direct and replay resolution bypasses, resolve only after all players pass, create a fresh Sol Ring permanent, retire the spell object, and clear the cast action from `pending_actions`.

## Evidence status

- Earlier behavioral, governance, exact-head CI, artifact, and durable-certification gates passed before this final transcript correction.
- Complete exact-head CI, renewed immutable Phase A verification, durable certification, and another exact-head Codex review remain required after the Sol Ring test lands.
- Explicit owner merge authorization remains required after all automated and review gates pass.

## Locks

The 500/200 pilot, policy discovery, and full study remain locked. Frozen identity V2.0.0 files were not edited.
