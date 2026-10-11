# Coimbra GitHub Actions → Mac M4: post-merge pilot

**Status:** Stage 1 is a *hosted-only eligibility gate*. This change deliberately
does **not** dispatch a job to the private Mac or relax `mac-access` controls.

## Intended flow

1. A PR against `main` runs `Mac runtime package / package` on **GitHub-hosted
   Ubuntu**. This check now runs on every PR, not only changes in `ops/mac