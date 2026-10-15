# Coimbra 039 — Ground-level Street QA for the accepted 037 browser scene

## Goal

Inspect the existing accepted Coimbra 032 / frame-181 GLB in the 037 browser viewer at human eye height, without mutating the Blender source scene or replacing the 034, 037 or 038 paths.

## Source and geographic placement

- Reuse the immutable 037 GLB and its existing WebGPURenderer.
- Reuse the three street QA *anchor/direction pairs* from Coimbra 010: Sanches/Brasil, Polo II and Portela.
- Match each anchor against the nearest non-path OSM road segment in existing static Coimbra 034 tiles (3×3 tile neighborhood). Use the closest point on the road centreline and apply the historical 010 lateral camera offset of 0.85 m.
- Refuse an anchor if its nearest verified road is more than 80 m away. Do not invent a road or take a camera pose from a building centroid.
- Sample ground by raycasting against the **exported City_Terrain object only**, not against buildings or rooftops. Fail visibly if absent or if the position has no ground intersection.
- Camera eye: 1.70 m above City_Terrain; glTF conversion is (X, Blender Z, -Blender Y). The source accepted GLB and its materials remain untouched.

The 034 road dataset is a positioning aid, *not* a replacement for accepted 032/037 city geometry.

## Browser UI

037 remains in its reference frame-181 aerial orbit view by default.

- Pick Sanches/Brasil, Polo II or Portela and enter Street QA.
- Drag to look around; WASD for slow movement (~2.2 m/s), Shift for brisk movement; maximum 45 m from the current QA entry point.
- Walking tracks City_Terrain periodically; steep discontinuities and missing ground stop movement. It is a visual QA controller, **not a collision-accurate pedestrian simulator**.
- Return to aerial restores the previous view; Reset frame 181 restores the original production camera. Frame-181 comparison still works in aerial mode.
- URL query for deterministic inspection: /037/?streetQA=sanches-brasil, ?streetQA=polo-ii or ?streetQA=portela.

## Evidence

"Save PNG + JSON" attempts to save one actual browser canvas frame plus a machine-readable receipt: selected point, OSM-road snap distance, actual three.js camera transform, 1.70 m eye-height target, viewport, frame-time mean and p95, and FPS estimate. The source of evidence is the browser, not the offline Cycles frame.

If WebGPU cannot export a canvas PNG, show an explicit failure rather than pretending a screenshot exists. The user should check downloaded images for blank WebGPU frames before accepting them.

Visual review must check facades/windows, road-to-sidewalk edges, floating/intersecting objects, terrain discontinuities, and whether the location invites walking. Flat/lightly textured city geometry may be acceptable for an aerial miniature but is not yet street QA acceptance.

## Guards and verification

- Do not edit or re-render the accepted 030/032 .blend, camera motion, or production-look contracts.
- Do not change /038/ (scripted route) or replace /034/ root.
- Keep human review gating. Street QA is diagnostic only, not a promotion of browser parity.
- Run the lightweight road projection tests locally or on the existing self-hosted Mac (Node 22). Do not run the heavy hosted-Linux 038 Pages job merely to validate this change.
- The historical 010 screenshots existed in run 36543166578 but were not available from current Actions artifact queries after storage cleanup. New PNG evidence must be captured against the current deployed or locally served accepted GLB before any visual verdict.
