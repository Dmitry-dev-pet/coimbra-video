# SPEC-COIMBRA-SEMANTIC-OBJECTS-1

## Goal

Add real-world semantic objects that are visually important from the aerial
camera without returning to procedural random placement.

023 adds:
- photovoltaic arrays detected from DGT orthophoto with Grounding DINO;
- OSM parking polygons;
- OSM sports / pitch / track / playground polygons.

The existing 022 semantic vegetation, pools and corrected 019 roof geometry are
preserved.

## Evidence

Solar:
- DGT Orthophotos 2025 RGB;
- deterministic OpenCV color/shape detection constrained to OSM building footprints;
- dark blue / blue-gray / near-black rectangular roof components are candidates;
- OSM solar features may be used as authoritative supplements;
- large dark roof membranes and shadows are rejected by rectangularity, area and color checks.

Parking / sports:
- pinned OSM semantics from the 009A artifact;
- only polygons in the 023 review crop are generated.

## Rendering

- start from accepted 019 corrected-roof full scene;
- rebuild the 022 evidence-based vegetation/pool layers;
- remove legacy procedural `Detail_Solar`;
- build semantic solar, parking and sports geometry;
- exclude semantic vegetation from parking/sports polygons;
- choose a production-route frame that maximizes visible semantic objects;
- render exactly one 1600×1000 PNG.

The user-facing artifact contains the PNG only.
