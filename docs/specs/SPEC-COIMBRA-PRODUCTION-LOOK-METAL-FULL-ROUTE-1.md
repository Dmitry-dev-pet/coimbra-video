# Coimbra 031 — production-look Metal full route

## Goal

Promote the human-reviewed Coimbra 030 v2 production look into a complete,
verified 360-frame Apple Metal delivery without changing that accepted look.

## Accepted source

Use the exact 030 review artifact from Actions run `36720891074`.

Pinned evidence:

- candidate revision: `v2-shadow-recovery`;
- candidate blend SHA-256:
  `5fe8ca9e8605c6ea1908d8a814f9ad5209248c606b34ebbbb3dd47607edff881`;
- non-light structure SHA-256:
  `c3e599c7d27547527c6d6b430b7aaed8c8103c297d93c68fc66eef0c194d02da`;
- underlying accepted 026 run: `36646652931`;
- 360 native frames, 30 fps, 12 seconds;
- 1600 × 1000;
- accepted 16-sample Cycles settings with denoising and adaptive sampling.

The 030 packed blend is authoritative for the accepted material, world, light and
color-management state. 031 must not rebuild the 030 look from parameter guesses.

## Render boundary

031 may change only the Cycles execution device from CPU to GPU / METAL.

It must preserve:

- the exact 030 packed blend before rendering;
- non-light structure and material assignments;
- accepted materials, world and light state;
- all 360 production camera poses, lenses and timing;
- resolution and Cycles quality settings.

Before/after hashes and camera records must prove the render did not mutate the scene.

## Full-route delivery

Render frames 1 through 360 and record per-frame SHA-256, byte size and wall time.
Group evidence into twelve logical 30-frame receipts.

Encode:

`coimbra-production-look-metal-12s.mp4`

Requirements:

- H.264 / yuv420p;
- 1600 × 1000;
- 30 fps;
- exactly 360 decoded frames;
- approximately 12.0 seconds;
- visible DGT and OpenStreetMap attribution.

Decode review frames 1, 181 and 360 from the final MP4.

## Acceptance

A Blender-free verifier must reject any source drift, incomplete frame set,
wrong renderer, wrong timing/resolution, failed attribution or missing review frame.

031 establishes the accepted full-route production-look delivery. It does not
rewrite the older 026 CPU or 028 Metal baselines.
