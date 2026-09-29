# SPEC-COIMBRA-ENVIRONMENT-REALISM-1 — Polo II environment realism

> **Status:** photo-only visual experiment · **Owner:** repository

## Scope

Build only on the corrected Polo II photo stack through 013. Do not expand the
photo patch and do not modify the full-city production scene.

014 improves only environment cues that currently make the still look synthetic:
surface response, low ground vegetation and lighting.

## Surfaces

- keep the existing sidewalk and curb geometry;
- replace only their local photo-patch materials with procedural concrete;
- concrete must use subtle color variation, high roughness and a small bump;
- do not change road centerlines, curb geometry, terrain geometry or hero
  building geometry.

## Vegetation

New vegetation may come only from OSM-tagged green areas intersecting the
220 m Polo II patch.

Accepted semantics:
- landuse: grass, meadow, forest, recreation_ground, village_green
- leisure: park, garden, pitch, golf_course
- natural: wood, grassland, scrub, heath

The pass may add:
- a low green-ground overlay draped onto the DGT terrain;
- sparse low-poly shrubs;
- sparse grass tufts.

Generated points must be rejected inside OSM building footprints and near OSM
highways. Existing trees remain untouched.

## Lighting

Use the existing 011 photo lights as the starting point:
- soften the sun by increasing angular size;
- reduce the strong cool area fill;
- keep a warm/cool daylight balance rather than studio-flat illumination;
- do not add a new production lighting system.

## Review images

Produce three review photos only:
- original 48 mm hero position;
- 55 mm lower candidate;
- 65 mm tighter candidate.

No Blender artifact is uploaded.
