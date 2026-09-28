from __future__ import annotations

import json
from pathlib import Path

from pyproj import Transformer


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "coimbra_bridge.json"
OSM = ROOT / "data" / "osm" / "coimbra-oss-rich.json"
OUT = ROOT / "data" / "processed" / "bridge_osm_oss_local.json"


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    data = json.loads(OSM.read_text())
    west, south, east, north = cfg["bbox_wgs84"]

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3763", always_xy=True)
    x1, y1 = transformer.transform(west, south)
    x2, y2 = transformer.transform(east, north)
    minx, maxx = sorted((x1, x2))
    miny, maxy = sorted((y1, y2))
    cx = (minx + maxx) / 2.0
    cy = (miny + maxy) / 2.0

    nodes = {}
    ways = []
    relations = []
    for element in data.get("elements", []):
        kind = element.get("type")
        if kind == "node":
            x, y = transformer.transform(float(element["lon"]), float(element["lat"]))
            nodes[str(element["id"])] = {
                "xy": [x - cx, y - cy],
                "tags": element.get("tags") or {},
            }
        elif kind == "way":
            ways.append(
                {
                    "id": int(element["id"]),
                    "nodes": [int(n) for n in element.get("nodes") or []],
                    "tags": element.get("tags") or {},
                }
            )
        elif kind == "relation":
            relations.append(element)

    payload = {
        "source": "OpenStreetMap via Overpass",
        "bbox_wgs84": cfg["bbox_wgs84"],
        "center_epsg3763": [cx, cy],
        "nodes": nodes,
        "ways": ways,
        "relations": relations,
        "counts": {
            "nodes": len(nodes),
            "ways": len(ways),
            "relations": len(relations),
            "crossing_nodes": sum(
                1
                for node in nodes.values()
                if (node["tags"].get("highway") or "").lower() == "crossing"
                or bool(node["tags"].get("crossing"))
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload) + "\n")
    print(json.dumps(payload["counts"], indent=2))


if __name__ == "__main__":
    main()
