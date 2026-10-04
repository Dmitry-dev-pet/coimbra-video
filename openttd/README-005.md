# Coimbra OpenTTD 005 — road fidelity

005 is stacked on the verified 004 city build.

It keeps the pinned DGT-derived heightmap, OSM network, four district anchors and
generation seed, but changes the build order:

1. found four small town anchors;
2. grow each compact town only until it reaches the 900-resident minimum;
3. stop all further town expansion;
4. build the OSM bridge/tunnel candidates and surface-road network over those capped anchors;
5. validate final populations without any post-OSM expansion;
6. allow only bounded local endpoint recovery for OSM grade-separated structures.

OpenTTD 15.3 rejects changing `economy.allow_town_roads` at runtime in the
dedicated build used here, so 005 limits invented roads by capping the entire
autonomous-growth phase rather than relying on an unsafe dynamic setting toggle.

No heightmap mutation and no demotion of failed bridge/tunnel candidates to ground
roads is allowed.

Baseline 004 run `37199363026`: roads 6037/1299, bridges 25/38, tunnels 0/13.
All four districts must remain at or above 900 residents.
