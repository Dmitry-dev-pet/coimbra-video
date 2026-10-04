# Coimbra OpenTTD 004 — real towns + urban development

004 turns the verified 003 transport skeleton into a recognisable Transport Tycoon city.

It keeps the same pinned Coimbra terrain and OSM network, then:

1. rebuilds the verified Coimbra road / bridge / tunnel GameScript;
2. imports the four normalized Coimbra district locations from the pinned 001 artifact;
3. founds real OpenTTD towns near those coordinates:
   - Vale das Flores
   - Bairro Norton de Matos
   - Polo II
   - Quinta da Portela
4. expands each town toward the configured target population before laying the OSM road network;
5. requires at least 900 residents in every district, while treating the older 001 population values as aspirational targets rather than a reason to flatten the real terrain;
6. saves the result as a real OpenTTD `.sav`;
7. reloads that save in graphical OpenTTD;
8. captures an overview, one 1280×720 frame per district, and a minimap.

The town placement searches only a small radius around each real coordinate so occupied road tiles or unsuitable terrain do not force the district far away.

The accepted Blender 032 scene/look and 033 camera-motion baseline remain untouched.

Town placement uses a 40-tile edge guard plus a 12-tile local search. This only affects edge-constrained districts such as Quinta da Portela; the pinned normalized coordinates remain the geographic anchors.
