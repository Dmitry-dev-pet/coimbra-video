# Coimbra 011–025 consolidation

Integration scope authorized on 2026-09-30. This document records the integration design, not a claim that a merge or a new render has completed; inspect its PR and Actions run for live results.

## Preserved directions

The repository retains both the Earth Studio/post-processing path and the reproducible Blender/APatch path. Recent Blender work is organized as follows:

- 011–015: the isolated Polo II photo patch, hero buildings, environment realism and final still-image treatments. These remain separate from the full-city camera route.
- 016B–020: the full-city scene, native-subframe slow route, roof audit and corrected pitched roofs. Stage 020 produces the existing 48-second, 1440-frame, 1280×720 EEVEE video.
- 021–023: semantic vegetation, undergrowth and verified solar/ground objects.
- 024–025: backend comparison and three-checkpoint validation of Cycles CPU, 16 samples plus denoising.
- 026 is a separate render-only PR for the explicitly authorized full 360-frame, 12-second Cycles acceptance pass; merging this 011–025 consolidation does not establish 026 success.

## Why one consolidation

The main development line ends at 025 commit `d178382d10eef41ec00da3fe562fcc445438f8da`. Stage 020 is a sibling, not an ancestor of 025. The integration preserves both histories with a two-parent merge and adds the two unchanged 020 files to the 025 tree. No geometry/semantic/material/camera algorithms are changed during that merge.

The read-only integration audit verifies that all thirteen original PR heads are ancestors of the integration commit, have not changed since the pinned snapshot, and have a successful matching render workflow for the exact executable state. A successful ancestor is accepted only when Blender, scripts and workflow files are identical. Missing evidence blocks the audit rather than silently treating a stale branch as tested.

Original PRs: #9–#21. Keep their branches/history; close or mark them integrated only after the consolidation is actually merged into main. Do not squash away the source ancestry. Do not confuse source-code integration with visual approval of every scene or with a new production render.

## Operational boundaries

No credentials are read or moved. Existing source-artifact runs stay pinned, including their expiry limitations. Existing heavy-render triggers remain branch-specific/manual; integrating them must not trigger every historic render on each main push. APatch's protected-layer rules and source attribution remain unchanged.
