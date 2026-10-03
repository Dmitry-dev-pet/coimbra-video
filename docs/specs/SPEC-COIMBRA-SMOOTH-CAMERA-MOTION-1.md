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

Render through a temporary detached proxy camera:

- duplicate the accepted camera object and camera data for review only;
- clear animation data, constraints and parent on the temporary camera;
- drive each rendered frame from the explicit 033 position/quaternion/lens/focus record;
- after every render, record the actual camera state and require it to match the intended record;
- restore the accepted production camera and remove the temporary camera before invariant checks.

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
- missing DGT/OpenStreetMap attribution;
- a proxy camera reset by Blender animation evaluation;
- excessive duplicate proxy frame hashes consistent with a static camera.

Passing 033 means only that the candidate is a valid inspectable motion review.
Human visual review is still required before any full Cycles render is authorized.


## Human review decision — 2026-10-03

The user reviewed the 033 motion model in a full 1,440-real-frame Cycles/Metal
preview and explicitly accepted the camera motion for future Coimbra full-route
renders.

Acceptance evidence:

- mac-access run: `37149136812`;
- render: 1,440 real frames, 60 fps, 24.0 s;
- review resolution: 640×480;
- Cycles samples: 4;
- adaptive threshold: 0.15;
- motion blur: disabled;
- repeated frames: none;
- optical flow: none;
- video SHA-256:
  `7153a061dd4e8ac27bc51ac5c9077c3154c6162df035a0d6953336ca9a74be27`;
- review video: https://youtu.be/ou7x35MhRSQ;
- translation-step CV measured in the acceptance run:
  `0.389748 → 0.000011`.

### Promotion boundary

This decision promotes the **033 camera-motion model only**:

- seven accepted route anchors;
- centripetal Catmull–Rom position spline;
- centripetal Catmull–Rom target spline;
- look-at quaternion orientation;
- global arc-length timing;
- cubic lens/focus interpolation.

It does not promote 640×480, 4 Cycles samples or adaptive threshold 0.15 as
production-quality settings. The accepted Coimbra 032 scene/look remains the
production visual baseline and should be combined with this accepted 033 motion
model for the next production-quality full-route render.
