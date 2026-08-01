# Phase A Post-Merge Correction Status

**Status:** ALL GOLDEN TRANSCRIPT EXACTNESS HARDENING IN PROGRESS

**Branch:** `agent/phase-a-post-merge-corrections`

## Implemented corrections

1. Activated abilities require a legal activation window; standalone mana abilities cannot be activated while another player holds priority.
2. Stack resolution is entered only by the completed all-player priority-pass transition; callers cannot supply an authorization flag.
3. State-based actions and waiting-trigger placement are deferred until the current spell or ability finishes resolving.
4. Phase A PASS depends on five exact, digest-bound, owner-approved golden transcripts.
5. Commit removes the pending action associated with a spell or spell copy that it removes from the stack.
6. Waiting triggers are not put on the stack after a direct-damage terminal event.
7. The golden-transcript approval document is anchored to the exact repository-owner-approved canonical digest and owner identity.
8. The approved Sol Ring transcript executes its exact production-path scenario.

## Current hardening

The remaining approved transcript tests are being strengthened to assert their complete machine contracts:

- Commit: both removed and resolving actions leave `pending_actions`, the original Opt remains pending, the copy leaves the stack, and the second-from-top library placement is recorded before synthetic cessation.
- Glint-Horn Buccaneer: discard, trigger placement, damage, stack resolution, and game termination occur in the approved order.
- Dualcaster Mage: the ETB trigger targets the exact Opt object and the resulting spell-copy successor follows its exact cessation lifecycle.
- Twinflame: both hasty component-free token copies have matching delayed triggers and exact exile/cessation successors.

## Evidence status

Complete exact-head CI, renewed immutable Phase A verification, durable certification, and another exact-head Codex review remain required after this hardening lands. Explicit owner merge authorization remains required after every automated and review gate passes.

## Locks

The 500/200 pilot, policy discovery, and full study remain locked. Frozen identity V2.0.0 files were not edited.
