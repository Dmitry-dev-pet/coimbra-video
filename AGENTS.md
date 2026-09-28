# AGENTS.md

GitHub main is the source of truth for this repository.

## Current production directions

- Earth Studio + post-process remains the realistic imagery path.
- `COIMBRA-BRIDGE-001` is the contract-governed Blender integration path.

## APatch Blender constraints

For `contracts/COIMBRA-BRIDGE-001.json`:
- all objects matching `City_*` are protected city geometry;
- the agent may change only operations listed in the contract;
- camera motion must be expressed through generic `animate_camera_path` contract data;
- do not replace the generic bridge with a Coimbra-specific edit script;
- verification must be performed by `Dmitry-dev-pet/apatch-blender`;
- OpenStreetMap attribution must remain visible in published video output.

The first OSM scene is intentionally reproducible without DGT credentials. DGT MDS/LiDAR may replace or augment the geometry provider later without changing the bridge contract model.


## DGT terrain bridge 003
`COIMBRA-BRIDGE-003` uses the pinned derived DGT MDT-2m crop in `data/processed/bridge_terrain_6m.npz`. The bridge contract permits only world, camera-path, light, render, and preview operations; terrain/buildings/roads remain protected. Do not replace the pinned terrain with unverified geometry during ordinary CI.


## Slow-flight variant
`COIMBRA-BRIDGE-003-SLOW` is a timing-only derivative of the verified 003 route. Preserve all camera locations, targets, lenses, protected `City_*` geometry, terrain source, and lighting; only retime the path to 360 frames / 12 seconds unless the contract is explicitly amended.


## Visual development bridge 004
`COIMBRA-BRIDGE-004-VISUAL` is the fast visual-review lane. Keep the verified
003-SLOW XY route, targets, lenses, and 360-frame timing, but allow explicit
visual changes to camera height, bounded camera DOF, world light, one bounded
golden key light, render settings, and preview frames. Do not run the full
360-frame MP4 render during normal 004 iteration. CI should emit the inspectable
`.blend` plus previews for frames 1, 181, and 360. Protected `City_*` geometry
and animation must remain unchanged.


## Texture development bridge 005
`COIMBRA-BRIDGE-005-TEXTURES` builds on the approved 004 visual look. Texture
base preparation may fetch only the CC0 assets declared in
`textures/COIMBRA-005-polyhaven.json`, at the declared resolution/maps, and must
pack them into `bridge_output_005/coimbra-textured-base.blend`. That packed
scene becomes the APatch baseline. After session start, protected `City_*`
state and the PBR provenance scene keys must remain unchanged. Normal 005
iteration renders only preview frames 1, 181 and 360, never the full movie.

For 005, the legacy `City_Roads_*` CURVE bevel geometry may be converted before APatch session start into flat mesh ribbons with the same centerlines, elevations, and full widths. Once `coimbra-textured-base.blend` is frozen, those flat road meshes are protected `City_*` state.
