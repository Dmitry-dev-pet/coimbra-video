# Coimbra OpenTTD 003 — playable save + real screenshots

003 turns the verified Coimbra geodata/GameScript pipeline into a concrete OpenTTD
savegame.

The workflow:

1. rebuilds the 002 road/bridge/tunnel GameScript from the pinned 001 geodata;
2. starts official OpenTTD 15.3 in dedicated mode on the 512×512 Coimbra heightmap;
3. waits for all road chunks to finish;
4. issues the real OpenTTD console command `save coimbra-openttd-003`;
5. verifies the resulting `.sav` with OpenTTD's `-q` savegame inspector;
6. loads the saved game in graphical OpenTTD under Xvfb;
7. captures a real isometric screenshot and a real OpenTTD minimap screenshot.

The GameScript persists a `completed` flag. Loading the generated save does not
rebuild the network.

003 intentionally produces a `.sav`, not a file merely renamed to `.scn`.
