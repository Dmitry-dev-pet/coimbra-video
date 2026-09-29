# SPEC-COIMBRA-FULL-PITCHED-ROOFS-1

## Goal

Eliminate the remaining visual contradiction where a roof uses a tile material
but is still represented by a horizontal slab in the full-route scene.

This pass is global for the production-camera corridor, not limited to the Polo
II photo patch.

## Inputs

- accepted Coimbra 018 full-route roof-audit scene;
- pinned OSM semantics;
- DGT Orthophotos 2025 already packed in the accepted scene;
- DGT LiDAR 2024–2025 height-above-ground grid at 1 m.

## Rules

1. A horizontal roof surface in the camera corridor must never keep a
   `City_Roof_*` tile material.
2. Explicit OSM `roof:shape` remains the strongest roof-form signal.
3. Unknown buildings may be treated as pitched only when:
   - aerial color is tile-like; and
   - LiDAR HAG has enough relief to support a pitched roof.
4. Safe simple footprints receive actual gabled / hipped / skillion geometry.
5. Complex or concave footprints that cannot be converted safely fall back to a
   non-tile warm/gray surface rather than a horizontal tile carpet.
6. Existing production-camera animation must remain byte-for-byte equivalent at
   the standard checkpoint frames.

## Geometry

- gabled roofs are generated only for four-point footprints;
- hipped and skillion roofs require convex footprints;
- roof rise is estimated from LiDAR HAG and clamped to a conservative range;
- old horizontal roof faces are physically removed for converted buildings;
- stale flat rooftop HVAC/solar/detail faces are removed from converted
  footprints to avoid floating through new slopes.

## QA

First render a full 12-second / 360-frame route at 1280×720 / 30 fps.

The verifier must require:
- zero horizontal `City_Roof_*` tile faces in the 550 m route corridor;
- at least 40 buildings converted to real pitched geometry;
- a non-empty sloped-roof overlay;
- unchanged production camera;
- valid 360-frame H.264 output.

If the 12-second QA is visually acceptable, use this prepared scene as the
source for the next 1440-frame native-subframe smooth render.
