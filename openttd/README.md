# Coimbra OpenTTD

Real-world Coimbra geodata for an OpenTTD/Transport-Tycoon-style scenario.

## Milestone 001

This milestone is intentionally small and reproducible. It reuses the pinned DGT
terrain already verified by the Coimbra 3D project and turns it into an OpenTTD
Scenario Editor import pack.

Outputs:
- `coimbra-heightmap.png`
- `coimbra-towns.json`
- `coimbra-osm-network.geojson` when Overpass is reachable
- `coimbra-preview.png`
- `manifest.json`

The first crop covers the southern Coimbra corridor around Vale das Flores,
Bairro Norton de Matos, Pólo II and Quinta da Portela. It is a proof that the
real DGT terrain and real coordinates survive the conversion before expanding
to a much larger city map.

OpenTTD's official workflow is: load the PNG heightmap in Scenario Editor, then
use Town Generation -> Load from file for the JSON town data. The axes in the
town JSON are intentionally swapped to match OpenTTD's coordinate convention.

## Run

```bash
python -m pip install numpy pillow pyproj
python openttd/build_pack.py \
  --config openttd/config/coimbra-openttd-001.json \
  --out artifacts/coimbra-openttd-001 \
  --fetch-osm
```

## Data

Terrain: DGT MDT-2m derived/pinned 6 m crop from the existing Coimbra pipeline.

Transport reference: © OpenStreetMap contributors, ODbL.

The OSM GeoJSON is not yet a generated OpenTTD road layer. Automatic road,
bridge and tunnel construction is the next milestone.
