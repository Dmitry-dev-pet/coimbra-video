# Coimbra 030 — production-look review

## Goal

Improve the visible full-route Coimbra look without rebuilding geometry or spending a
full-route render on an unreviewed grade.

030 starts from the exact accepted 026 frozen scene and creates paired review frames
for the accepted baseline and one deterministic candidate look. Promotion remains a
human visual-review decision.

## Frozen source

Use the accepted 026 prepared artifact from run `36646652931`.

Required source evidence:

- packed blend SHA-256:
  `5eed3da289693015ed6b491eb26f992f0c579a1625540f1f4acc13155860a590`;
- protected 026 state SHA-256:
  `98ee88d4c6e28dfccb010b7ad9faa89f88466768eed7ec440fb96d99b276450f`;
- production route: frames 1–360, 30 fps;
- resolution: 1600 × 1000;
- Cycles: accepted 16-sample / denoise / adaptive settings.

## Allowed visual changes

030 may change only:

- simple semantic vegetation and hardscape material values named in the 030 palette;
- world Background color/strength;
- lighting objects and light data;
- Blender color-management view/look/exposure.

030 must not change:

- mesh vertices, edges, topology or UVs;
- object transforms for non-light objects;
- material assignments;
- production camera object, camera animation, lens or route timing;
- semantic evidence or source-data files;
- output framing or Cycles quality settings.

## Candidate look

The first candidate deliberately reuses the lighting direction already proven in the
Polo II photo-patch work:

- cool blue ambient world;
- warm, soft 8-degree sun;
- broad cool fill;
- slightly muted semantic vegetation;
- neutral-dark parking;
- AgX contrast with a restrained exposure lift.

This is a review candidate, not a claim that the look is accepted.

## Review output

Render paired baseline/candidate Cycles frames:

- 1;
- 181;
- 360.

Produce:

- six full-resolution PNGs;
- one side-by-side comparison sheet;
- `production-look-review.json`;
- `production-look-verification.json`;
- the candidate `coimbra-production-look.blend`.

The verifier checks structural/camera invariants and confirms a bounded pixel delta.
Pixel metrics are guardrails only and must never be treated as a visual-quality score.

## Promotion boundary

030 is complete when the review artifact is reproducible and verified.

Do not render or publish a full 360-frame candidate movie until a human review chooses
to promote the candidate. A promoted full-route render must be a separate follow-up lane.
