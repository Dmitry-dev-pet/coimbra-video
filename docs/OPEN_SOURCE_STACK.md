# 009 — Open-source geospatial stack

This lane evaluates existing open-source components against the Coimbra miniature
pipeline instead of reimplementing mature geospatial functionality.

## Pinned upstreams

- **MOSAIQ OpenStreetMap to Blender Add-On** — Apache-2.0, commit
  `f73d030aecd3289007472a887d78aae2e74b6ea0`.
  Used as a runtime dependency for OSM street-detail geometry and tag semantics.
  Upstream code is checked out in CI; it is not copied into this repository.

- **OSM2World** — MIT, commit
  `8ec26a9ea426444a4f7882cf0cfcab432c876ae5`.
  Built in CI and run independently against the same Coimbra OSM bbox. The GLB
  output is a comparison/reference artifact, not a replacement for our scene.

- **PDAL** — permissive BSD-style license. The 009C lane uses the official
  `pdal/pdal:2.9.0` container to process raw DGT LAZ and produce a 1 m
  HeightAboveGround reference surface.

- **OpenDroneMap** — AGPL-3.0. Kept as an optional external photogrammetry tool.
  It is not required by the current DGT/OSM pipeline because we already have
  official orthophoto, MDT, MDS and LiDAR sources.

## Architecture

```text
DGT 25 cm orthophoto ──► YOLO OBB ───────────────► real vehicle placement
DGT MDT/MDS 50 cm ─────► raster highres lane ───► 2 m terrain + 1 m HAG
DGT raw LAZ ────────────► PDAL ──────────────────► independent 1 m HAG reference

OSM bbox ──► current Coimbra generator ──────────► buildings/roads
        ├──► MOSAIQ runtime dependency ──────────► sidewalks/parking/crosswalks
        └──► OSM2World ──────────────────────────► independent GLB reference

all accepted layers ──► Blender miniature scene ──► APatch governance
```

The benchmark lanes must remain separable. A successful upstream benchmark does
not automatically replace the current layer: visual QA and source/evidence
comparison come first.
