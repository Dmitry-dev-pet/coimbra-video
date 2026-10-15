# Coimbra 040 — Polo II visual A/B at street level

## Goal
Test a bounded, temporary look improvement on the accepted Coimbra 032/037 GLB from a 1.7-meter camera. This is visual research, not a replacement of the production scene or renderer.

## Scope and source
- Exactly 220 × 220 meters, centered on the historic Coimbra 011 Polo II point in local EPSG:3763 (-168.37, -748.07); in three.js that is (-168.37, +748.07) in X/Z.
- Use accepted source GLB SHA-256 c02e245f6c59e5f3ec7999b00c8bfb7acc4f96cc8a6d893f708c060757bb8dfd; no regeneration or mutation of its geometry/materials.
- Temporary facade overlay: original near-vertical City_Buildings triangles whose vertices are all inside the bounding square, muted plaster colors. These colors are illustrative, not surveyed real façade materials.
- Temporary road strips: existing published Coimbra 034 OSM road data, with every vertex snapped to original imported City_Terrain. Drop segments lacking valid ground or with steep discontinuities. Widths are illustrative, not a real surveyed boundary.
- Temporary balanced sky fill, lower exposure, less severe inherited directional lighting and light fog. Original lights, fog, background and exposure restored on exiting the patch.

## Interaction
Open /037/?streetQA=polo-ii&qaBackend=webgl&poloLook=before and toggle 'Polo II: visual candidate'; use poloLook=after for an initial candidate state. This is explicit browser QA only; default /037/ must remain unchanged. The /034/ and /038/ pages are out of scope.

## Verification
- Node road-projection tests and TypeScript/Vite typecheck/build.
- A/B captures in the same browser session at exactly the same camera pose, baseline and candidate. Confirm overlay facade/road counts, unchanged original GLB, and restoration of baseline when moving to Portela.
- Compare the non-HUD image region for actual differences, reject blank frames, save PNGs, contact sheet and machine-readable receipt. Artifacts expire after two days.
- Human review of the visual results is mandatory. Image pixel difference is NOT evidence of visual improvement. CI software-GPU screenshots with QA-only oversized texture downsampling are NOT WebGPU parity or Mac M4 FPS evidence.

## Deliberate exclusions
No invented buildings, sidewalks, crosswalks, NPCs, cars, foliage dataset or photogrammetry in this pass. Existing crude vegetation in Polo II remains a known problem to be evaluated separately. Keep any new PR as draft and do not merge to main or deploy Pages without explicit review.
