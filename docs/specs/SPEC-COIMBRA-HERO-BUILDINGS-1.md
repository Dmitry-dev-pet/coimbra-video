# SPEC-COIMBRA-HERO-BUILDINGS-1 — Polo II hero geometry

> **Status:** photo-only visual experiment · **Owner:** repository

## Scope

Work only inside the existing 011 Polo II photo patch. Do not improve the full
Coimbra scene and do not expand the patch.

Select exactly four buildings with the largest visible screen contribution in
the 011 hero camera. These are the only buildings that receive higher-detail
geometry.

## Roof rule

The material rule is strict:

- **flat roof → no roof-tile material**
- flat roofs use a rough membrane/concrete-like surface and a small parapet;
- sloped roofs may use the existing packed Coimbra roof-tile material;
- explicit OSM `roof:shape` wins when present;
- otherwise building type, footprint area and aspect ratio provide a deterministic
  fallback classification.

Supported local forms are flat, gabled and hipped. A gabled request on an
irregular footprint may fall back to hipped rather than creating broken
geometry.

## Facades and windows

For the four selected buildings:

- add an opaque facade shell over the old low-detail building surface;
- remove the old procedural facade-window faces within those footprints;
- derive floor count from `building:levels` when available, otherwise height;
- derive window columns from actual facade length;
- create glass panels plus four-piece frames and projecting sills;
- create one front entrance on a readable camera-facing facade;
- do not use random dark rectangles as the only window representation.

Old rooftop solar/HVAC/detail faces inside the selected footprints are removed
so they do not float through a newly sloped roof.

## Outputs

Render only images plus a manifest:

- hero image using the existing 011 camera;
- close-up A on the highest-ranked hero building;
- close-up B on the second-ranked hero building;
- manifest with selected OSM way ids, roof classification, window counts and
  the flat-roof tile invariant.

No Blender file is uploaded from this stage. The user-facing artifact is the
set of review images.
