# Data sources and attribution

## DGT LiDAR / MDS

Direção-Geral do Território (DGT), Portugal.

LiDAR survey of mainland Portugal. The official DGT documentation describes:
- mean point density: about 10 points/m²
- point cloud: LAZ
- derived MDT/MDS: 0.5 m and 2 m GeoTIFF
- reference system: PT-TM06 / ETRS89 (EPSG:3763)
- acquisition: 2024–2025

Landing page:
https://www.dgterritorio.gov.pt/levantamento-lidar-de-portugal-continental-0

Data centre:
https://cdd.dgterritorio.gov.pt/

The DGT states that these LiDAR data are open and without restrictions on use.

## DGT Orthophotos 2025

Direção-Geral do Território (DGT), Portugal.

25 cm orthophotos of mainland Portugal, RGB+NIR, 2025.

Catalog:
https://dados.gov.pt/en/datasets/ortofotos-25-cm-portugal-continental-2025

WMS:
https://cartografia.dgterritorio.gov.pt/wms/ortos2025

Layer:
`Ortos2025-RGB`

Catalog license:
Creative Commons Attribution 4.0 (CC BY 4.0).

Suggested attribution:
`Orthophoto 2025 © Direção-Geral do Território (DGT), CC BY 4.0`


## OpenStreetMap / Overpass

The APatch Blender bridge demo uses OpenStreetMap building footprints and road geometry for a reproducible, credential-free Coimbra 3D scene.

Data © OpenStreetMap contributors, available under the Open Database License (ODbL).

Copyright/license:
https://www.openstreetmap.org/copyright

The workflow requests a bounded Coimbra corridor from the public Overpass API and renders its own Blender geometry; it does not use OpenStreetMap raster tiles.


## Bridge 002 texture use

`COIMBRA-BRIDGE-002` fetches the DGT `Ortos2025-RGB` WMS for the exact Coimbra route bbox and applies it to the Blender ground plane.

The orthophoto source is DGT Orthophotos 2025, catalogued as CC BY 4.0. The final video includes DGT and OpenStreetMap attribution.


## DGT MDT-2m terrain crop

`COIMBRA-BRIDGE-003` uses DGT `MDT-2m` as the bare-earth terrain source. Nine source tiles intersect the route bbox. The pinned derived asset is downsampled from 2 m to 6 m for CI rendering; the original source remains DGT open data. The MDT is used instead of MDS because MDS includes buildings and vegetation surfaces, which would double-count those features when OSM buildings are extruded separately.


## Coimbra V2-001 photogrammetry

Sketchfab model: `Coimbra` by VirtualPhoto3D (@johnagotinho).

Model UID:
`4175f64513a44546b65a119af5aacdff`

Model page:
https://sketchfab.com/3d-models/coimbra-4175f64513a44546b65a119af5aacdff

Published metadata describes DJI Mini 2 photogrammetry, approximately 7.5M
triangles / 3.8M vertices, under Creative Commons Attribution.

Sketchfab's Download API requires an authenticated user before it returns the
short-lived archive URL. V2-001 therefore consumes `SKETCHFAB_TOKEN` only inside
the guarded source-preparation workflow. The token and signed archive URL are never
written to manifests, issue comments, logs intentionally, or repository history.

Suggested rendered-output attribution:
`Coimbra photogrammetry by VirtualPhoto3D (@johnagotinho), Sketchfab, CC Attribution`.
