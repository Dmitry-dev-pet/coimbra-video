# AGENTS.md

GitHub main is the source of truth for this repository.

## Current production directions

- Earth Studio + post-process remains the realistic imagery path.
- `COIMBRA-BRIDGE-001` is the contract-governed Blender integration path.

## APatch Blender constraints

For `contracts/COIMBRA-BRIDGE-001.json`:
- all objects matching `City_*` are protected city geometry;
- the agent may change only operations listed in the contract;
- camera motion must be expressed through generic `animate_camera_path` contract data;
- do not replace the generic bridge with a Coimbra-specific edit script;
- verification must be performed by `Dmitry-dev-pet/apatch-blender`;
- OpenStreetMap attribution must remain visible in published video output.

The first OSM scene is intentionally reproducible without DGT credentials. DGT MDS/LiDAR may replace or augment the geometry provider later without changing the bridge contract model.
