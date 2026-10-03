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
4. expands each town toward the configured target population;
5. saves the result as a real OpenTTD `.sav`;
6. reloads that save in graphical OpenTTD;
7. captures an overview, one 1280×720 frame per district, and a minimap.

The town placement searches only a small radius around each real coordinate so occupied road tiles or unsuitable terrain do not force the district far away.

The accepted Blender 032 scene/look and 033 camera-motion baseline remain untouched.
