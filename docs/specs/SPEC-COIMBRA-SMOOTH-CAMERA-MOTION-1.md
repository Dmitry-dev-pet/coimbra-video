# Coimbra 033 — Smooth camera-motion review

## Goal

Determine whether the remaining judder in Coimbra 032 comes from camera
kinematics rather than temporal sampling.

032 already renders 1,440 real Blender samples at 60 fps / 24 seconds. 033 does
**not** increase frame count. Instead it creates a motion-only proxy candidate
that smooths the camera path while preserving the accepted production scene and
the same seven route anchors.

033 is a review lane. It must not be described as a production-look acceptance
render until the side-by-side motion comparison has been visually reviewed.

## Accepted source

Use the exact accepted 030 v2 packed scene:

- Actions run: `36720891074`;
- candidate revision: `v2-shadow-recovery`;
- blend SHA-256:
  `5fe8ca9e8605c6ea1908d8a814f9ad5209248c606b34ebbbb3dd47607edff881`;
- structure SHA-256:
  `c3e599c7d27547527c6d6b430b7aaed8c8103c297d93c68fc66eef0c194d02da`;
- accepted 026 prepare evidence: run `36646652931`.

Use the completed 032 delivery only as the visual comparison baseline:

- mac-access run: `36856154207`;
- video SHA-256:
  `7c34fd28a75d0cbb2aad76871238a0f9871439206fb43ead9f1e4e61574e05b7`.

## Frozen native camera evidence

The accepted native camera animation remains immutable. 033 may sample it and
derive a review candidate, but must not edit its keyframes or save a modified
production blend.

Use these seven source anchor frames:

`1, 61, 121, 181, 241, 301, 360`

At each anchor capture:

- world-space camera location;
- world-space orientation quaternion;
- lens;
- focus distance.

For target smoothing, derive a forward target from the accepted orientation at
each anchor. This preserves the accepted pointing direction at the anchors
without relying on Euler interpolation.

## Candidate motion model

Position:

- centripetal Catmull–Rom through the seven accepted anchor locations;
- continuous tangent through interior anchors;
- no new route waypoint chosen by the issue or runtime environment.

Direction:

- derive one target point from each accepted anchor orientation;
- centripetal Catmull–Rom through those target points;
- derive output orientation by looking from smoothed position to smoothed target;
- do not directly interpolate Euler angles.

Timing:

- build a dense spatial representation of the smoothed position spline;
- parameterize output time by cumulative arc length across the complete route;
- therefore translational distance per output frame should be approximately
  constant across segment boundaries.

Lens/focus:

- cubic interpolation through the accepted anchor values.

## Proxy

Render exactly:

- 1,440 real EEVEE proxy frames;
- 60 fps;
- 24.0 seconds;
- 960×600;
- same production materials/world/lights/color management;
- no motion blur for this first review.

Motion blur is intentionally disabled so this lane isolates camera-path smoothing
from temporal blur.

Encode:

`coimbra-033-smooth-camera-proxy-24s.mp4`

Then create:

`coimbra-033-vs-032-side-by-side.mp4`

with the accepted 032 delivery on the left and the 033 motion proxy on the right,
both shown at the same playback rate.

## Evidence

Record motion metrics for both:

1. the current 032 fractional-frame sampling of the accepted camera;
2. the 033 smoothed candidate.

At minimum record:

- per-frame translation step;
- per-frame angular step;
- absolute change in translation step;
- absolute change in angular step;
- mean, standard deviation, CV, p50, p95 and maximum.

The verifier may require the arc-length candidate to have near-constant
translational step. Angular metrics remain review evidence; they must not be
converted into an automatic visual-quality score.

## Acceptance boundary

The independent verifier must reject:

- wrong accepted source scene;
- mutation of the native camera animation or scene structure;
- changed start/end route locations;
- missing route anchors;
- wrong frame count, fps, duration or proxy resolution;
- non-monotonic route progress;
- failure to pass near every original route anchor;
- missing DGT/OpenStreetMap attribution.

Passing 033 means only that the candidate is a valid inspectable motion review.
Human visual review is still required before any full Cycles render is authorized.
