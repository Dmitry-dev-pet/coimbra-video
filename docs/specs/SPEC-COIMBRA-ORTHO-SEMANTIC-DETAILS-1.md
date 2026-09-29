# SPEC-COIMBRA-ORTHO-SEMANTIC-DETAILS-1

## Goal

Increase real-world detail density from open data instead of manually copying
Google imagery.

The first semantic-detail pass targets the two missing visual classes that are
most obvious in the current renders:

- individual tree crowns;
- swimming pools.

## Sources

- DGT Orthophotos 2025 RGB, 25 cm / px, CC BY 4.0;
- DGT LiDAR 2024–2025 height-above-ground grid, 1 m;
- OpenEarthMap lightweight FasterSeg model from
  `cliffbb/oem-lightweight`, pinned at
  `8b301688b870f0eb8a5b93337ca3bc90a28734c4`.

The OpenEarthMap model is trained for 0.25–0.5 m aerial/satellite imagery and
provides the classes used here: `tree` and `water`.

Google Maps/Earth is not scraped or used to build the semantic dataset.

## Trees

1. Segment OpenEarthMap `tree` pixels at 0.5 m model resolution.
2. Intersect the semantic tree mask with DGT LiDAR HAG > 2.2 m.
3. Find local HAG maxima and deduplicate tree centers at ~3.2 m.
4. Replace the old sparse OSM-sampled `Vegetation_Trees` mesh with one
   consolidated semantic tree mesh.
5. Use LiDAR HAG as tree height and semantic canopy extent to estimate crown
   radius.

## Pools

1. Segment OpenEarthMap `water` pixels.
2. Extract connected components.
3. Keep compact components between 8 and 900 m² with a blue/cyan aerial-color
   signal and low LiDAR HAG.
4. Convert the detected outline into a water polygon plus a narrow coping rim.

## Review

Start from the accepted 019 corrected-roof full scene.

Render exactly one 1600×1000 PNG. Prefer a production-route frame that contains
a detected pool and many semantic trees. If the production route never sees a
pool, create a temporary inspection camera near the largest detected pool.

The user-facing artifact contains the PNG only.
