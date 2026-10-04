# Coimbra OpenTTD 006 — urban density on locked OSM roads

006 stacks directly on the verified OpenTTD 005 road-fidelity baseline
(run `37212552230`, commit `3f27c5a`).

Goal: make the four Coimbra districts visibly denser **without changing the accepted
005 road network**.

Method:

1. rebuild the same pinned terrain/OSM transport network and require the exact
   accepted 005 runtime counters: roads `6229/1107`, bridges `44/19`, tunnels `0/13`;
2. found the same four compact district anchors beside existing OSM roads;
3. keep `economy.allow_town_roads=false` from game start;
4. never call `GSTown.ExpandTown`;
5. fingerprint all road tiles (count + tile-index checksum);
6. temporarily set each town to a 1-day natural growth interval for exactly 4,440
   GameScript ticks;
7. freeze every town again with `TOWN_GROWTH_NONE`;
8. recompute the road fingerprint and reject the run if it changed;
9. require every district to reach at least 300 residents;
10. save the real `.sav`, verify it with OpenTTD 15.3 and capture six real frames.

006 is a review lane. It does not replace 005 unless the screenshots are materially
better while the road fingerprint remains unchanged.
