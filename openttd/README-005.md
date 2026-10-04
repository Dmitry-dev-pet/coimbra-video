# Coimbra OpenTTD 005 — road fidelity

005 is stacked on the verified 004 city build.

It keeps the pinned DGT-derived heightmap, OSM network, four district anchors and
generation seed, but changes the build order:

1. found four small town anchors;
2. temporarily allow town roads only until each district reaches the 900-resident minimum;
3. freeze `economy.allow_town_roads=false`;
4. build the OSM bridge/tunnel candidates and surface-road network;
5. perform only buildings-only post-growth toward aspirational populations;
6. allow only bounded local endpoint recovery for OSM grade-separated structures.

No heightmap mutation and no demotion of failed bridge/tunnel candidates to ground
roads is allowed.

Baseline 004 run `37199363026`: roads 6037/1299, bridges 25/38, tunnels 0/13.
All four districts must remain at or above 900 residents.
