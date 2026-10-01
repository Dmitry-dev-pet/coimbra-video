# Coimbra 036 — reviewed quality64 full-route delivery

## Goal

Promote only the **quality64** treatment reviewed in Coimbra 035 to a complete
production delivery while preserving the accepted Coimbra 032 route, timing,
camera, scene and look.

036 does not promote the Coimbra 035 motion-blur or atmosphere/light variants.

## Human-review source

The production choice is based on the verified Coimbra 035 visual-polish review:

- mac-access Actions run: `36892916114`;
- reviewed coimbra-video source:
  `5a76e767d8b95578a9e999b4803176812a78b3a6`;
- five fixed checkpoints: `121, 421, 721, 1021, 1321`;
- selected treatment: `quality64`;
- rejected for production in this lane: `motion_blur`, `atmosphere_light`.

The selected treatment changes only Cycles sampling quality:

- samples: **64**;
- adaptive threshold: **0.03**;
- adaptive sampling retained;
- denoising retained;
- motion blur disabled;
- world, lights and atmosphere unchanged.

## Temporal contract

Reuse Coimbra 032 exactly:

- 1,440 real Blender fractional-frame evaluations;
- 60 fps;
- 24.0 seconds;
- source route 1.0 through 360.0;
- output frame `k` samples
  `1 + (k - 1) * 359 / 1439`;
- no repeated frames;
- no optical flow;
- no camera-keyframe rewrite.

## Accepted source

Use the same accepted Coimbra 030 v2 packed scene as 032/035:

- run: `36720891074`;
- blend SHA-256:
  `5fe8ca9e8605c6ea1908d8a814f9ad5209248c606b34ebbbb3dd47607edff881`;
- structure SHA-256:
  `c3e599c7d27547527c6d6b430b7aaed8c8103c297d93c68fc66eef0c194d02da`;
- underlying 026 evidence: run `36646652931`.

## Render

Use Apple Metal at 1600×1000.

Record every output frame with its exact source sample, base frame, subframe,
SHA-256, byte size and render time. Group receipts into twelve logical
120-frame shards.

The renderer must restore the accepted 16-sample / 0.08 source sampling state
after the render and must never save a modified production blend.

## Delivery

Encode:

`coimbra-production-look-slow60-quality64-metal-24s.mp4`

Requirements:

- H.264 / yuv420p;
- 1600×1000;
- 60 fps;
- exactly 1,440 decoded frames;
- approximately 24.0 seconds;
- DGT/OpenStreetMap attribution.

Decode review frames 1, 361, 721, 1081 and 1440 from the final MP4.

## Acceptance

The Blender-free verifier must reject:

- any source, scene, camera or temporal drift from Coimbra 032;
- anything other than 64 samples / adaptive threshold 0.03;
- motion blur or atmosphere/light promotion;
- missing 035 review provenance;
- incomplete 1..1440 frame receipts;
- wrong codec, resolution, fps, frame count or duration;
- missing attribution or decoded review frames.

Passing 036 establishes a separate quality64 production delivery and leaves
accepted Coimbra 032 unchanged.
