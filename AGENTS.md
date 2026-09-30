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


The 005 facade pass may generate one deterministic `Facade_Windows` mesh before
APatch session start. Protect `Facade_*` alongside `City_*`; do not mutate
window geometry or facade provenance after the textured baseline is frozen.


## Vegetation development bridge 006
`COIMBRA-BRIDGE-006-VEGETATION` may add one deterministic
`Vegetation_Trees` mesh before APatch session start using OSM tree/green-area
data plus DGT terrain elevation. Avoid trees on buildings, facade quads and road
ribbons via scene ray-cast rejection. After `coimbra-vegetation-base.blend` is
frozen, protect `Vegetation_*` together with `City_*` and `Facade_*`.
Cars are out of scope for this pass.


## Miniature detail bridge 007
`COIMBRA-BRIDGE-007-MINIATURE-DETAILS` may add deterministic `Detail_*` meshes
before APatch session start: cars, solar panels, rooftop fixtures and HVAC.
Slight oversizing is intentional because the target is a readable physical-model
look, not an exact digital twin. After the details baseline is frozen, protect
`Detail_*` together with `City_*`, `Facade_*`, and `Vegetation_*`.


## High-resolution geodata bridge 008
008A may replace the procedural car mesh before APatch session start using
25 cm DGT orthophoto OBB detections. Preserve the detection JSON and QA overlay
as evidence; do not claim the detector is exhaustive.

008B may acquire DGT `MDT-50cm` and `MDS-50cm` only through the authenticated
CDD flow. Preserve exact cropped 50 cm GeoTIFFs as source evidence and derive
coarser practical render/height grids from them. Do not commit DGT credentials
or raw authenticated URLs. The 50 cm source resolution and any Blender render
resolution must remain explicitly distinguished in metadata.


## Urban quality bridge 010
`feature/coimbra-010-urban-quality` is a visual QA lane stacked on the accepted
009 open-source stack. It starts from the governed 009D scene, preserves the
production camera/path and all non-`Urban_*` layers, and may rebuild only the
street-furniture representation plus add `Urban_Curbs` and
`Urban_RoadMarkings` before any future APatch session.

Street-level QA cameras are temporary render-only cameras and must not be saved
into the output blend. Do not add external GLB asset dependencies to this pass.
Promotion to a new governed production contract requires visual review first.


## Photo patch bridge 011
`feature/coimbra-011-photo-patch` is intentionally not a full-city production
upgrade. It crops the accepted 010 scene to one approximately 220 x 220 m Polo II
photo patch and creates a still-only Blender scene.

The patch may remove geometry outside its crop, replace the route camera with a
single still camera and use photo-specific lighting. It must not be presented as
a replacement for the full Coimbra scene. The purpose is to create a small,
editable hero-shot asset where substantially more manual/high-detail work is
practical.


## Hero building pass 012
`feature/coimbra-012-hero-buildings` is a photo-only refinement stacked on
the 011 Polo II patch. It may replace facade/roof representation only for the
five buildings with the largest visible contribution in the 011 hero camera.

Flat roofs must never receive the packed tile materials. Sloped roofs may use
the existing packed Coimbra tile material. Old facade-window and rooftop-detail
faces inside the selected footprints may be removed before the higher-detail
local overlay is built.

012 uploads review images and a manifest only; do not publish a Blender artifact
from this stage.


## Hero realism pass 013
`feature/coimbra-013-hero-realism` is a photo-only refinement stacked on the
corrected 012b Polo II hero geometry. It must not expand the patch or change the
full-city production scene.

013 may reduce the regularity of generated windows deterministically, add
restrained facade trims/downpipes, add balconies only where a camera-facing
hero facade is physically wide enough, and add small technical units only on
flat hero roofs at guaranteed interior footprint points.

The review lane uploads images and a manifest only; do not publish a Blender
artifact from 013.


## Environment realism pass 014
`feature/coimbra-014-environment-realism` is a photo-only environment refinement
stacked on 013. It must remain inside the existing Polo II photo patch and must
not modify the full-city production scene or the 013 hero-building geometry.

014 may replace only the photo-patch sidewalk/curb material response, add low
ground vegetation derived from OSM green-area semantics, and soften the existing
photo lighting. New low vegetation must be rejected inside OSM building
footprints and near OSM highways. Existing trees remain untouched.

The review lane uploads images and a manifest only; do not publish a Blender
artifact from 014.


## Final look pass 015
`feature/coimbra-015-final-look` is a photo-only finishing pass stacked on 014.
It must not change scene geometry, materials, lighting, or full-city production
state.

015 renders the accepted lower 55 mm composition at 3200 x 2000, then produces
1600 x 1000 delivery images via deterministic 2x LANCZOS downsampling and three
restrained post-render grades: neutral, warm, and soft cinematic.

No Blender file or oversampled master should be published as a user-facing
artifact; upload only the three final review images plus manifests.


## Cycles production baseline 025
`feature/coimbra-025-cycles-production-baseline` is a render-backend validation
lane stacked on the successful 024 A/B/C comparison. It must preserve the 023
semantic geometry/material state and the production camera exactly.

Render the established route checkpoints 1, 181 and 360 with both the inherited
current EEVEE path and Cycles CPU at 16 samples with denoising. 025 may change
render-backend settings only; it must not change route timing, camera animation,
geometry, materials, semantic evidence or solar-promotion rules.

Upload paired stills, one comparison sheet, exact render/camera metadata and
basic image metrics. Promotion of Cycles to a full-route renderer happens only
after multi-frame visual review.


## Mac Metal checkpoint lane 027

`feature/coimbra-027-mac-metal-checkpoints` is a render-only A/B lane over the
accepted 026 packed scene. It must not rebuild or modify geometry, materials,
world/light state, semantic evidence, or the production camera.

Use exactly the accepted 026 prepared artifact from run `36646652931` and verify
its packed-scene/protected-state hashes before rendering. Render checkpoints
1, 181 and 360 with the accepted 026 CPU settings and then with only the Cycles
execution device changed to GPU / Metal.

027 is evidence collection, not renderer promotion. Passing checkpoint timing and
image-difference guards does not authorize replacing the accepted 026 CPU full-route
delivery. A full-route Metal render requires a separate follow-up acceptance lane.
