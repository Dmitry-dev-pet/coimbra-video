# Coimbra 034 — WebGPU feasibility

## Goal

Test whether the governed Coimbra geodata can drive a responsive browser renderer
without replacing or mutating the accepted Blender production lanes.

034 is a parallel renderer experiment. It is not a replacement for 031–033 and
it does not authorize any change to the accepted Blender scene, camera keyframes,
materials, lighting or render contracts.

## Inputs

Use only existing non-secret, inspectable sources:

- pinned DGT terrain: data/processed/bridge_terrain_6m.npz and its metadata;
- OpenStreetMap building/highway data fetched through the existing public
  scripts/fetch_osm_bridge.py path;
- the local EPSG:3763 conversion produced by
  scripts/prepare_osm_local_for_terrain.py;
- the seven governed camera anchors in COIMBRA-BRIDGE-003-SLOW.

The ordinary 034 build must not retrieve authenticated DGT sources, credentials,
private URLs or production Blender artifacts.

## Web dataset

scripts/export_webgpu_coimbra.py converts the inputs into static JSON tiles:

- tile size: 250 metres;
- terrain heights remain derived from the pinned 6 m DGT terrain;
- OSM buildings are draped on that terrain;
- road segments are draped on the same height sampler;
- the 003-SLOW camera anchors are copied into index.json as immutable source
  evidence for scripted-route playback.

Generated web data is a build artifact, not a new source of truth.

## Browser renderer

The prototype lives under web/ and uses:

- three.js 0.186.1;
- WebGPURenderer;
- one shared terrain material, one shared building material and shared road
  materials;
- frozen matrices for static tile objects;
- compileAsync before a newly built tile is shown;
- distance streaming around the camera;
- two feasibility LOD levels: near includes roads, far omits roads;
- free flight plus a scripted Catmull-Rom playback through the governed route
  anchors.

This is deliberately smaller than a production city engine. Facade generation,
orthophoto materials, vegetation, reflections, sky-occlusion baking and richer
LOD are follow-up work only if 034 proves viable.

## CI contract

The pull-request workflow must:

1. run Blender-free exporter unit tests;
2. fetch public OSM data for the existing Coimbra bbox;
3. convert it into the existing local EPSG:3763 coordinate system;
4. export 250 m static tiles;
5. type-check and build the Vite application with Node 22;
6. verify that dist contains both the app and generated Coimbra index;
7. upload the complete static dist as an Actions artifact.

A successful CI build proves reproducibility, not browser performance.

## Performance receipt

The app records rolling browser frame times and can export
coimbra-034-webgpu-benchmark.json.

For the first M4 16 GB feasibility run use:

- WebGPU enabled;
- scripted route mode;
- browser zoom 100%;
- a fresh page load followed by at least 5 seconds warm-up;
- then at least 60 seconds of measurement;
- no other heavy GPU workload.

Record viewport, device pixel ratio, browser/user-agent, sample count, mean,
p50, p95, maximum frame time and the number of frames above 50 ms.

The promotion target is:

- p50 frame time at or below 16.7 ms;
- p95 at or below 22 ms;
- no recurring shader-compilation stalls above 50 ms after warm-up.

If the target is missed, keep the receipt as evidence and optimize the 034
renderer; do not reinterpret a miss as a pass.

## Deployment

The build output is static. The workflow exposes it as a downloadable Actions
artifact on every 034 PR. GitHub Pages deployment is manual and must use the
same verified dist artifact; 034 must not silently replace another existing
Pages site.

## Attribution

Published 034 output must preserve:

- DGT source attribution appropriate to the pinned terrain;
- © OpenStreetMap contributors · ODbL.

The InsideWalk New York MIT project is an architectural reference for streaming
and WebGPU techniques; 034 does not copy its city dataset.

## Acceptance boundary

Passing CI means only that the WebGPU prototype and its real Coimbra dataset
build reproducibly.

034 is feasible for promotion only after a browser performance receipt on the
target Mac is reviewed. Even then, Blender remains the cinematic/offline path
until a separate contract explicitly changes that decision.
