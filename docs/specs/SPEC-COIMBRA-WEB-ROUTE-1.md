# Coimbra 038 — accepted 032 full camera route in browser

## Goal

Run the accepted Coimbra 032 production route directly in the browser while
preserving the exact scene geometry and exact 032 temporal camera sampling.

038 builds on the 037 accepted-scene GLB. It must not regenerate Coimbra from
OSM/DGT boxes and must not alter the accepted 030/032 scene.

## Frozen source

Use the accepted Coimbra 030 production-look artifact from Actions run
`36720891074`:

- artifact: `coimbra-030-production-look-review`;
- packed scene: `coimbra-production-look.blend`;
- expected SHA-256:
  `5fe8ca9e8605c6ea1908d8a814f9ad5209248c606b34ebbbb3dd47607edff881`.

The browser geometry remains the 037 static frame-181 GLB exported from this
same packed scene.

## Exact 032 route contract

The camera route is sampled in Blender with the same 032 formula:

`source = 1 + (k - 1) * 359 / 1439`

for output frames `k = 1..1440`.

Required delivery:

- 1440 Blender-evaluated camera samples;
- 60 fps;
- 24.0 seconds;
- source range 1..360;
- no repeated-frame slow motion;
- no optical flow;
- camera matrix and vertical field of view recorded for every sample.

The exporter also records an exact source-frame-181 camera anchor. The web
viewer uses that anchor to align Blender world matrices to the coordinate
conversion of the imported glTF camera.

## Browser playback

The viewer lives at `/038/` and:

- reuses `/037/data/coimbra-032-frame181.glb`;
- loads `coimbra-032-camera-route.json`;
- advances through the 1440 exact samples at 60 fps;
- loops after the full 24-second route;
- offers pause/play, restart, timeline scrubbing and exact frame-181 reference
  comparison;
- preserves the 1600:1000 camera aspect.

## Production-look approximation

glTF does not carry Blender world shading or Blender color-management settings
verbatim. 038 therefore explicitly restores the accepted 030/032 intent where
the browser can represent it cheaply:

- AgX tone mapping;
- exposure +0.28 (browser exposure multiplier `2^0.28`);
- accepted cool world background;
- a broad cool ambient fill approximation;
- exported production glTF lights remain active.

This is a parity approximation, not a claim of pixel-identical Cycles output.

## Deployment boundary

The combined GitHub Pages site must preserve:

- 034 at the Pages root;
- 037 at `/037/`;
- 038 at `/038/`.

038 owns automatic Pages deployment after merge to `main`. Older workflows
may still build but must not race 038 with an automatic Pages deployment.

## Acceptance

038 is complete when CI verifies:

- the frozen source blend hash;
- valid GLB container;
- exactly 1440 route samples;
- 60 fps / 24.0 second route contract;
- source endpoints 1.0 and 360.0;
- exact frame-181 anchor;
- the combined site contains root 034, 037 and 038 assets;
- the Pages deployment succeeds.

Human review then decides whether lighting/color parity is sufficient for the
next browser-quality pass.
