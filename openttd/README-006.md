# Coimbra OpenTTD 006 — editor house-density lane

006 still starts from the exact verified 005 save from run `37212552230`
(SHA-256 `6e650c35125eef7c53f5eceec5782200f9936c233489756a1729d828453984e3`).

Stock OpenTTD GameScript cannot place an ordinary town house directly. Every stock
workaround we tested either failed to add density or changed road tiles. Therefore
006 now uses a **temporary OpenTTD 15.3 editor binary** built from exact upstream
commit `14ec60f248547d4d062a1160f0fc26d742319888`.

The patch is deliberately tiny:
- export `GSTown.PlaceHouse(tile, house_id)` to GameScript;
- allow a Deity GameScript to invoke the already-existing `CMD_PLACE_HOUSE`;
- make Deity-placed houses immediately completed.

No savegame format, road algorithm, town-growth algorithm, or serialization code is
changed.

For each of the four existing 005 towns, the GameScript scans at most 32 tiles from
the town centre, only considers buildable tiles directly adjacent to an existing
road, and places up to 40 single-tile base houses (HouseID 0–2). It requires at
least 15 successful houses and a positive population gain per district.

Acceptance remains strict:
1. load the exact 005 save;
2. road fingerprint before/after must match exactly;
3. all four existing towns must gain population;
4. no `ExpandTown` calls;
5. save with the temporary editor binary;
6. verify that output save with the **official unmodified OpenTTD 15.3**;
7. render review screenshots with the official binary.

The editor executable is never a deliverable. The deliverable is an ordinary
OpenTTD save that stock 15.3 can load.
