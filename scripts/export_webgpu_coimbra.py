from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TERRAIN = ROOT / "data" / "processed" / "bridge_terrain_6m.npz"
DEFAULT_TERRAIN_META = ROOT / "data" / "processed" / "bridge_terrain_6m.json"
DEFAULT_OSM = ROOT / "data" / "processed" / "bridge_osm_local_epsg3763.json"
DEFAULT_CONTRACT = ROOT / "contracts" / "COIMBRA-BRIDGE-003-SLOW.json"
DEFAULT_OUT = ROOT / "web" / "public" / "data" / "coimbra"

ROAD_GROUPS = {
    "major": {"motorway", "trunk", "primary", "secondary"},
    "local": {"tertiary", "residential", "living_street", "unclassified"},
    "service": {"service"},
    "paths": {"footway", "path", "pedestrian", "cycleway", "steps", "track"},
}


def parse_number(value):
    if value is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    return float(match.group()) if match else None


def building_height(tags: dict) -> float:
    direct = parse_number(tags.get("height"))
    if direct is not None:
        return max(3.0, min(90.0, direct))
    levels = parse_number(tags.get("building:levels"))
    if levels is not None:
        return max(3.0, min(90.0, levels * 3.0))
    if tags.get("building") in {"church", "cathedral", "chapel"}:
        return 18.0
    if tags.get("building") in {"university", "school", "hospital", "public"}:
        return 14.0
    return 9.0


def road_group(highway: str | None) -> str | None:
    if not highway:
        return None
    for name, values in ROAD_GROUPS.items():
        if highway in values:
            return name
    return None


def route_anchors(contract: dict) -> list[dict]:
    expected = contract.get("expected", {}).get("camera_path", {}).get("checkpoints")
    if expected:
        return expected
    for operation in contract.get("operations", []):
        if operation.get("op") == "animate_camera_path":
            return operation.get("params", {}).get("keyframes", [])
    raise ValueError("Contract has no camera-path checkpoints")


def make_sampler(xs: np.ndarray, ys: np.ndarray, z: np.ndarray, z0: float):
    x0, x1 = float(xs[0]), float(xs[-1])
    y0, y1 = float(ys[0]), float(ys[-1])
    width = z.shape[1]
    height = z.shape[0]

    def sample(x: float, y: float) -> float:
        col = int(round((float(x) - x0) / (x1 - x0) * (width - 1)))
        row = int(round((y0 - float(y)) / (y0 - y1) * (height - 1)))
        col = max(0, min(width - 1, col))
        row = max(0, min(height - 1, row))
        return float(z[row, col] - z0)

    return sample


def tile_of(x: float, y: float, tile_size: float) -> tuple[int, int]:
    return math.floor(x / tile_size), math.floor(y / tile_size)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )


