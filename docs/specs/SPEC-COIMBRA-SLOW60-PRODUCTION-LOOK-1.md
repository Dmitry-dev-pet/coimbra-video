# Coimbra 032 — 60 fps half-speed production-look full route

## Goal

Create a smoother, slower delivery of the accepted Coimbra production look while
preserving the exact route and scene.

032 is a timing/sampling-only derivative of the accepted 030 v2 packed scene:

- same production route from source frames 1 through 360;
- same materials, world, lights and color management;
- same 1600 × 1000 framing;
- same Cycles quality settings;
- same Apple Metal execution backend.

## Temporal contract

Render **1440 real Blender images** by evaluating the existing route at native
fractional source frames.

For output frame `k`:

`source = 1 + (k - 1) * 359 / 1439`

Therefore:

- output 1 samples source 1.000000;
- output 1440 samples source 360.000000;
- adjacent output frames advance by about 0.24948 source frames;
- no source camera keyframe is moved or rewritten;
- no repeated-frame slow motion;
- no optical flow or AI interpolation.

## Delivery timing

- 1440 rendered frames;
- 60 fps;
- 24.0 seconds;
- same complete route as 031;
- route traversal speed = 0.5 × the 031 delivery speed;
- temporal sampling density = 4 × the 031 output frame count.

This combination is intentional: doubling FPS from 30 to 60 while quadrupling the
number of rendered samples doubles the duration from 12 to 24 seconds.

## Accepted source

Use the exact accepted 030 review artifact from Actions run `36720891074`:

- revision: `v2-shadow-recovery`;
- candidate blend SHA-256:
  `5fe8ca9e8605c6ea1908d8a814f9ad5209248c606b34ebbbb3dd47607edff881`;
- structure SHA-256:
  `c3e599c7d27547527c6d6b430b7aaed8c8103c297d93c68fc66eef0c194d02da`;
- underlying accepted 026 run: `36646652931`.

The loaded camera at all 360 integer source frames must still match the accepted
026 camera evidence before and after rendering.

## Render evidence

Record for every output frame:

- output frame number;
- exact source-frame sample;
- integer base frame and Blender subframe;
- PNG SHA-256;
- byte size;
- render time.

Group the 1440 receipts into twelve logical 120-frame shards.

## Final video

Encode:

`coimbra-production-look-slow60-metal-24s.mp4`

Requirements:

- H.264 / yuv420p;
- 1600 × 1000;
- 60 fps;
- exactly 1440 decoded frames;
- approximately 24.0 seconds;
- visible DGT and OpenStreetMap attribution.

Decode review frames 1, 361, 721, 1081 and 1440 from the final MP4.

## Acceptance

The Blender-free verifier must reject:

- source-scene drift;
- changed native camera path;
- wrong source-frame sampling;
- repeated frames or optical-flow policy;
- incomplete 1..1440 receipt coverage;
- wrong fps, frame count, duration, resolution or codec;
- missing attribution or review frames.

032 does not overwrite 031. It creates a separate accepted temporal delivery lane.
