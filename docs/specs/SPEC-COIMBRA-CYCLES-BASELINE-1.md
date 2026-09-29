# SPEC-COIMBRA-CYCLES-BASELINE-1

## Goal

Validate the Cycles + denoise result from Coimbra 024 across the production route
before treating it as the preferred final-render backend.

## Source

- stacked on `feature/coimbra-024-render-backend-ab`;
- exact 024 source commit:
  `d5583af1a837c6a3a0831f42ffdc667abd6b37ab`;
- accepted corrected-roof scene from Coimbra 019;
- the same 022/023 semantic vegetation and semantic-object derivation used by 024.

## Invariants

025 is a render-backend validation pass only.

It must not:
- change production camera animation;
- change geometry;
- change materials;
- change semantic-object evidence;
- change solar promotion rules;
- change route timing.

The only intended render difference is the backend/settings used for the final still.

## Route checkpoints

Render the established route review frames:

- 1 — route start;
- 181 — route midpoint;
- 360 — route end.

For every checkpoint, render both:

1. current 023 EEVEE path;
2. Cycles CPU, 16 samples, denoise enabled, adaptive sampling enabled.

Resolution: 1600 × 1000.

## Evidence

The workflow must emit:

- six PNG files (EEVEE + Cycles for each checkpoint);
- one 2×3 comparison sheet;
- one render manifest containing exact camera state and backend settings;
- one metrics JSON with basic luminance/dark-pixel measurements.

The verifier checks identity of the frame set, source commit, image dimensions,
Cycles sample/denoise settings, and that paired outputs are genuinely distinct.

025 does not merge or rewrite the production scene. Promotion of Cycles to the
full-route production renderer is a separate decision after visual review.