def export_dataset(
    terrain_path: Path,
    terrain_meta_path: Path,
    osm_path: Path,
    contract_path: Path,
    out_dir: Path,
    tile_size: float = 250.0,
) -> dict:
    terrain = np.load(terrain_path)
    xs = np.asarray(terrain["xs"], dtype=float)
    ys = np.asarray(terrain["ys"], dtype=float)
    z = np.asarray(terrain["z"], dtype=float)
    z0 = float(terrain["z0"])
    meta = json.loads(terrain_meta_path.read_text(encoding="utf-8"))
    osm = json.loads(osm_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))

    if z.shape != (len(ys), len(xs)):
        raise ValueError(
            f"Terrain shape {z.shape} does not match ys/xs {(len(ys), len(xs))}"
        )
    if tile_size <= 0:
        raise ValueError("tile_size must be positive")

    sample_height = make_sampler(xs, ys, z, z0)
    nodes = osm.get("nodes", {})
    ways = osm.get("ways", [])

    tiles: dict[tuple[int, int], dict] = {}

    def ensure_tile(i: int, j: int) -> dict:
        key = (i, j)
        if key not in tiles:
            tiles[key] = {
                "i": i,
                "j": j,
                "terrain": None,
                "buildings": [],
                "roads": [],
                "top": 0.0,
            }
        return tiles[key]

    i_min, j_min = tile_of(float(xs.min()), float(ys.min()), tile_size)
    i_max, j_max = tile_of(float(xs.max()), float(ys.max()), tile_size)

    epsilon = 1e-6
    for i in range(i_min, i_max + 1):
        x_lo, x_hi = i * tile_size, (i + 1) * tile_size
        cols = np.where((xs >= x_lo - epsilon) & (xs <= x_hi + epsilon))[0]
        if len(cols) < 2:
            continue
        for j in range(j_min, j_max + 1):
            y_lo, y_hi = j * tile_size, (j + 1) * tile_size
            rows = np.where((ys >= y_lo - epsilon) & (ys <= y_hi + epsilon))[0]
            if len(rows) < 2:
                continue
            tile = ensure_tile(i, j)
            heights = z[np.ix_(rows, cols)] - z0
            tile["terrain"] = {
                "xs": [round(float(v), 3) for v in xs[cols]],
                "ys": [round(float(v), 3) for v in ys[rows]],
                "heights": [
                    [round(float(v), 3) for v in row] for row in heights
                ],
            }
            tile["top"] = max(tile["top"], float(np.nanmax(heights)))

    for way in ways:
        tags = way.get("tags", {})
        if "building" not in tags:
            continue
        coords = [nodes.get(str(node_id)) for node_id in way.get("nodes", [])]
        if any(coord is None for coord in coords) or len(coords) < 4:
            continue
        if coords[0] != coords[-1]:
            continue
        polygon = coords[:-1]
        if len(polygon) < 3:
            continue
        cx = sum(float(point[0]) for point in polygon) / len(polygon)
        cy = sum(float(point[1]) for point in polygon) / len(polygon)
        base = sample_height(cx, cy) + 0.35
        height = building_height(tags)
        i, j = tile_of(cx, cy, tile_size)
        tile = ensure_tile(i, j)
        tile["buildings"].append(
            {
                "id": int(way.get("id", 0)),
                "polygon": [
                    [round(float(point[0]), 3), round(float(point[1]), 3)]
                    for point in polygon
                ],
                "base": round(base, 3),
                "height": round(height, 3),
            }
        )
        tile["top"] = max(tile["top"], base + height)

    for way in ways:
        kind = road_group(way.get("tags", {}).get("highway"))
        if kind is None:
            continue
        coords = [
            nodes.get(str(node_id))
            for node_id in way.get("nodes", [])
            if nodes.get(str(node_id)) is not None
        ]
        for a, b in zip(coords, coords[1:]):
            ax, ay = map(float, a)
            bx, by = map(float, b)
            mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
            i, j = tile_of(mx, my, tile_size)
            tile = ensure_tile(i, j)
            tile["roads"].append(
                {
                    "kind": kind,
                    "a": [round(ax, 3), round(ay, 3), round(sample_height(ax, ay) + 0.45, 3)],
                    "b": [round(bx, 3), round(by, 3), round(sample_height(bx, by) + 0.45, 3)],
                }
            )

    tiles_dir = out_dir / "tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)

    index_tiles = []
    for (i, j), tile in sorted(tiles.items()):
        path = tiles_dir / f"t_{i}_{j}.json"
        write_json(path, {key: value for key, value in tile.items() if key != "top"})
        index_tiles.append(
            {
                "i": i,
                "j": j,
                "top": round(float(tile["top"]), 3),
                "path": f"tiles/t_{i}_{j}.json",
            }
        )

    anchors = []
    for item in route_anchors(contract):
        anchors.append(
            {
                "frame": int(item["frame"]),
                "location": [round(float(v), 4) for v in item["location"]],
                "target": [round(float(v), 4) for v in item["target"]],
                "lens": round(float(item.get("lens", 50.0)), 4),
            }
        )

    index = {
        "schema_version": 1,
        "lane": "coimbra-034-webgpu-feasibility",
        "tile_size": tile_size,
        "bounds_local": [
            round(float(xs.min()), 3),
            round(float(ys.min()), 3),
            round(float(xs.max()), 3),
            round(float(ys.max()), 3),
        ],
        "terrain": {
            "source": meta.get("source", "DGT MDT-2m"),
            "resolution_m": meta.get("terrain_resolution_m", 6.0),
            "z0": z0,
            "bbox_wgs84": meta.get("bbox_wgs84"),
            "bbox_epsg3763": meta.get("bbox_epsg3763"),
        },
        "city": {
            "source": "OpenStreetMap via Overpass API",
            "attribution": "© OpenStreetMap contributors · ODbL",
        },
        "route": {
            "source_contract": contract.get("id", contract_path.name),
            "duration_seconds": 24.0,
            "anchors": anchors,
        },
        "tiles": index_tiles,
    }
    write_json(out_dir / "index.json", index)
    return index


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Coimbra DGT/OSM data into small static WebGPU tiles."
    )
    parser.add_argument("--terrain", type=Path, default=DEFAULT_TERRAIN)
    parser.add_argument("--terrain-meta", type=Path, default=DEFAULT_TERRAIN_META)
    parser.add_argument("--osm", type=Path, default=DEFAULT_OSM)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--tile-size", type=float, default=250.0)
    args = parser.parse_args()

    for required in (args.terrain, args.terrain_meta, args.osm, args.contract):
        if not required.exists():
            raise SystemExit(f"Missing input: {required}")

    index = export_dataset(
        args.terrain,
        args.terrain_meta,
        args.osm,
        args.contract,
        args.out,
        args.tile_size,
    )
    print(
        json.dumps(
            {
                "out": str(args.out),
                "tiles": len(index["tiles"]),
                "route_anchors": len(index["route"]["anchors"]),
                "tile_size": index["tile_size"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
