# Coimbra OpenTTD 006 — urban density on the exact verified 005 save

006 is no longer allowed to rebuild Coimbra under a different OpenTTD version.
Its source of truth is the exact verified OpenTTD 005 save from run
`37212552230`:

- file: `coimbra-openttd-005.sav`;
- SHA-256: `6e650c35125eef7c53f5eceec5782200f9936c233489756a1729d828453984e3`;
- accepted 005 transport counters: roads `6229/1107`, bridges `44/19`,
  tunnels `0/13`.

006 loads that binary save in pinned OpenTTD 16.0-beta4 and migrates the
`Coimbra Builder` GameScript state from the completed 005 script to the 006
density-upgrade path. It attaches the four already-existing towns by name; it
does **not** refound them and it does **not** rebuild any OSM transport.

Density review:

1. fingerprint every road tile in the loaded 005 save;
2. for each existing district, attempt up to eight batches of
   `GSTown.ExpandTown(town_id, 100)`, stopping early at 600 residents;
3. `economy.allow_town_roads=false` remains inherited from the verified 005 save;
4. freeze each town again with `TOWN_GROWTH_NONE`;
5. fingerprint roads again and reject the run on any count/checksum change;
6. require all four districts to reach at least 300 residents;
7. save, verify and render the upgraded real save.

Rejected experiments are retained as evidence:
- run `37220893049`: stable 15.3 natural growth was too weak;
- run `37221497082`: beta4 expansion preserved its own fingerprint, but rebuilding
  the map under beta4 changed the OSM construction result, so it was not a valid
  continuation of 005.

006 remains review-only until its screenshots are directly compared with 005.
