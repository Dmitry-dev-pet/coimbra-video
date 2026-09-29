# SPEC-COIMBRA-SMOOTH-PITCHED-ROOFS-1

## Goal

Produce the final smooth 48-second full-route render using the corrected 019
roof geometry.

The source scene includes:
- Coimbra 010 full-city urban-quality scene;
- 012b/013 Polo II hero architecture;
- localized 014 groundcover from the 016B stack;
- 018 full-route roof material audit;
- 019 full-route real pitched-roof geometry.

## Temporal sampling

Keep the production route unchanged and sample Blender at 1440 true fractional
frames over source frames 1 through 360.

Use:
`source = 1 + (k - 1) * 359 / 1439`

No repeated frames and no optical-flow interpolation.

## Video

- 1440 actual Blender renders;
- 30 fps;
- 48 seconds;
- 1280×720;
- H.264 / yuv420p / CRF 18;
- 12 parallel shards of 120 frames.

The final artifact publishes only the MP4, five inspection stills and manifests.
