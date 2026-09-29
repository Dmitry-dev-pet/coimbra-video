# SPEC-COIMBRA-URBAN-DETAILS-1 — OSM/MOSAIQ urban details

> **Status:** Draft v1 · **Owner:** repository
> **apatch artifact:** `spec:SPEC-COIMBRA-URBAN-DETAILS-1`

## R1 Add real OSM urban scale cues using pinned MOSAIQ semantics

`COIMBRA-BRIDGE-009D-URBAN-DETAILS` starts from the approved 008C
high-resolution miniature scene.

Before APatch session start, the preparation stage may add:
- sidewalks and tagged parking strips using MOSAIQ's pinned OSM tag parsers
  and geometry helpers;
- zebra crossings at exact tagged OSM crossing nodes;
- low-poly fixtures at exact tagged OSM points: street lamps, benches,
  waste/recycling containers, bicycle parking, traffic lights and stop/give-way
  signs.

MOSAIQ is a runtime dependency pinned at
`f73d030aecd3289007472a887d78aae2e74b6ea0` under Apache-2.0. Its source is
checked out separately in CI and is not copied into this repository.

The production miniature layer intentionally adapts visual dimensions rather
than accepting all upstream defaults. Sidewalk width is reduced to 1.75 m and
crosswalk stripes are tuned for the existing miniature scale.

Do not add MOSAIQ procedural vehicles: the scene keeps 008A orthophoto-detected
vehicles.

All generated urban geometry must be consolidated into a small number of
`Urban_*` meshes, draped to the 2 m terrain derived from DGT MDT-50cm.

After the prepared scene becomes the APatch baseline, all existing city,
facade, vegetation, detail and `Urban_*` state plus selected metadata must
remain unchanged. Normal iteration renders frames 1 / 181 / 360 only.

(verify: python3 scripts/verify_urban_details_evidence.py --report bridge_output_009d/urban-details-verification.json --probe verification/COIMBRA-BRIDGE-009D-URBAN-DETAILS.probe)
