# Coimbra 035 — Visual Polish Review

## Goal

Evaluate visual improvements on top of the accepted Coimbra 032 delivery without
changing its camera path, fractional-frame timing, route speed, framing or
production geometry.

035 is review-only. It renders four isolated visual variants at five fixed
checkpoints. It does not authorize a full 1,440-frame production render.

## Accepted source

Use the exact accepted 030 v2 packed production-look scene:

- Actions run: `36720891074`;
- candidate blend SHA-256:
  `5fe8ca9e8605c6ea1908d8a814f9ad5209248c606b34ebbbb3dd47607edff881`;
- structure SHA-256:
  `c3e599c7d27547527c6d6b430b7aaed8c8103c297d93c68fc66eef0c194d02da`;
- accepted 026 prepare evidence: run `36646652931`.

The accepted delivery lane remains Coimbra 032:

- 1,440 true Blender samples;
- 60 fps;
- 24 seconds;
- output frame `k` samples
  `source = 1 + (k - 1) * 359 / 1439`;
- native camera animation remains unchanged.

## Fixed review checkpoints

Render exactly these 032 output frames:

`121, 421, 721, 1021, 1321`

They cover the route at approximately 2, 7, 12, 17 and 22 seconds while
remaining away from the animation endpoints, which avoids boundary artifacts in
the motion-blur comparison.

All variants must use the exact same evaluated camera state at every checkpoint.

## Variants

### 1. baseline

Exact accepted 032 look and Cycles settings:

- 16 samples;
- adaptive sampling enabled;
- adaptive threshold 0.08;
- denoising enabled;
- motion blur disabled;
- no world volume changes.

### 2. motion_blur

Change only motion blur.

Blender defines shutter length in frame units. 032 advances only
`359 / 1439 ≈ 0.249478805` native source-frame units per 60-fps output frame.
Therefore a 180-degree shutter for the 032 delivery is:

`0.5 × 359 / 1439 ≈ 0.124739402` source frames.

Use:

- motion blur enabled;
- position: Center on Frame;
- shutter: `0.124739402` native source frames;
- all accepted sampling/light/world settings unchanged.

### 3. atmosphere_light

Change only subtle depth atmosphere and light balance.

Use:

- homogeneous World Volume Scatter;
- density: `0.00015`;
- anisotropy: `0.18`;
- world background strength: `0.68`;
- Coimbra030_Sun energy: `1.65`;
- Coimbra030_Sun angle: `10°`;
- Coimbra030_Fill energy: `900`;
- accepted 16-sample rendering;
- no motion blur.

The accepted world volume must be unlinked before this temporary review node is
added. Remove the node and restore the original world/light values after the
variant.

### 4. quality64

Change only Cycles sampling quality.

Use:

- 64 samples;
- adaptive threshold: `0.03`;
- adaptive sampling and denoising retained;
- no motion blur;
- no atmosphere/light changes.

## Render

Use Apple Metal and the accepted 1600×1000 resolution.

Render twenty PNGs total:

- 5 checkpoints × 4 variants.

Every image receipt must record:

- variant;
- 032 output-frame number;
- exact source-frame sample;
- integer base frame and Blender subframe;
- evaluated camera state;
- SHA-256;
- byte size;
- render time.

## Review matrix

The Mac execution lane may create a labeled contact sheet for human comparison,
but the underlying 20 PNGs remain the authoritative evidence.

Recommended matrix:

- rows: the five fixed route checkpoints;
- columns: baseline / motion blur / atmosphere+light / quality64.

## Restoration and invariants

After all review renders:

- remove the temporary World Volume Scatter node;
- restore motion-blur settings;
- restore Cycles samples and adaptive threshold;
- restore world background and accepted Coimbra030 lights;
- production camera animation must match accepted 026 evidence;
- scene structure and accepted protected visual state must match the source.

035 must never save a modified production blend.

## Acceptance boundary

The Blender-free verifier must reject:

- wrong 030/026 source evidence;
- any camera or timing drift from 032;
- different camera states across variants;
- a combined variant that changes more than the documented isolated variable;
- incorrect 180-degree shutter mapping;
- wrong atmosphere/light values;
- wrong quality64 sampling;
- fewer than four visibly changed checkpoints for any non-baseline variant;
- failure to restore accepted scene state.

Passing verification means only that the A/B review is valid. Selection of a
visual treatment requires human review before any full production render.
