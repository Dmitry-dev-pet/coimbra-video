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


## COIMBRA-OPENTTD-004

Goal: turn the verified 003 transport skeleton into a recognisable OpenTTD city by
founding the four pinned Coimbra districts as real towns and growing visible urban
development around them.

Required towns:
- Vale das Flores
- Bairro Norton de Matos
- Polo II
- Quinta da Portela

Rules:
- town coordinates must come from the pinned 001 `coimbra-towns.json`, not from
  hand-tuned screenshot positions;
- if the exact tile is occupied or unsuitable, search only a small bounded radius;
- all four towns must be created successfully before the 004 save is accepted;
- each district must reach at least 900 residents; the pinned population remains an
  aspirational growth target, not permission to flatten or materially distort terrain;
- town expansion must use OpenTTD's own town-building API, not painted or generated
  building sprites;
- 004 screenshots must come from the reloaded `.sav` in graphical OpenTTD;
- preserve the 003 road/bridge/tunnel semantics and never flatten failed
  grade-separated structures;
- do not mutate accepted Blender 032/033 assets.


## COIMBRA-OPENTTD-005

Goal: improve real-world road fidelity over verified 004 without changing the pinned
001 terrain/OSM sources or accepted Blender 032/033 baselines.

Rules:
- stack on verified OpenTTD 004 run `37199363026` and keep generation seed `1996061907`;
- found only compact town anchors before transport construction;
- set `economy.allow_town_roads=false` and grow population only after the OSM
  network exists, so `GSTown.ExpandTown` adds buildings rather than new roads;
- all four required districts must still reach at least 900 residents;
- bridge/tunnel recovery may search only within 3 tiles of OSM-derived endpoints;
- bridge recovery may trim heads by at most 2 tiles or shift the whole span
  parallel by at most 3 tiles;
- failed grade-separated structures must never be flattened to surface roads;
- the pinned 001 heightmap is immutable in 005;
- compare runtime counts against verified 004: roads 6037/1299, bridges 25/38,
  tunnels 0/13;
- screenshots must come from the reloaded real 005 `.sav`.
