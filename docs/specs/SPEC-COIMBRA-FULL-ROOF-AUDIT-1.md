# SPEC-COIMBRA-FULL-ROOF-AUDIT-1

## Goal

Fix implausible tiled roofs directly in the full production-route scene.

The old base scene assigned one of four tile materials deterministically to
almost every extruded OSM roof, even though the underlying top face is flat.
018 replaces that material logic along the visible production-camera corridor.

## Evidence hierarchy

For each City_Buildings roof face inside 550 m of the production camera route:

1. explicit OSM `roof:shape` wins;
2. explicit OSM `roof:material` is next;
3. strong building-type evidence may classify obvious flat or pitched cases;
4. very large footprints default to flat;
5. otherwise DGT Orthophotos 2025 roof color resolves the uncertain case.

Google Maps/Earth imagery may be used manually for spot-checking disputed
buildings, but is not bulk-downloaded or used to build the dataset.

## Material rules

- classified flat roof -> never use `City_Roof_*` tile material;
- flat roof color is selected from DGT orthophoto as light / gray / dark / warm;
- explicit or strongly supported pitched tile roofs retain a tile material;
- heuristic pitched roofs whose aerial color is clearly non-red may use a
  neutral metal roof material;
- the corrected 012b/013 Polo II geometry remains separate and authoritative.

## Scope

- source: accepted 016B full-city scene with localized 012b/013/014 geometry;
- production camera animation must remain byte-equivalent at checkpoints;
- roof audit changes materials only on `City_Buildings`;
- no global lighting, camera, terrain or route changes.

## QA render

Render a full 360-frame / 12-second / 30-fps / 1280×720 production route.
Preserve five inspection frames chosen automatically from viewpoints where
corrected roof faces are most visible.
