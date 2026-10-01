# Coimbra V2-001 — Photogrammetry hero frame

## Goal

Prove a materially more realistic Coimbra representation before any new full-route
video is authorized.

V2-001 is a **still-image and registration lane**. It does not inherit the 032–036
production geometry and it does not promote a new movie renderer.

## Visual target

The first hero view is anchored on the left bank near Santa Clara and looks across
the Mondego / Baixa toward Paço das Escolas. The exact camera is derived from the
fixed WGS84 control points in `config/coimbra_v2_001.json`.

The first delivery is intentionally neutral:

- 1600 × 1000;
- 55 mm lens;
- no depth of field;
- no motion blur;
- no cinematic post-grade;
- 16 Cycles samples with denoising;
- one daylight setup only.

If the scene is not convincing under those conditions, V2-001 has not solved the
underlying city-quality problem.

## Independent V2 geographic extent

The legacy Coimbra bridge bbox ends south of the historic university core. V2-001
therefore owns a separate bbox:

`[-8.4435, 40.1980, -8.4160, 40.2145]`

Do not mutate `config/coimbra_bridge.json` or replace any accepted 032–036 asset.

## Sources

### Photogrammetry core

Sketchfab model `4175f64513a44546b65a119af5aacdff`:

- title: Coimbra;
- creator: VirtualPhoto3D / @johnagotinho;
- DJI Mini 2 photogrammetry;
- 7.5M triangles / 3.8M vertices as published by Sketchfab;
- CC Attribution;
- downloadable through Sketchfab's authenticated Download API.

The repository stores only provenance and download tooling. The large source asset
is an Actions artifact / runner input, not a normal Git blob.

### Context

Use official DGT data for the V2 bbox:

- Orthophotos 2025 RGB at 25 cm/px, CC BY 4.0;
- MDT-50cm and MDS-50cm from the 2024–2025 LiDAR survey;
- derived 2 m practical terrain and 1 m height-above-ground evidence.

OSM is not the primary visible building representation in V2-001.

## Registration strategy

Do not hand-place the photogrammetry.

1. Import the Sketchfab glTF/GLB in Blender.
2. Render a neutral orthographic top-down texture image and record exact model XY
   bounds.
3. Match that image against the DGT 2025 orthophoto using local image features.
4. Estimate a RANSAC-constrained 2D similarity transform from photogrammetry XY to
   the V2 local EPSG:3763 frame.
5. Apply the same scale to Z.
6. Estimate vertical translation by comparing spatially binned photogrammetry
   surface maxima against DGT MDS.
7. Persist the transform, match statistics and source hashes before rendering.

Reject the registration when feature support or RANSAC inlier evidence is weak.
A visually plausible but unverified manual transform is not acceptable V2 evidence.

## First-frame composition

The camera anchor is Mosteiro de Santa Clara-a-Nova and the target is Paço das
Escolas. At execution time the exact local XYZ values are recomputed from EPSG:3763
and DGT terrain/surface evidence.

The frame should contain enough surrounding context to reveal whether the
photogrammetry-to-DGT transition is believable.

## Acceptance

V2-001 passes only after human review confirms:

- Coimbra is immediately recognizable;
- the historic core reads as captured city geometry rather than generic extrusion;
- scale and terrain contact are plausible;
- no obvious registration drift is visible;
- DGT context and the photogrammetry core belong to the same scene;
- the image is substantially better before motion blur, DOF or grading.

Passing V2-001 authorizes more V2 stills. It does **not** authorize a full video.
