from __future__ import annotations

import json
from pathlib import Path

from pyproj import Transformer


ROOT = Path(__file__).resolve().parents[1]
OSM = ROOT / "data" / "osm" / "coimbra-route.json"
TERRAIN_META = ROOT / "data" / "processed" / "bridge_terrain_6m.json"
OUT = ROOT / "data" / "processed" / "bridge_osm_local_epsg3763.json"


def main() -> None:
    if not OSM.exists():
        raise SystemExit(f"Missing {OSM}; run scripts/fetch_osm_bridge.py")
    if not TERRAIN_META.exists():
        raise SystemExit(f"Missing pinned terrain metadata: {TERRAIN_META}")

    osm = json.loads(OSM.read_text())
    terrain = json.loads(TERRAIN_META.read_text())
    cx, cy = map(float, terrain["center_epsg3763"])

    transformer = Transformer.from_crs(
        "EPSG:4326",
        "EPSG:3763",
        always_xy=True,
    )

    nodes = {}
    for element in osm.get("elements", []):
        if element.get("type") != "node":
            continue
        x, y = transformer.transform(element["lon"], element["lat"])
        nodes[str(element["id"])] = [x - cx, y - cy]

    ways = [
        element
        for element in osm.get("elements", [])
        if element.get("type") == "way"
    ]

    payload = {
        "center_epsg3763": terrain["center_epsg3763"],
        "bbox_epsg3763": terrain["bbox_epsg3763"],
        "bbox_wgs84": terrain["bbox_wgs84"],
        "nodes": nodes,
        "ways": ways,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload))
    print(
        f"Wrote {OUT}: {len(nodes)} nodes, {len(ways)} ways "
        f"centered at EPSG:3763 {terrain['center_epsg3763']}"
    )


if __name__ == "__main__":
    main()
