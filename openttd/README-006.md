# Coimbra OpenTTD 006 — real micro-neighbourhood density

006 loads the exact verified 005 save from run `37212552230`
(SHA-256 `6e650c35125eef7c53f5eceec5782200f9936c233489756a1729d828453984e3`)
and stays on OpenTTD 15.3.

Rejected approaches:
- timed natural growth was too weak;
- `ExpandTown` produced no population gain and mutated road tiles;
- rebuilding the map under beta4 changed the accepted transport result.

The current experiment does not grow the four existing towns. It adds five real
Coimbra neighbourhood/locality anchors inside the same pinned crop:
Arregaça, Bairro da Fonte do Castanheiro, Quinta Dom João, Quinta da Boa Vista,
and Bairro da Fonte da Talha.

For each locality the GameScript searches at most 16 tiles for a buildable tile
directly adjacent to an existing road, founds a small town, then immediately sets
`TOWN_GROWTH_NONE`.

Acceptance:
1. exact 005 source-save SHA;
2. all five density towns created with non-zero population;
3. zero `ExpandTown` calls;
4. road tile count + checksum unchanged;
5. upgraded save verifies in OpenTTD 15.3 and renders real screenshots.

Any road fingerprint change rejects 006 and leaves 005 as the accepted baseline.
