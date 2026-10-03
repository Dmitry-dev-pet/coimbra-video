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


## COIMBRA-OPENTTD-002

Goal: quantize the 001 OSM transport reference to a 512×512 four-connected
OpenTTD road plan and emit an installable Coimbra Builder GameScript.

Rules:
- surface roads may be snapped to the tile grid;
- bridge/tunnel/layer-tagged geometry remains grade-separated;
- failed or unrepresentable grade-separated candidates must never be silently
  flattened to surface roads;
- 002 may read 001 outputs but must not mutate the pinned DGT source or accepted
  Blender 032/033 assets;
- a GameScript package is an executable construction layer, not yet a committed
  binary .scn/savegame.


## COIMBRA-OPENTTD-003

Goal: execute the full 002 Coimbra network in official OpenTTD 15.3, save the
result as a real .sav, verify the save with OpenTTD itself, and capture real game
screenshots from the saved map.

Rules:
- 003 must use the pinned 001 geodata hashes and rebuild the 002 GameScript from
  the current branch.
- wait for `Coimbra network build complete.` before issuing the save command;
- verify the .sav with OpenTTD `-q`;
- screenshots must come from the saved game loaded by graphical OpenTTD, not from
  Pillow, Blender, generated artwork, or the diagnostic road preview;
- persist a completed GameScript state so loading the save does not rebuild the network;
- do not mutate accepted Blender 032/033 assets.
