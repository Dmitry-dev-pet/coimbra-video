# SPEC-COIMBRA-SEMANTIC-OBJECTS-1

## Goal

Add real-world semantic objects that are visually important from the aerial
camera without returning to procedural random placement.

023 adds:
- photovoltaic-array candidates detected from DGT Orthophotos 2025 with deterministic OpenCV, OSM building footprints and OpenEarthMap building segmentation;
- OSM parking polygons;
- OSM sports / pitch / track / playground polygons.

The existing 022 semantic vegetation, pools and corrected 019 roof geometry are
preserved.

## Evidence

Solar:
- DGT Orthophotos 2025 RGB;
- pinned OpenEarthMap FasterSeg building segmentation gates OSM building footprints before candidate extraction;
- deterministic OpenCV color/shape/edge analysis keeps a broad QA candidate set;
- large highly blue, textured rectangular arrays have a separate conservative path so genuine roof-scale arrays are not lost;
- only high-confidence candidates are marked `production_ready`;
- Blender places non-OSM candidates only when a downward ray hits `City_Buildings` on a roof-facing surface;
- OSM solar features may be used as authoritative supplements;
- QA evidence includes the full detection JSON, orthophoto overlay, contact sheet and summary counts.

Parking / sports:
- pinned OSM semantics from the 009A artifact;
- only polygons in the 023 review crop are generated.

## Rendering

- start from accepted 019 corrected-roof full scene;
- rebuild the 022 evidence-based vegetation/pool layers;
- remove legacy procedural `Detail_Solar`;
- build only `production_ready` semantic solar plus parking and sports geometry;
- exclude semantic vegetation from parking/sports polygons;
- choose a production-route frame that maximizes visible semantic objects;
- render exactly one 1600×1000 PNG.

The review-render artifact contains the PNG only. A separate QA artifact keeps the
solar overlay, candidate contact sheet, summary and full candidate JSON.
