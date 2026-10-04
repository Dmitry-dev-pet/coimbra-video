# Coimbra OpenTTD 006 — urban density on locked OSM roads

006 stacks on the verified OpenTTD 005 road-fidelity baseline
(run `37212552230`, commit `3f27c5a`).

The first 006 experiment on stable OpenTTD 15.3 used fast natural town growth.
It preserved the 005 transport counters but produced almost no useful density
(70 / 118 / 129 / 144 residents), so that path is rejected.

The current review uses **OpenTTD 16.0-beta4**. OpenTTD 16 specifically changes
`GSTown.ExpandTown` to respect `economy.allow_town_roads`. 006 therefore tests
a bounded `ExpandTown(town, 60)` for each district while
`allow_town_roads=false`.

Acceptance remains strict:

1. rebuild the exact accepted 005 network counters: roads `6229/1107`, bridges
   `44/19`, tunnels `0/13`;
2. found the same four district anchors beside existing OSM roads;
3. fingerprint all road tiles before density expansion;
4. expand each town by at most 60 houses;
5. freeze the town immediately afterwards;
6. fingerprint all road tiles again and require count + checksum to match exactly;
7. require each district to reach at least 300 residents;
8. verify the real save and screenshots.

This is deliberately a **beta review lane**, not a replacement for the stable 005
baseline. Promotion requires both an unchanged road fingerprint and a human visual
comparison against 005.
