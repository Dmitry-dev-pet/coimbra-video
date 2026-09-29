# Coimbra Video

Current direction: **Google Earth Studio → tilt-shift post-processing → MP4**.

The earlier DGT/LiDAR experiment is kept in the repository as a fallback, but it is no longer the main path.

## Why this path

Google Earth Studio already provides the realistic 3D city imagery and cinematic camera system. We use it only as the source renderer, then do our own miniature/tilt-shift look afterwards.

The post-processing stage:
- keeps the original Earth Studio framing;
- never crops the image;
- applies a tilted focus band;
- progressively blurs foreground/background;
- adds a small saturation/contrast lift;
- explicitly protects the bottom attribution area from blur;
- encodes the final H.264 MP4.

## 1. Create the Coimbra shot

See [EARTH_STUDIO.md](EARTH_STUDIO.md).

Recommended first test:
- search for **Universidade de Coimbra**;
- 10–12 seconds;
- 30 fps;
- 1920×1080;
- slow oblique orbit/lateral move;
- University + Baixa + Mondego in frame;
- render an image sequence ZIP;
- leave Earth Studio attribution visible.

Official Earth Studio:
https://earth.google.com/studio/

## 2. Process locally

Install Python dependencies and ffmpeg:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then:

```bash
python scripts/earth_studio_post.py \
  --input ~/Downloads/earth-studio-render.zip \
  --output output/coimbra_earthstudio_tiltshift.mp4 \
  --fps 30
```

Main controls:

```text
--focus-y       vertical position of the sharp band
--tilt          slope of the sharp band
--sharp-width   width of the fully sharp zone
--blur-span     how quickly blur grows away from focus
--max-radius    maximum Gaussian blur radius
```

## 3. Process in GitHub Actions

Open:

**Actions → Coimbra Earth Studio post-process → Run workflow**

Provide:
- `source_url`: a **direct downloadable URL** to the ZIP exported by Earth Studio;
- `fps`: the same frame rate as the Earth Studio project;
- optional `focus_y` and `tilt`.

The result appears under the workflow run in:

**Artifacts → coimbra-earthstudio-video**

and contains:

```text
coimbra_earthstudio_tiltshift.mp4
```

A normal Google Drive sharing page is not a direct file URL. For Actions, use a URL that returns the ZIP bytes directly.

## Attribution

Do not crop, hide, replace or remove Google Earth / imagery-provider attribution.

Earth Studio automatically generates attribution for rendered frames. The post-processing script preserves the bottom part of every original frame so the credits remain readable.

Official attribution documentation:
https://earth.google.com/studio/docs/attribution/

## Legacy DGT experiment

The original open-data experiment remains available:
- DGT 2025 orthophoto downloader;
- DGT MDS/LiDAR downloader;
- mesh builder;
- Blender preview.

Those files are retained as a fallback, not used by the main GitHub Action.


## APatch Blender bridge

The repository now also contains a credential-free contract-governed Blender path.

`COIMBRA-BRIDGE-001`:
- fetches real Coimbra building footprints and roads from OpenStreetMap/Overpass;
- builds one protected city scene in Blender;
- executes camera/lighting/render changes through `Dmitry-dev-pet/apatch-blender`;
- protects all `City_*` geometry with semantic hashes;
- renders the Sanches/Rua Brasil → Polo II → Portela → Princesa Cindazunda corridor;
- independently verifies the camera checkpoints and unchanged city geometry;
- outputs a 854×480 H.264 MP4 with OpenStreetMap attribution.

This is separate from the Earth Studio path and exists specifically as the large integration test for the generic Blender bridge.


## Textured Blender bridge 002

`COIMBRA-BRIDGE-002` upgrades the reproducible OSM city with:
- DGT 2025 25 cm orthophoto packed into the Blender file;
- separate deterministic wall and roof materials for buildings;
- improved road-class materials;
- the same contract-governed camera/lighting/render edits;
- protected `City_*` geometry verified by semantic hashes.

The DGT orthophoto is fetched only for the route bbox and is embedded into the prepared `.blend`, so parallel render jobs remain self-contained.


## DGT terrain bridge 003

`COIMBRA-BRIDGE-003` is the terrain upgrade:
- authenticated DGT `MDT-2m` tiles;
- 6 m render terrain generated from the official surface model;
- OSM buildings and roads transformed to EPSG:3763 and draped onto the terrain;
- DGT 2025 ortho packed into the terrain material;
- the same generic APatch Blender camera/light/render contract;
- all `City_*` terrain/building/road geometry protected by semantic verification.

