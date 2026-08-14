# Phase C Exploratory V2 Diagnostic

Classification: **NON_AUTHORIZED_DIAGNOSTIC**

This directory documents the implementation-validation workflow for the three exploratory V2 arms. It does not contain, authorize, or stand in for a new pilot. The historical Phase C pilot remains unchanged.

The workflow `.github/workflows/phase-c-exploratory-v2-diagnostic.yml` runs the repository integrity gates, the unchanged STANDARD regression controls, targeted V2 tests, and then each exploratory arm separately using predetermined diagnostic environment and exploration seeds. Each diagnostic game requires clean-engine execution, transcript replay, fresh-process policy recomputation, complete candidate evidence, baseline retention, and land-development compliance.

Arm outputs are written only under `artifacts/phase-c-exploratory-v2-diagnostic/<arm-id>/` and are uploaded as three distinct `NON_AUTHORIZED_DIAGNOSTIC-*` workflow artifacts. There is intentionally no pooled win/access aggregate.

`DIAGNOSTIC_SUMMARY.md` is updated only from an executed diagnostic workflow. Until that workflow passes, no technical gate is represented as passed.
