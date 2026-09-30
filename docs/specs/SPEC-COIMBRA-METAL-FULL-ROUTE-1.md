# Coimbra 028 — full-route Apple Metal acceptance

## Goal

Render the entire accepted Coimbra 026 route on the dedicated Mac M4 using
Cycles GPU / Metal while preserving the exact frozen 026 scene and production
camera.

028 is a new delivery lane. It does not rewrite or invalidate the accepted 026
Cycles CPU baseline.

## Frozen source

Use the exact accepted 026 prepared artifact from Actions run `36646652931`.

Required evidence:

- packed scene SHA-256:
  `5eed3da289693015ed6b491eb26f992f0c579a1625540f1f4acc13155860a590`;
- protected scene-state SHA-256:
  `98ee88d4c6e28dfccb010b7ad9faa89f88466768eed7ec440fb96d99b276450f`;
- accepted 025 source:
  `d178382d10eef41ec00da3fe562fcc445438f8da`;
- 360 native frames;
- 30 fps / 12 seconds;
- 1600 × 1000.

Do not rebuild or edit geometry, materials, semantic evidence, world/light state
or camera animation.

## Render backend

Keep the accepted 026 Cycles settings:

- 16 samples;
- denoising enabled;
- adaptive sampling enabled;
- accepted bounce limits and adaptive threshold.

Change only the execution device from CPU to GPU / METAL.

At least one actual Cycles `METAL` device must be detected and recorded.

## Full-route render

Render native integer frames 1 through 360.

For evidence, group receipts into twelve logical 30-frame shards. Each receipt
must contain:

- exact start/end frame;
- per-frame SHA-256;
- per-frame byte size;
- per-frame wall-clock render time;
- shard wall-clock time.

The full render also records total wall-clock rendering time.

## Invariants

Before and after rendering:

- frozen blend SHA matches 026;
- protected scene-state SHA matches 026;
- all 360 production camera records match 026;
- resolution remains 1600 × 1000;
- render settings remain the accepted 026 values except CPU -> GPU/METAL.

A failed invariant blocks delivery.

## Delivery

Encode the 360 rendered PNGs into:

`coimbra-metal-full-route-12s.mp4`

Requirements:

- H.264;
- yuv420p;
- 1600 × 1000;
- 30 fps;
- exactly 360 decoded frames;
- approximately 12.0 seconds;
- visible DGT/OpenStreetMap attribution.

Extract review frames 1, 181 and 360 from the encoded delivery.

## Acceptance

A Blender-free verifier validates the render receipt and decoded MP4 metadata.

028 acceptance establishes that the complete frozen 026 route can be rendered
through the Agent Hub L5 Mac backend on Apple Metal. It does not by itself
remove the 026 CPU baseline; promotion to a preferred renderer is a separate
project decision.
