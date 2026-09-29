# SPEC-COIMBRA-FULL-RENDER-NEW-GEOMETRY-1

## Goal

Render the complete 360-frame production route with the newest validated
building geometry included where it actually exists.

## Scene composition

- full-city source remains the accepted Coimbra 010 Urban Quality scene;
- integrate the corrected 012b + 013 architecture for the four validated Polo
  II OSM buildings:
  - 143294113
  - 143294117
  - 143294126
  - 379862984
- also integrate the localized 014 OSM-grounded green-ground / shrub / grass geometry inside Polo II;
- preserve the Coimbra 010 production camera animation exactly;
- preserve 010 lighting and full-city environment outside the local patch;
- do not apply the photo-specific 014 lighting treatment or global sidewalk/curb material treatment;
- do not apply the still-image 015 post-render grade to the animation.

The temporary 011 photo camera may be reconstructed only to make the localized
geometry deterministic. It must be deleted before the full-render scene is
saved.

## Render

- frames 1–360;
- 30 fps;
- 12 seconds;
- 1280×720;
- 12 parallel shards of 30 frames;
- H.264 / yuv420p / CRF 19.

## Review

Publish the MP4 plus stills at frames 1, 90, 180, 270 and 360. Intermediate
frame shards are not part of the final artifact.
