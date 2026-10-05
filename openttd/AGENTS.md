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
- build the OSM-derived transport network before any Coimbra town exists;
- only after OSM transport completes, found the four pinned compact town anchors;
- first search for a buildable founding tile directly adjacent to an already-built OSM road, with only a bounded fallback around the pinned anchor;
- freeze every successfully founded town with `GSTown.SetGrowthRate(..., TOWN_GROWTH_NONE)`;
- 005 must contain no `GSTown.ExpandTown` calls;
- configure `economy.allow_town_roads=false` from game start; do not rely on runtime setting changes;
- all four required districts must be created successfully with non-zero population;
- the 900-resident minimum belongs to 004 and is deliberately not an acceptance condition for 005;
- after founding the four anchors, mark the GameScript complete and save immediately;
- bridge/tunnel recovery may search only within 3 tiles of OSM-derived endpoints;
- bridge recovery may trim heads by at most 2 tiles or shift the whole span
  parallel by at most 3 tiles;
- failed grade-separated structures must never be flattened to surface roads;
- the pinned 001 heightmap is immutable in 005;
- compare runtime counts against verified 004: roads 6037/1299, bridges 25/38,
  tunnels 0/13;
- screenshots must come from the reloaded real 005 `.sav`;
- run `37202300102` is a rejected diagnostic run because autonomous town growth
  created a large invented road grid despite green CI;
- run `37210983009` is a rejected diagnostic run because the OSM-first order worked
  but Bairro Norton de Matos was founded with population 0.

## COIMBRA-OPENTTD-006

Goal: add ordinary completed houses to the exact verified 005 save without changing
any accepted road tile.

Rules:
- source authority is verified 005 run `37212552230`, save SHA-256
  `6e650c35125eef7c53f5eceec5782200f9936c233489756a1729d828453984e3`;
- stay on OpenTTD 15.3 and do not rebuild OSM transport;
- editor source must be exact upstream commit
  `14ec60f248547d4d062a1160f0fc26d742319888`;
- the temporary engine patch may only expose `GSTown.PlaceHouse`, permit Deity to
  use existing `CMD_PLACE_HOUSE`, and complete Deity-placed houses immediately;
- do not alter savegame serialization or town/road growth algorithms;
- attach the four existing 005 towns by name; never refound them;
- place houses only on buildable tiles adjacent to an already-existing road;
- only HouseID 0, 1, or 2 may be attempted (single-tile base-house invariant);
- target 40 successful houses per district; require at least 15 and a positive
  population gain for every district;
- no `GSTown.ExpandTown` calls are allowed;
- road fingerprint before and after must match exactly;
- final output must load successfully in official unmodified OpenTTD 15.3;
- screenshots must be rendered with official unmodified OpenTTD 15.3;
- rejected evidence includes runs `37220893049`, `37221497082`,
  `37222115679`, and `37222874353`;
- 006 remains review-only until screenshots are materially better than 005.


## COIMBRA-OPENTTD-007

Goal: replace the rejected 006 fixed-house experiment with population-targeted,
mixed low-/medium-rise urban fabric while preserving the exact verified 005 roads.

Rules:
- source authority is verified 005 run `37212552230`, save SHA-256
  `6e650c35125eef7c53f5eceec5782200f9936c233489756a1729d828453984e3`;
- attach the four existing 005 towns by name; never refound them;
- target the pinned populations: Vale das Flores 2200, Bairro Norton de Matos 2600,
  Polo II 1800, Quinta da Portela 1800;
- place only completed houses adjacent to an already-existing road;
- use a deterministic mixed palette and explicit gaps; do not repeat the rejected
  HouseID 0 wall/tower pattern from 006;
- require at least 15 placed houses, 5 low-rise houses, and 2 medium-rise houses
  for every district;
- final population must reach its target but may overshoot by at most 120;
- no `GSTown.ExpandTown` calls and no autonomous town-road growth;
- road fingerprint before and after must match exactly;
- final output must load successfully in official unmodified OpenTTD 15.3;
- screenshots must be rendered with official unmodified OpenTTD 15.3;
- verified reference run is `37232609341`, with road fingerprint
  `13767 / 1811156236` preserved.

## COIMBRA-OPENTTD-008

Goal: reduce the large empty gaps visible in 007 by adding low-rise fabric around
five real OSM-sourced secondary Coimbra neighborhood anchors, without inventing
roads or creating new towns.

Rules:
- source authority is verified 007 run `37232609341`, save SHA-256
  `3e4e67971511bd083c6c9b3e4981acb55fba6ff428d9f7a969561fe8ca2cc041`;
- use only anchors from `openttd/config/coimbra-openttd-006-density-towns.json`;
- do not found or rename towns and do not change the four existing 007 town anchors;
- place houses only on buildable tiles directly adjacent to an existing road;
- the 008 palette is low-rise only: HouseID `0x1A`, `0x18`, `0x19`, or `0x06`;
- preserve deterministic gaps so the result does not become a continuous roadside wall;
- target at most 24 houses per secondary anchor and require at least 8 successful
  houses for every anchor;
- no `GSTown.ExpandTown` calls and no autonomous town-road growth;
- road fingerprint before and after must remain exactly `13767 / 1811156236`;
- the temporary editor bridge remains limited to the existing `GSTown.PlaceHouse`
  mechanism from 006/007; do not alter save serialization or growth algorithms;
- final output must load successfully in official unmodified OpenTTD 15.3;
- review screenshots must be captured from the reloaded 008 save with official
  unmodified OpenTTD 15.3.
