# Coimbra OpenTTD agent contract

This subtree is an independent OpenTTD experiment. It must not mutate, replace, or
promote the accepted Coimbra Blender 032 scene/look or 033 camera-motion baseline.

## COIMBRA-OPENTTD-001

Goal: produce a first real-world Coimbra geodata pack that OpenTTD's Scenario
Editor can import.

Allowed inputs:
- `data/processed/bridge_terrain_6m.npz`
- `data/processed/bridge_terrain_6m.json`
- public OpenStreetMap data queried through Overpass
- explicit town/district coordinates in `openttd/config/coimbra-openttd-001.json`

Required outputs:
- `coimbra-heightmap.png`: square 8-bit grayscale PNG
- `coimbra-towns.json`: OpenTTD town import JSON using normalized/swapped axes
- `coimbra-osm-network.geojson`: review/reference transport network when OSM fetch succeeds
- `coimbra-preview.png`: human-review image
- `manifest.json`: exact source/config/output metadata

Rules:
- Preserve real horizontal proportions: crop the source terrain to a square before
  resizing; do not stretch the DGT raster.
- Keep source terrain immutable.
- Do not claim the GeoJSON road network is already imported into an OpenTTD .scn.
- This lane is a geodata/import-pack milestone. A generated .scn/savegame is a
  separate follow-up milestone.
- OSM attribution must be present in documentation and manifest.
