# SPEC-COIMBRA-HERO-REALISM-1 — Polo II hero realism pass

> **Status:** photo-only visual experiment · **Owner:** repository

## Scope

Build only on the corrected 012b Polo II hero geometry. Do not expand the
220 m photo patch and do not modify the full-city production scene.

## Windows

The regular 012 window grid is retained only as a structural guide.

For the generated hero windows:

- camera-facing walls keep most openings;
- side/rear walls deterministically omit more openings;
- a small deterministic size and horizontal-position variation breaks perfect
  spreadsheet alignment;
- a subset of visible windows gets a central mullion;
- the pass must still preserve a coherent floor/bay rhythm.

This is not a random-noise pass: all choices are deterministic from world
coordinates.

## Facade realism

Only the four existing hero buildings may receive the 013 overlay:

- a darker ground plinth;
- a small cornice band;
- one restrained downpipe;
- balconies only on the top two camera-facing hero facades;
- balcony railings must have a slab, front rail, posts and side rails.

## Roof realism

The 012b roof geometry remains authoritative.

013 may add small technical roof units only on flat hero roofs. Their anchor
must come from an interior triangle of the footprint rather than the polygon
centroid, so concave roofs cannot receive floating rooftop units outside their
boundary.

## Review images

Produce four photos only:

1. existing hero-camera composition with 013 realism;
2. a slightly lower 55 mm version;
3. a 65 mm version from the original hero location;
4. a 105 mm facade detail from the same safe hero location.

No Blender file is uploaded.