The DGT data are open-data. The CDD download flow required one authenticated acquisition, so the exact route crop is now pinned in the repository as a compact 6 m derived terrain asset (`bridge_terrain_6m.npz`, about 400 KB). Normal CI runs no longer need DGT credentials. The source provenance remains DGT MDT-2m, with the original 2 m data downsampled to 6 m for rendering.


## Slow terrain flight

`COIMBRA-BRIDGE-003-SLOW` preserves the validated DGT/MDT terrain route and doubles its duration from 6 to 12 seconds. The same seven camera poses are retimed over 360 frames at 30 fps, so geometry, framing targets, lighting, and route remain comparable to the original 003 proof.


## Visual development 004

`COIMBRA-BRIDGE-004-VISUAL` is the fast Blender look-development loop. It
keeps the full 360-frame route in the scene for local scrubbing, but GitHub
Actions renders only three 854×480 previews (frames 1, 181, and 360) and uploads
the governed `coimbra-visual-dev.blend`.

The first look raises the camera about 15% while preserving XY positions,
targets, lenses, and timing; combines cool ambient light with a warm low golden
key; and enables moderate camera depth of field. Full MP4 rendering is deferred
until the visual style is approved.


## Texture development 005

`COIMBRA-BRIDGE-005-TEXTURES` keeps the approved 004 camera/light/DOF look and
adds a reproducible CC0 PBR material layer to the generated city. CI downloads
the declared 1K materials from the official Poly Haven API, applies them with
triplanar box mapping, packs the images into a textured baseline `.blend`, and
then hashes that baseline into the APatch SDD session.

The first material set uses plaster/stone wall variants, weathered terracotta
roof tiles, asphalt, and cobblestone paving. Full MP4 rendering remains disabled
during ordinary texture iteration; Actions emit the inspectable `.blend` plus
frames 1, 181 and 360.

Texture assets are CC0. API integration: **Powered by Poly Haven**.

The 005 preparation step also replaces the legacy beveled road curves with flat terrain-following mesh ribbons, preserving the same centerlines and widths so roads read as roads rather than pipes.


The 005 visual baseline now also generates one lightweight procedural
`Facade_Windows` mesh from building wall quads. It adds repeated dark windows
and a small deterministic warm-lit subset without creating thousands of Blender
objects.


## Vegetation development 006

`COIMBRA-BRIDGE-006-VEGETATION` builds on the approved 005 textured/facade
scene and adds a lightweight low-poly tree layer. Exact OSM `natural=tree`
nodes are used when present; green OSM areas are deterministically sampled for
additional sparse coverage. Tree ground elevation comes from the pinned DGT
terrain model.

Trees are combined into one `Vegetation_Trees` mesh with a small material
palette so the Blender file stays practical. Buildings, facades, roads,
vegetation and provenance metadata are protected after the 006 baseline is
frozen. Normal iteration still renders only frames 1, 181 and 360.


## Miniature details 007

`COIMBRA-BRIDGE-007-MINIATURE-DETAILS` adds deliberately readable scale cues
to the approved 006 miniature scene: simplified cars, rooftop solar arrays,
chimneys/vents/utility boxes, and sparse facade HVAC units. These details are
procedural visual-model elements rather than claims of exact real-world object
placement.

Each detail category is consolidated into one `Detail_*` mesh so the scene
remains practical to inspect. Normal iteration still renders only frames
1, 181 and 360.


## High-resolution geodata 008

008 is split into two independent lanes.

### 008A — car reality

The 2025 DGT RGB orthophoto is fetched at its native 25 cm ground sampling
distance. A DOTAv1-pretrained oriented-bounding-box detector searches tiled
aerial imagery for small/large vehicles, converts OBB centers/orientations to
the local EPSG:3763 scene frame, samples an approximate vehicle color from the
orthophoto, and replaces the purely procedural 007 car layer. The detector is
a build-time QA/derivation tool; detections are stored as JSON and a downscaled
OBB overlay is emitted for visual inspection.

### 008B — 50 cm LiDAR derivatives

The CDD-authenticated lane downloads both DGT `MDT-50cm` and `MDS-50cm`
tiles intersecting the Coimbra bbox. It preserves exact cropped 50 cm GeoTIFFs
and derives:
- a 2 m terrain grid for practical Blender rendering;
- a 1 m max-pooled `MDS - MDT` height-above-ground grid for later calibration
  of trees/buildings and other above-ground structures.

CDD download requires a registered DGT account and repository secrets
`DGT_USER` / `DGT_PASSWORD`.
