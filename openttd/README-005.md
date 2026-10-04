# Coimbra OpenTTD 005 — road fidelity

005 is stacked on the verified 004 city build, but road fidelity takes precedence
over synthetic population growth.

It keeps the pinned DGT-derived heightmap, OSM network, four district anchors and
generation seed, and uses this order:

1. start the 512×512 map with no towns;
2. build OSM-derived bridges, tunnels and the surface-road network;
3. only after the transport build is complete, found the four compact Coimbra town anchors;
4. prefer a buildable founding tile directly adjacent to an already imported OSM road;
5. immediately set each town to `TOWN_GROWTH_NONE`;
6. do not call `GSTown.ExpandTown` at all;
7. keep `economy.allow_town_roads=false` from game start;
8. mark the GameScript complete and save immediately.

This avoids the failure seen in run `37202300102`, where towns founded before the
long OSM build autonomously grew to tens of thousands of residents and filled the
map with invented OpenTTD streets.

005 acceptance requires all four real district anchors to exist with non-zero
population. The 900-resident minimum remains an 004 urban-visibility requirement,
not a 005 road-fidelity requirement.

No heightmap mutation and no demotion of failed bridge/tunnel candidates to ground
roads is allowed.

Baseline 004 run `37199363026`: roads 6037/1299, bridges 25/38, tunnels 0/13.
Failed 005 run `37202300102` is retained as diagnostic evidence, not a baseline.
Run `37210983009` proved the OSM-first ordering works, but Bairro Norton de Matos was founded with population 0; the road-adjacent founding pass fixes that case without enabling town road growth.
