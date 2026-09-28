# SPEC-COIMBRA-VEGETATION-1 — Coimbra vegetation development

> **Status:** Draft v1 · **Owner:** repository
> **apatch artifact:** `spec:SPEC-COIMBRA-VEGETATION-1`

## R1 Produce an inspectable vegetation visual-dev scene

`COIMBRA-BRIDGE-006-VEGETATION` must start from the approved textured/facade
scene and add a lightweight deterministic tree layer before APatch session
start.

Tree placement uses:
- exact OpenStreetMap `natural=tree` nodes where available;
- deterministic sparse sampling inside OSM green areas such as park, garden,
  wood, forest, orchard, meadow and grass;
- the pinned DGT terrain model for tree ground elevation.

The vegetation layer must be a small number of Blender objects, ideally one
combined low-poly mesh, not thousands of independent objects.

The prepared vegetation scene becomes the APatch baseline. From that point
onward `City_*`, `Facade_*` and `Vegetation_*` state plus selected provenance
metadata must remain unchanged.

The output must include:
- an inspectable governed `.blend`;
- preview frames 1 / 181 / 360;
- a vegetation manifest with source/count evidence;
- a passing semantic verification report.

Do not render the full 360-frame movie during ordinary vegetation iteration.
Cars are explicitly out of scope for this first vegetation pass.

(verify: python3 scripts/verify_vegetation_dev_evidence.py --report bridge_output_006/vegetation-verification.json --probe verification/COIMBRA-BRIDGE-006-VEGETATION.probe)

## Visual target

- break up the bare terrain and hard building silhouettes;
- trees should read at drone distance without dominating the city;
- preserve the approved 005 camera, lighting, DOF, facades, roads and PBR;
- avoid dense forest-like coverage in ordinary streets.
