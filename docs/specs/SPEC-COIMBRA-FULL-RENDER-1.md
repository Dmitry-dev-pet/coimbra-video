# SPEC-COIMBRA-FULL-RENDER-1 — full production-route render

> **Status:** full-route visual QA · **Source:** merged main through Coimbra 010

## Purpose

Render the complete production camera route from the accepted Coimbra 010
Urban Quality scene.

This is intentionally separate from the 011–015 Polo II photo experiments.
Those passes are local still-image experiments and are not silently propagated
to the full-city route.

## Render contract

- source: accepted Coimbra 010 Urban Quality artifact;
- frames: 1–360 inclusive;
- frame rate: 30 fps;
- duration: 12 seconds;
- resolution: 1280×720;
- renderer and scene lighting/materials: inherit from 010;
- production camera animation: unchanged;
- render the 360 frames in 12 shards of 30 frames.

## Final video

Encode the assembled PNG sequence as H.264/yuv420p, CRF 19, with fast-start.

The final video must retain attribution for:
- DGT terrain/orthophoto sources;
- OpenStreetMap contributors / ODbL.

## Outputs

Publish:
- MP4;
- five inspection stills from frames 1, 90, 180, 270 and 360;
- render manifests.

Do not publish the intermediate 360-frame PNG set after finalization.
