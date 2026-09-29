# SPEC-COIMBRA-DETAILS-1 — Coimbra miniature detail development

> **Status:** Draft v1 · **Owner:** repository
> **apatch artifact:** `spec:SPEC-COIMBRA-DETAILS-1`

## R1 Produce an inspectable miniature-detail visual-dev scene

`COIMBRA-BRIDGE-007-MINIATURE-DETAILS` must start from the approved 006
vegetation scene and add a deterministic miniature-detail layer before APatch
session start.

The layer should deliberately favor readability over exact digital-twin
reconstruction. Small urban objects may be modestly oversized so they remain
legible at the approved drone/miniature camera distance.

The first 007 pass includes:
- simplified colored cars placed on major/local/service road ribbons;
- solar-panel arrays on a deterministic subset of sufficiently large roofs;
- rooftop chimneys / vents / utility boxes;
- outdoor HVAC units on a sparse subset of building facades.

Each category should be consolidated into one or a small number of
`Detail_*` mesh objects rather than thousands of Blender objects.

The prepared scene becomes the APatch baseline. From that point onward
`City_*`, `Facade_*`, `Vegetation_*`, and `Detail_*` state plus selected
provenance/count metadata must remain unchanged.

The output must include:
- an inspectable governed `.blend`;
- preview frames 1 / 181 / 360;
- a detail manifest with generated counts;
- a passing semantic verification report.

Do not render the full 360-frame movie during ordinary detail iteration.

(verify: python3 scripts/verify_details_dev_evidence.py --report bridge_output_007/details-verification.json --probe verification/COIMBRA-BRIDGE-007-MINIATURE-DETAILS.probe)

## Visual target

- reinforce the feeling of a richly built physical city model;
- make scale cues visible without cluttering the image;
- preserve the approved camera, DOF, lighting, PBR, facades, roads and trees;
- avoid exact claims that every generated panel, AC unit or car exists at that
  real-world location.
