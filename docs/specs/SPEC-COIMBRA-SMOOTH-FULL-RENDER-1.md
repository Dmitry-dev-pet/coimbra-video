# SPEC-COIMBRA-SMOOTH-FULL-RENDER-1

## Goal

Create a genuinely smoother 4× slower version of the complete Coimbra route.

The 48-second result must **not** be made by repeating frames and must **not**
use optical-flow or AI interpolation.

## Source scene

Use the accepted prepared full-city scene from Coimbra 016B, including:
- Coimbra 010 full-city urban-quality geometry;
- corrected 012b Polo II roofs/windows;
- 013 Polo II facade/balcony/roof details;
- localized 014 OSM-grounded Polo II groundcover.

Keep the production route, lighting and scene geometry unchanged.

## Temporal sampling

The original production route occupies Blender source frames 1 through 360.

Render 1440 actual images. Output frame `k` samples Blender at:

`source = 1 + (k - 1) * 359 / 1439`

Therefore:
- output 1 samples source 1.000;
- output 1440 samples source 360.000;
- adjacent output frames differ by about 0.24948 source frames.

Use Blender's native fractional-frame evaluation so constraints, Bezier
animation, drivers, focus distance and all other evaluated animation state are
sampled consistently.

## Video

- 1440 real rendered frames;
- 30 fps;
- 48 seconds;
- 1280×720;
- H.264 / yuv420p / CRF 18;
- no repeated-frame slow motion;
- no optical-flow interpolation.

Render in 12 parallel shards of 120 output frames each. Intermediate PNGs are
temporary and should not be published in the final artifact.
