# Coimbra 027 — Mac Metal checkpoint A/B

## Goal

Measure Apple Metal rendering against the accepted Coimbra 026 Cycles CPU baseline
without changing scene content or promoting a new production renderer prematurely.

027 is a render-only experiment.

## Frozen source

Use the exact accepted 026 prepared artifact from Actions run `36646652931`.

Required evidence:

- packed scene SHA-256:
  `5eed3da289693015ed6b491eb26f992f0c579a1625540f1f4acc13155860a590`;
- protected scene-state SHA-256:
  `98ee88d4c6e28dfccb010b7ad9faa89f88466768eed7ec440fb96d99b276450f`;
- accepted 025 source:
  `d178382d10eef41ec00da3fe562fcc445438f8da`;
- native resolution: 1600 × 1000;
- checkpoints: frames 1, 181 and 360.

Do not rebuild geometry, semantic evidence, materials, world/light state or camera
animation in this lane.

## A/B render

On the dedicated Mac L5 runner, Blender 5.2.2 LTS renders each checkpoint twice:

1. accepted Cycles CPU settings from 026;
2. the same settings with only the execution device changed to Cycles GPU / Metal.

The Metal pass must detect at least one actual `METAL` device.

Record per-frame and total wall-clock render time for both modes. A speedup is a
measurement, not an acceptance requirement.

## Visual comparison

Compare the raw CPU and Metal PNGs at identical dimensions.

For each checkpoint record:

- normalized mean absolute pixel difference;
- normalized RMS pixel difference;
- maximum channel difference;
- an amplified difference image for review.

The automated guard is intentionally broad: mean difference <= 0.08 and RMS <= 0.15.
It is designed to reject grossly different/blank/wrong-camera renders, not to claim
bit-identical CPU/GPU output.

## Invariants

Before and after both render passes:

- packed scene checksum matches the accepted 026 scene;
- protected geometry/material/world/light state hash remains unchanged;
- all 360 production camera records remain unchanged;
- samples stay at 16;
- denoising and adaptive sampling stay enabled;
- resolution stays 1600 × 1000.

027 must not modify 026 or change its accepted CPU production contract.

## Promotion

Passing 027 checkpoints proves that the frozen 026 scene can be rendered on Apple
Metal with bounded visual drift and measured performance.

It does **not** promote Metal to the full 360-frame production renderer.

A full-route Metal delivery is a separate follow-up decision after actual checkpoint
images and timing evidence are reviewed.
