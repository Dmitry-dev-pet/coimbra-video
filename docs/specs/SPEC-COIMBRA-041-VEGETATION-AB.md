# Coimbra 041 — source-anchored Polo II vegetation A/B/A

## Goal
Refine harsh polygonal foliage in a bounded Polo II pedestrian view of the accepted Coimbra 032/037 city without changing original saved Blender scene, glTF buffers or distant city geometry. This is a reversible **diagnostic visual experiment**, stacked on Coimbra 040 and 039.

## Source and bounds
- SHA-256-pinned accepted 032/037 GLB: `c02e245f6c59e5f3ec7999b00c8bfb7acc4f96cc8a6d893f708c060757bb8dfd`.
- Original `Semantic_Canopy_Masses`, `Semantic_Trees` foliage (no trunk removal) and `Semantic_Undergrowth` material-split meshes are the sole sources. Never add tree centers manually or derive trees from unrelated nearby OSM road points.
- Polo II bounds: local X/Z centered at (-168.37,+748.07), 220 x 220 m, with 12 m margin. Only complete source-connected crown components fully inside the inner 196 x 196 m are eligible.
- Each component is reconstructed through the **original indexed triangles** and its world bbox; reject trunks, degenerate triangles, very small/large components and any piece crossing the safety boundary.
- Browser candidate is a set of five deterministic, smaller smooth lobe instances around each accepted bbox. Colors are deliberately restrained illustrative foliage palettes, **not** an assertion of surveyed tree species, shading or exact crowns.

## How the accepted model is protected
- Original `BufferGeometry` objects, `BufferAttribute` arrays, original materials and the published `.glb` on Pages stay untouched.
- Each eligible vegetation mesh gets a temporary **new index buffer** that removes only inside-bounds complete original crown components. All source triangles outside the bounded patch are retained exactly, with the same original attributes.
- Candidate instances live in a separately named removable group. On toggle-off, returning to aerial or switching out of Polo II, restore the exact original mesh geometry reference and hide candidate instances. No disposal of original buffers or alteration of glTF file bytes.
- This temporary **runtime mesh.geometry pointer swap** is allowed for QA only. It is distinct from production scene mutation, which remains prohibited.
- Candidate is only available when Coimbra 040's bounded visual pass is active, avoiding visible effects elsewhere in the scene.

## A/B/A and constraints
- Use the same Coimbra 039 camera at 1.70 m above original `City_Terrain`, and unchanged pose/quaternion across all three screenshots: 040 baseline, 041 candidate, restored 040 baseline.
- Chrome headless software renderer with explicit WebGL2 fallback and QA-only adapted 8192px orthophoto is a diagnostic medium. No claim of WebGPU parity or Mac M4 frame rate.
- Run source topology inventory separately; browser QA fails on absent semantic meshes, out-of-bounds replacement, no real crown components, and failed restoration.
- Verify distinct, nonblank candidate pixels outside HUD and near-exact restoration to original camera-identical image. Save a contact sheet and JSON receipts, two-day Actions artifact retention.
- All outputs require human visual review; tests measure **structural correctness** and visible differences, not photorealism or pleasantness.

## Visual caveats and next gate
Rounder vegetation can still look artificial. Software-GPU material response may be unstable; QA includes an unlit diagnostic foliage swatch to avoid washed-out whites. No pedestrians, roads, trees elsewhere, weather, photogrammetry or original lighting outside Coimbra 040 are changed. Do not merge, deploy Pages or replace accepted scenes until the A/B images have been inspected and explicitly approved.
