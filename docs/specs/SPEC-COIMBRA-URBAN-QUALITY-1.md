# SPEC-COIMBRA-URBAN-QUALITY-1 — street-scale urban quality pass

> **Status:** Experimental visual QA · **Owner:** repository

## Goal

Improve the visual readability of the accepted 009D urban-detail layer without
changing its geospatial sources, production camera path, orthophoto-detected
vehicles, high-resolution DGT terrain, buildings, facades or vegetation.

The pass starts from the already governed
`coimbra-urban-details-visual-dev.blend` produced by 009D.

## Allowed pre-governance changes

The 010 preparation step may:

- rebuild `Urban_Fixtures` at the exact OSM node anchors already used by 009D;
- add `Urban_Curbs` along OSM-tagged sidewalks;
- add `Urban_RoadMarkings` to appropriate higher-class two-way roads;
- improve fixture geometry while remaining low-poly and deterministic.

No external GLB asset pack is required. Geometry is generated in Blender so the
result remains reproducible and does not add another asset-license dependency.

## Fixture target

The visual pass should make these objects recognizable at low/drone-level
inspection:

- street lamps: pole, outreach arm, housing and emissive underside;
- benches: separate wood slats, backrest and metal supports;
- waste/recycling: body, lid and opening/readable top treatment;
- bicycle parking: inverted-U racks rather than isolated posts;
- traffic lights: pole, head and three signal lenses;
- stop/give-way signs: recognizable octagonal/triangular plates.

## Street infrastructure

- Sidewalk geometry from 009D remains unchanged.
- Curbs are narrow raised strips on the street edge of tagged sidewalks.
- Road markings are restrained dashed center lines only on suitable
  trunk/primary/secondary/tertiary two-way roads.
- Do not invent lane markings for every residential road.

## QA

The workflow renders:

- production-camera frames 1 / 181 / 360;
- temporary street-level views at Sanches/Brasil, Polo II and Portela.

Street QA cameras and neutral inspection fill lights are render-only and must not be saved into the output scene. Production-camera checkpoints must hash identically before and after preparation.

This is a visual-development lane. Promotion into a new APatch-governed
production contract happens only after the rendered QA is reviewed.
