# Coimbra 037 — Web visual parity from accepted 032 scene

## Goal

Build the browser version from the same accepted production scene that feeds
Coimbra 032 instead of rebuilding the city from coarse DGT/OSM primitives.

Coimbra 032 remains the canonical production baseline. Coimbra 034 remains the
WebGPU feasibility prototype. 037 is a separate visual-parity candidate and must
not replace either baseline until direct human review.

## Frozen source

Use the accepted Coimbra 030 production-look artifact from Actions run
`36720891074`:

- artifact: `coimbra-030-production-look-review`;
- packed scene: `coimbra-production-look.blend`;
- expected SHA-256:
  `5fe8ca9e8605c6ea1908d8a814f9ad5209248c606b34ebbbb3dd47607edff881`;
- reference still: `frame-181-candidate.png`.

032 is a timing/sampling derivative of this exact production-look scene, so the
packed 030 scene is the correct geometry/material source for web parity.

## First deliverable

Export one static GLB at source frame 181 with:

- all render-visible city mesh/curve objects;
- production materials and packed image textures where glTF supports them;
- the production camera at frame 181;
- production lights that can be represented by glTF;
- no new OSM extrusion, no HAG reconstruction and no Sketchfab/V2 geometry.

The exporter must emit a manifest with source hash, object/material counts,
geometry counts, camera state, GLB size and GLB SHA-256.

## Browser review

The 037 viewer lives at `/037/` and loads only the exported accepted-scene GLB.
It uses the exported frame-181 camera by default and keeps a toggleable copy of
the accepted Blender frame-181 PNG as an exact visual reference.

The comparison viewport is locked to 1600:1000 aspect ratio so framing changes
are not confused with geometry/material differences.

## Deployment boundary

The existing 034 site remains at the Pages root while 037 is under `/037/`.
The combined Pages deployment must include both 034 data and 037 assets.

Once 037 owns the combined Pages deployment, the 034 workflow may still build
and benchmark its prototype but must not race 037 by automatically publishing a
second incomplete Pages artifact from the same push.

## Acceptance

037 is not promoted by CI success alone. Human review must confirm that:

- the browser clearly depicts the same Coimbra scene as 032;
- frame-181 composition is materially aligned with the accepted reference;
- roofs, terrain, facade representation, vegetation and details come from the
  accepted production scene rather than regenerated OSM boxes;
- material differences are understood and bounded;
- the GLB remains practical to load in a normal desktop browser.

Only after the first still reaches acceptable parity may 037 add the 032 route
animation and browser-specific LOD/streaming.
