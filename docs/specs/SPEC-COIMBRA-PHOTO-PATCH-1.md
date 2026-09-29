# SPEC-COIMBRA-PHOTO-PATCH-1 — Polo II single-photo patch

> **Status:** visual experiment · **Owner:** repository

## Goal

Do not build a higher-detail version of the entire Coimbra scene.

Create one small Blender scene specifically for a single hero still near Polo II.
The patch is cropped from the accepted Coimbra 010 visual scene and should keep
only the geometry needed around the selected camera.

## Spatial scope

- center: local EPSG:3763-relative XY `[-168.37, -748.07]`
- patch: approximately `220 × 220 m`
- source scene: `coimbra-urban-quality.blend`

The output is intentionally not a production route scene and does not replace
010.

## Photo scene

The preparation step may:

- physically remove mesh faces outside the patch;
- remove the production animation cameras/lights;
- add one still-photo camera and still-photo lighting;
- add a small bevel to the cropped building mesh;
- keep the existing local terrain, buildings, facades, vegetation, real cars,
  sidewalks, crossings, curbs, markings and street furniture that survive the
  crop.

The first patch targets Polo II because the 010 street QA already showed a
readable urban corridor there.

## Output

Produce:

- `coimbra-polo2-photo-patch.blend`
- one 1600×1000 hero PNG
- one square overview PNG showing the physical patch extent
- a manifest with before/after geometry counts and reduction ratio

The expected result is a much smaller scene that can be manually refined for a
single photograph without carrying the whole Coimbra model into the editing
workflow.
