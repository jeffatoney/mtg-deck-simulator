# Phase B Execution Status

**Status:** SLICE 1 — EXACT DECK AND COVERAGE IN CI

**Branch:** `engine/phase-b-full-deck-policy`

**Base:** corrected Phase A on `main` at merge commit `b5743b54fa26e3e20c175fddb6401b390c828b8c`

This file is a progress tracker only. It does not create project authority or unlock pilot execution.

## Controls

- The owner-approved single-owner exception is active.
- Required pull request, required CI, conversation resolution, standing Phase A verification, and durable certification remain mandatory.
- Implementation enters as ordinary source commits in three reviewable slices.
- Opaque patch blobs and code-applying workflows are prohibited.
- Test counts alone are not completion evidence; Phase B requires digest-bound, owner-approved behavioral transcripts.

## Intended Phase B result

- migrate every exact deck card and both commanders to the clean Oracle-backed card layer;
- extend only the rules capabilities required by the exact deck and modeled environment;
- build the baseline and exploratory policy framework without future-information access;
- implement interaction scenarios, measurements, bounded exploratory search, and fresh-process replay;
- add at least 12 mandatory behavioral transcripts covering the high-risk cross-system scenarios;
- preserve standing Phase A verification and current durable Phase A certification;
- create a separate durable Phase B certification;
- keep the 500/200 pilot and 20,000/5,000 study locked.

## Progress

- [x] Create the Phase B branch and draft PR #37
- [x] Inventory binding Phase B specifications and implementation surfaces
- [x] Freeze the Phase B contract and initial acceptance mapping
- [x] Remove opaque patch transport and temporary workflows
- [x] Record the owner-approved single-owner exception
- [x] Merge corrected Phase A and its golden-transcript gate into the Phase B line
- [x] Publish Slice 1 exact-deck construction and reviewed coverage as ordinary source commits
- [ ] Complete Slice 1 CI, Phase A recertification, and review record
- [ ] Publish Slice 2 policy configuration and shared legal-action broker
- [ ] Complete Slice 2 CI and review record
- [ ] Publish Slice 3 bounded search, measurements, manifests, replay, transcripts, and verification
- [ ] Create Phase B verifier, immutable result artifact, and durable Phase B certification
- [ ] Renew durable Phase A certification after all final covered changes
- [ ] Independent technical review and final Phase B GO/NO-GO

## Review-derived corrections

- Phase A post-merge rules corrections are incorporated.
- Phase B acceptance now requires behavioral golden transcripts rather than relying on aggregate test counts.
- Phase A retains its precise certification surface; Phase B receives a separate certification instead of forcing unrelated policy/analytics changes to rewrite Phase A certification.
- The reported `id: null` transcript-summary issue was not reproduced on final corrected `main`; the validator emits `transcript_id` and remains under observation.

## Locked

- 500/200 pilot execution
- 20,000/5,000 full study
- Policy discovery or outcome evaluation during Phase B acceptance
- Legacy deletion or legacy workflow reactivation
- Changes to frozen identity V2.0.0 without a new version and owner approval
