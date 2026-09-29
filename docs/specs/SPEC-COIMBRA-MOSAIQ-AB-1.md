# SPEC-COIMBRA-MOSAIQ-AB-1 — MOSAIQ geometry comparison

> **Status:** Experiment · **Owner:** repository

## Goal

Compare the current Coimbra OSM geometry generator with the public
`TUMFTM/MOSAIQ-OpenStreetMap-to-Blender-Add-On` on the exact same Coimbra
bounding box before deciding whether any MOSAIQ layers should become part of
the governed APatch baseline.

The experiment is intentionally separate from the production APatch contracts.
It must not mutate the approved 004/005/006 baselines.

## Fixed inputs

- WGS84 bbox: `config/coimbra_bridge.json`
- terrain: pinned DGT MDT-2m derived 6 m crop
- terrain projection: EPSG:3763 local coordinates around the pinned DGT center
- ground texture: DGT 2025 orthophoto
- camera/light/render: inherited unchanged from the current terrain baseline
- MOSAIQ revision: `f73d030aecd3289007472a887d78aae2e74b6ea0`

## A/B procedure

A — current generator:
1. fetch the existing building/highway OSM payload;
2. build `bridge_output_003/coimbra-terrain-base.blend`;
3. render `bridge_output_007/current-preview.png`.

B — MOSAIQ:
1. fetch an OSM XML payload for the same bbox including buildings, roads,
   areas, crossings and POI-relevant nodes;
2. import it through the pinned MOSAIQ Blender add-on;
3. remove MOSAIQ's flat ground plane;
4. reproject imported Web Mercator geometry to EPSG:3763 local coordinates;
5. drape generated geometry onto the same pinned DGT terrain;
6. preserve the same camera, DGT terrain, orthophoto and light;
7. save `bridge_output_007/coimbra-mosaiq-ab.blend`;
8. render `bridge_output_007/mosaiq-preview.png`.

## Evidence

The artifact must include both `.blend` files, both preview images and
`mosaiq-manifest.json` with counts for buildings, roads, areas, sidewalks,
crosswalks, parking lanes, road markings and POI instances.

The public MOSAIQ repository contains the instancing logic for POIs and parked
vehicles, but does not ship the GLB asset pack itself. A zero POI/car count in
this experiment therefore does not mean the placement logic is unavailable;
it means the public asset directory is empty.

## Decision after review

Only after visual inspection should useful MOSAIQ layers be promoted into a
new contract-governed hybrid baseline. The expected first candidates are
sidewalks, crossings, parking and area/POI tagging; DGT terrain, existing PBR,
facades, vegetation, camera and APatch governance remain ours.
