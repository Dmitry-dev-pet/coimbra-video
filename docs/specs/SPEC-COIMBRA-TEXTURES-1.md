# SPEC-COIMBRA-TEXTURES-1 — Coimbra PBR texture development

> **Status:** Draft v1 · **Owner:** repository
> **apatch artifact:** `spec:SPEC-COIMBRA-TEXTURES-1`

## R1 Produce an inspectable textured visual-dev scene

`COIMBRA-BRIDGE-005-TEXTURES` must preserve the approved 004 camera path,
camera DOF, lighting and 360-frame timing while replacing the flat generated
building/road materials in the reproducible base scene with a small CC0 PBR
material set.

Texture base preparation is deterministic and happens before the governed
Blender plan. The resulting packed textured `.blend` is the baseline hashed
into the APatch SDD session. From that point onward protected `City_*`
geometry, animation, material assignments and selected scene provenance
metadata must remain unchanged.

The output must include:

- an inspectable governed `.blend`;
- preview frames 1 / 181 / 360;
- the texture download and packed-material manifests;
- a passing semantic verification report.

Do not render the full 360-frame movie during ordinary texture iteration.

(verify: python3 scripts/verify_texture_dev_evidence.py --report bridge_output_005/texture-verification.json --probe verification/COIMBRA-BRIDGE-005-TEXTURES.probe)

## Material source

The 1K PBR source set is declared in
`textures/COIMBRA-005-polyhaven.json`. Assets are CC0. The CI downloader uses
the official Poly Haven API and records source URLs plus checksums for the
downloaded maps. The project credits the API as Powered by Poly Haven.

## Visual target

- retain the approved 004 miniature/golden-hour camera and light;
- visible plaster variation across building walls;
- visibly terracotta/weathered roofs instead of flat roof colors;
- asphalt on major/local roads;
- stone paving on service/path surfaces;
- texture detail should read at drone distance without making the city noisy.
