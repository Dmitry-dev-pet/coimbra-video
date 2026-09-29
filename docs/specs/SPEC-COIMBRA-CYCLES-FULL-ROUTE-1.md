# Coimbra 026 — full-route Cycles acceptance

## Scope and baseline

User-authorized on 2026-09-30: render the whole 360-frame route with the 025 Cycles backend and consolidate the accumulated branch stack. This pass is render-only, not a geometry/asset-realism change.

Pin the accepted 025 code at `d178382d10eef41ec00da3fe562fcc445438f8da` and its checkpoint artifact from run `36644592881`. Reuse its scene builder, semantic/solar-promotion rules and `configure_cycles` implementation unchanged. Compare rebuilt geometry metadata and all three camera checkpoints against the accepted manifest before freezing the prepared scene.

## Render contract

- Cycles CPU, 16 samples, denoising and adaptive sampling; exact settings inherited from 025.
- Native scene frames 1–360, 30 fps, 12 seconds. No inserted repeated frames, optical flow, retiming, camera/path edits or material edits.
- Preserve 025's 1600 × 1000 framing. Do not silently change to 16:9 or crop.
- Render twelve independent 30-frame shards from one checksum-verified packed Blender scene; hash protected geometry/material/world/light state and evaluate all 360 camera poses before and after rendering.
- Encode H.264/yuv420p and burn the existing DGT/OpenStreetMap attribution into the video. Preserve the uncropped composition.
- Decode the final MP4 with ffprobe; verify exact frame coverage, codec, resolution, duration and per-shard invariant receipts using a Blender-free verifier.
- Extract review frames 1, 181 and 360 from the encoded delivery, not from substitute still renders.

## Existing slow-motion lane

017/020 are separate 48-second, 1440-native-subframe EEVEE deliveries. Preserve their workflows and source history when integrating; 026 is the explicitly requested 360-frame backend-acceptance pass, not an overwrite of the 48-second version.

## Output

`coimbra-026-cycles-full-route`: `coimbra-cycles-full-route-12s.mp4`, decoded review stills, source/prepare manifest, twelve shard receipts, ffprobe output, attribution text and final verification JSON. No production promotion may be reported merely because a workflow was submitted.

## Tests and failure behavior

`python -m unittest discover -s scripts -p 'test_cycles_full_route.py' -v` covers valid delivery plus scene/camera mutation, missing and duplicate shards, missing frames, backend-setting drift, incorrect timing and cropped framing. A failed source comparison, invariant check, render or final verifier blocks delivery. Full renders are triggered only on the dedicated 026 branch or explicit workflow dispatch, never on every main-branch push.

The render guard supplements the existing APatch-governed source pipeline; it does not weaken or replace the generic APatch bridge or authorize edits to protected source layers. Artifact dependencies retain their original expiry; no live DGT credentials are read by this pass.
