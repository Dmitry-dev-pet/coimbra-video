# SPEC-COIMBRA-HIGHRES-TERRAIN-1 — high-resolution terrain integration

> **Status:** Draft v1 · **Owner:** repository
> **apatch artifact:** `spec:SPEC-COIMBRA-HIGHRES-TERRAIN-1`

## R1 Integrate DGT 50 cm terrain derivatives into the miniature scene

`COIMBRA-BRIDGE-008C-HIGHRES-TERRAIN` starts from the successful 008A scene
with orthophoto-detected vehicles and replaces the legacy 6 m render terrain
with the DGT high-resolution dataset prepared by 008B.

The authoritative sources are the exact cropped DGT `MDT-50cm` and
`MDS-50cm` products. Blender uses the derived 2 m bare-earth grid for practical
rendering while preserving explicit source-resolution metadata.

Before APatch session start the preparation step must:
- replace `City_Terrain` with the 2 m grid derived from `MDT-50cm`;
- preserve the existing DGT orthophoto terrain material/UV coverage;
- vertically reproject generated city/building/road/facade/vegetation/detail
  geometry by the local delta between the legacy 6 m terrain and new 2 m terrain;
- reject implausible vertical deltas greater than 5 m rather than silently
  moving assets;
- retain the 1 m max-pooled `MDS-MDT` height-above-ground dataset as evidence
  for later tree/building height calibration;
- preserve the approved camera, DOF, lighting, materials, route and 008A cars.

The resulting high-resolution scene becomes the APatch baseline. From session
start onward all protected city/facade/vegetation/detail state and highres
metadata must remain unchanged.

Normal visual iteration renders only frames 1 / 181 / 360, not the full movie.

(verify: python3 scripts/verify_highres_terrain_evidence.py --report bridge_output_008c/highres-terrain-verification.json --probe verification/COIMBRA-BRIDGE-008C-HIGHRES-TERRAIN.probe)
