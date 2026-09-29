# SPEC-COIMBRA-CAR-REALITY-1 — orthophoto vehicle placement

> **Status:** Draft v1 · **Owner:** repository
> **apatch artifact:** `spec:SPEC-COIMBRA-CAR-REALITY-1`

## R1 Replace procedural cars with orthophoto-detected vehicles

`COIMBRA-BRIDGE-008A-CAR-REALITY` must start from the approved 007 miniature
scene and replace the procedural `Detail_Cars` layer with a deterministic
vehicle layer derived from the DGT 2025 25 cm orthophoto.

Detection uses an oriented-bounding-box model pretrained on DOTAv1. Only the
`small vehicle` and `large vehicle` classes are accepted. The detector must
tile the route orthophoto, merge duplicate detections across overlapping tiles,
convert pixel centers and orientations to local EPSG:3763 scene coordinates,
and reject implausible physical box sizes.

The Blender preparation step must remove the old procedural car mesh and place
the detected vehicles at the detected center/orientation. Approximate vehicle
body color may be sampled from the orthophoto. A scene ray-cast must reject
detections whose top surface is a building, facade, vegetation crown, solar
array, rooftop fixture or HVAC unit.

The resulting scene becomes the APatch baseline. From session start onward all
`City_*`, `Facade_*`, `Vegetation_*`, and `Detail_*` state plus car-source
metadata must remain unchanged.

The output must include:
- governed `.blend`;
- frames 1 / 181 / 360;
- raw detection JSON;
- a downscaled OBB visual-QA image;
- car-reality manifest;
- passing semantic verification.

(verify: python3 scripts/verify_car_reality_evidence.py --report bridge_output_008a/car-reality-verification.json --probe verification/COIMBRA-BRIDGE-008A-CAR-REALITY.probe)
