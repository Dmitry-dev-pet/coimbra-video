from __future__ import annotations

import hashlib
import json
import math
import random
import time
from pathlib import Path

import requests
from pyproj import Transformer


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "coimbra_bridge.json"
TERRAIN_META = ROOT / "data" / "processed" / "bridge_terrain_6m.json"
OUT = ROOT / "data" / "processed" / "bridge_vegetation_local.json"

GREEN_WAY_FILTERS = [
    'way["natural"~"wood|scrub|grassland"]',
    'way["landuse"~"forest|orchard|grass|meadow|recreation_ground"]',
    'way["leisure"~"park|garden"]',
]


def point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
        ):
            inside = not inside
        j = i
    return inside


def deterministic_points(
    way_id: int,
    polygon: list[list[float]],
    tags: dict,
    *,
    global_limit: int,
) -> list[list[float]]:
    if len(polygon) < 3:
        return []

    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max_x - min_x
    height = max_y - min_y
    if width <= 0 or height <= 0:
        return []

    kind = (
        tags.get("natural")
        or tags.get("landuse")
        or tags.get("leisure")
        or "green"
    )
    if kind in {"wood", "forest"}:
        spacing = 18.0
    elif kind == "orchard":
        spacing = 15.0
    elif kind in {"park", "garden"}:
        spacing = 24.0
    else:
        spacing = 28.0

    seed_bytes = hashlib.sha256(f"coimbra-veg:{way_id}:{kind}".encode()).digest()
    seed = int.from_bytes(seed_bytes[:8], "big")
    rng = random.Random(seed)
    offset_x = rng.random() * spacing
    offset_y = rng.random() * spacing

    points = []
    y = min_y + offset_y
    row = 0
    while y <= max_y and len(points) < global_limit:
        x = min_x + offset_x + (spacing * 0.5 if row % 2 else 0.0)
        while x <= max_x and len(points) < global_limit:
            jitter_x = (rng.random() - 0.5) * spacing * 0.45
            jitter_y = (rng.random() - 0.5) * spacing * 0.45
            px = x + jitter_x
            py = y + jitter_y
            if point_in_polygon(px, py, polygon):
                points.append([px, py])
            x += spacing
        y += spacing
        row += 1
    return points


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    terrain = json.loads(TERRAIN_META.read_text())
    west, south, east, north = cfg["bbox_wgs84"]
    bbox = f"{south},{west},{north},{east}"

    query_lines = [
        "[out:json][timeout:120];",
        "(",
        f'  node["natural"="tree"]({bbox});',
    ]
    for filter_expr in GREEN_WAY_FILTERS:
        query_lines.append(f"  {filter_expr}({bbox});")
    query_lines.extend(
        [
            ");",
            "out body;",
            ">;",
            "out skel qt;",
        ]
    )
    query = "\n".join(query_lines)

    headers = {
        "User-Agent": (
            "coimbra-video/006-vegetation "
            "(+https://github.com/Dmitry-dev-pet/coimbra-video)"
        )
    }

    raw = None
    errors = []
    for endpoint in cfg["overpass_endpoints"]:
        for attempt in range(1, 4):
            try:
                print(f"Vegetation Overpass: {endpoint} attempt {attempt}")
                response = requests.post(
                    endpoint,
                    data={"data": query},
                    headers=headers,
                    timeout=180,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload.get("elements"), list):
                    raise RuntimeError("Overpass JSON has no elements list")
                raw = payload
                break
            except Exception as exc:
                errors.append(f"{endpoint} attempt {attempt}: {exc!r}")
                time.sleep(attempt * 3)
        if raw is not None:
            break

    if raw is None:
        raise SystemExit("All vegetation Overpass endpoints failed:\n" + "\n".join(errors))

    cx, cy = map(float, terrain["center_epsg3763"])
    transformer = Transformer.from_crs(
        "EPSG:4326",
        "EPSG:3763",
        always_xy=True,
    )

    node_xy: dict[str, list[float]] = {}
    exact_trees = []
    for element in raw["elements"]:
        if element.get("type") != "node":
            continue
        x_abs, y_abs = transformer.transform(element["lon"], element["lat"])
        local = [x_abs - cx, y_abs - cy]
        node_xy[str(element["id"])] = local
        if element.get("tags", {}).get("natural") == "tree":
            exact_trees.append(
                {
                    "id": int(element["id"]),
                    "xy": local,
                    "species": element.get("tags", {}).get("species"),
                    "genus": element.get("tags", {}).get("genus"),
                }
            )

    green_areas = []
    sampled = []
    per_way_limit = 500
    total_sample_limit = 3500
    for element in raw["elements"]:
        if element.get("type") != "way":
            continue
        refs = element.get("nodes") or []
        polygon = [node_xy.get(str(node_id)) for node_id in refs]
        if any(point is None for point in polygon) or len(polygon) < 4:
            continue
        polygon = [point for point in polygon if point is not None]
        if polygon[0] != polygon[-1]:
            continue

        tags = element.get("tags", {})
        points = deterministic_points(
            int(element["id"]),
            polygon[:-1],
            tags,
            global_limit=min(per_way_limit, total_sample_limit - len(sampled)),
        )
        if not points:
            continue

        kind = tags.get("natural") or tags.get("landuse") or tags.get("leisure") or "green"
        green_areas.append(
            {
                "id": int(element["id"]),
                "kind": kind,
                "point_count": len(points),
            }
        )
        sampled.extend(
            {
                "way_id": int(element["id"]),
                "kind": kind,
                "xy": point,
            }
            for point in points
        )
        if len(sampled) >= total_sample_limit:
            break

    result = {
        "source": "OpenStreetMap via Overpass API",
        "license": "ODbL",
        "bbox_wgs84": cfg["bbox_wgs84"],
        "center_epsg3763": terrain["center_epsg3763"],
        "exact_tree_nodes": exact_trees,
        "green_areas": green_areas,
        "sampled_green_points": sampled,
        "counts": {
            "exact_tree_nodes": len(exact_trees),
            "green_areas": len(green_areas),
            "sampled_green_points": len(sampled),
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["counts"], indent=2))


if __name__ == "__main__":
    main()
