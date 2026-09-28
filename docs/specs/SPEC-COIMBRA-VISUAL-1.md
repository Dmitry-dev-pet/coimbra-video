# SPEC-COIMBRA-VISUAL-1 — Coimbra miniature visual development

> **Status:** Draft v1 · **Owner:** repository
> **apatch artifact:** `spec:SPEC-COIMBRA-VISUAL-1`

## R1 Produce an inspectable governed visual-dev scene

`COIMBRA-BRIDGE-004-VISUAL` must create an inspectable Blender scene without
rendering the full 360-frame movie. The plan may change camera height, camera
depth of field, world light, one bounded golden key light, render settings, and
three preview frames. Protected `City_*` geometry and animation must remain
unchanged.

The output must include the governed `.blend`, preview frames 1 / 181 / 360,
and a passing semantic verification report. The 360-frame camera path remains
in the `.blend` so visual review can scrub the entire 12-second route locally.

(verify: python3 scripts/verify_visual_dev_evidence.py --report bridge_output_004/visual-verification.json --probe verification/COIMBRA-BRIDGE-004-VISUAL.probe)

## Visual target

- camera Z about 15% above the verified 003-SLOW path;
- original XY route, targets, lenses, and timing preserved;
- cool ambient/world with a warm low golden key;
- moderate depth of field for a miniature / tilt-shift-like look;
- no deep texture or geometry redesign in this iteration.
