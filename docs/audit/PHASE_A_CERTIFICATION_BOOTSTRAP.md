# Phase A certification closeout bootstrap

This branch intentionally begins without `docs/audit/phase-a-certification/CERTIFICATION.json`.

The standing CI workflow first reruns the Phase A production verifier and generates a
CI-only certification candidate outside the repository tree. The durable-record check then
fails closed because no candidate has yet been committed. The candidate artifact is copied
into the repository, after which the same CI workflow must pass without exceptions.

This bootstrap note is not part of the certification content surface and may be removed
once the durable record is committed.
