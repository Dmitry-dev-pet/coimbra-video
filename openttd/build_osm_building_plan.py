#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import re


SKIP_BUILDING_TYPES = {
    "garage",
    "garages",
    "roof",
    "shed",
    "carport",
    "construction",
    "ruins",
    "industrial",
    "farm_auxiliary",
    "storage_tank",
    "service",
}


def polygon_centroid_area(points: list[list[float]]) -> tuple[float, float, float] | None:
    pts = list(points)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return None

    twice_area = 0.0
    cx = 0.0
    cy = 0.0
    for i, p in enumerate(pts):
        q = pts[(i + 1) % len(pts)]
        cross = float(p[0]) * float(q[1]) - float(q[0]) * float(p[1])
        twice_area += cross
        cx += (float(p[0]) + float(q[0])) * cross
        cy += (float(p[1]) + float(q[1])) * cross

    if abs(twice_area) < 1e-9:
        return (
            sum(float(p[0]) for p in pts) / len(pts),
            sum(float(p[1]) for p in pts) / len(pts),
            0.0,
        )

    # Polygon centroid uses 1/(3 * twice_area).
    return cx / (3.0 * twice_area), cy / (3.0 * twice_area), abs(twice_area) / 2.0


def to_tile(
    local_x: float,
    local_y: float,
    *,
    center: tuple[float, float],
    bounds: tuple[float, float, float, float],
    map_size: int,
) -> tuple[int, int]:
    xmin, ymin, xmax, ymax = bounds
    easting = center[0] + local_x
    northing = center[1] + local_y
    col = round((easting - xmin) / (xmax - xmin) * (map_size - 1))
    row = round((ymax - northing) / (ymax - ymin) * (map_size - 1))
    # OpenTTD axes are swapped relative to image rows / columns.
    return int(row), int(col)


def parse_town_locations(path: Path) -> dict[str, dict[str, int]]:
    text = path.read_text(errors="replace")
    pattern = re.compile(
        r"Coimbra town built: (.+?) population=(\d+) target=(\d+) "
        r"minimum=(\d+) tile=(\d+),(\d+)"
    )
    result = {}
    for source_order, (name, population, target, minimum, x, y) in enumerate(pattern.findall(text)):
        result[name] = {
            "source_order": source_order,
            "population": int(population),
            "target_population": int(target),
            "minimum_population": int(minimum),
            "x": int(x),
            "y": int(y),
        }
    if len(result) != 4:
        raise ValueError(f"expected four exact towns in source log, got {sorted(result)}")
    return result


def house_profile(kind: str, area_m2: float) -> tuple[int, int, str] | None:
    kind = kind.lower()

    if kind in {"chapel", "church", "temple"}:
        return 0x03, 5, "civic"
    if kind in {"apartments", "dormitory", "hotel"}:
        return 0x1B, 100, "medium"
    if kind in {"commercial", "retail", "office"}:
        return 0x0E, 95, "medium"
    if kind in {"house", "detached", "semidetached_house", "bungalow"}:
        return 0x1A, 13, "low"
    if kind == "terrace":
        return 0x06, 30, "low"
    if kind in {"residential", "yes"}:
        if area_m2 >= 500.0:
            return 0x1B, 100, "medium"
        if area_m2 >= 160.0:
            return 0x06, 30, "low"
        return 0x1A, 13, "low"
    return None


def spread_key(candidate: dict) -> tuple[int, int]:
    value = (
        candidate["x"] * 73856093
        ^ candidate["y"] * 19349663
        ^ candidate["osm_id"] * 83492791
    ) & 0xFFFFFFFF
    return value, candidate["osm_id"]


def closest_town_name(candidate: dict, exact_towns: dict[str, dict[str, int]]) -> str:
    """Match OpenTTD 15.3 CalcClosestTownFromTile / Kdtree::FindNearest.

    OpenTTD's town k-d tree uses Manhattan distance, not Euclidean distance.
    Equal distances are resolved by the smaller TownID. The source 005 build log
    is emitted in the same creation order, recorded as source_order below.
    """
    return min(
        exact_towns,
        key=lambda name: (
            abs(candidate["x"] - exact_towns[name]["x"])
            + abs(candidate["y"] - exact_towns[name]["y"]),
            exact_towns[name]["source_order"],
        ),
    )


def build_plan(
    osm: dict,
    manifest: dict,
    towns: list[dict],
    exact_towns: dict[str, dict[str, int]],
    *,
    map_size: int,
    radius_tiles: int,
) -> dict:
    center = tuple(float(v) for v in osm["center_epsg3763"])
    bounds = tuple(float(v) for v in manifest["crop_bbox_epsg3763"])
    nodes = osm["nodes"]

    by_tile: dict[tuple[int, int], dict] = {}
    rejected = Counter()

    for way in osm.get("ways", []):
        tags = way.get("tags") or {}
        kind = str(tags.get("building") or "").lower()
        if not kind:
            rejected["not_building"] += 1
            continue
        if kind in SKIP_BUILDING_TYPES:
            rejected[f"skip:{kind}"] += 1
            continue

        points = []
        for node_id in way.get("nodes", []):
            node = nodes.get(str(node_id))
            if node and node.get("xy"):
                points.append(node["xy"])

        geometry = polygon_centroid_area(points)
        if geometry is None:
            rejected["bad_geometry"] += 1
            continue
        local_x, local_y, area_m2 = geometry

        profile = house_profile(kind, area_m2)
        if profile is None:
            rejected[f"unsupported:{kind}"] += 1
            continue

        x, y = to_tile(
            local_x,
            local_y,
            center=center,
            bounds=bounds,
            map_size=map_size,
        )
        if not (1 <= x < map_size - 1 and 1 <= y < map_size - 1):
            rejected["outside_crop"] += 1
            continue

        house_id, population, urban_class = profile
        candidate = {
            "osm_id": int(way["id"]),
            "x": x,
            "y": y,
            "area_m2": round(float(area_m2), 2),
            "building": kind,
            "house_id": int(house_id),
            "population": int(population),
            "urban_class": urban_class,
        }

        tile = (x, y)
        previous = by_tile.get(tile)
        if previous is None or candidate["area_m2"] > previous["area_m2"]:
            if previous is not None:
                rejected["duplicate_tile_replaced"] += 1
            by_tile[tile] = candidate
        else:
            rejected["duplicate_tile_dropped"] += 1

    grouped: dict[str, list[dict]] = defaultdict(list)
    for candidate in by_tile.values():
        nearest_name = closest_town_name(candidate, exact_towns)
        town = exact_towns[nearest_name]
        distance = math.hypot(candidate["x"] - town["x"], candidate["y"] - town["y"])
        if distance > radius_tiles:
            rejected["outside_town_radius"] += 1
            continue
        candidate = {**candidate, "distance_tiles": round(distance, 3)}
        grouped[nearest_name].append(candidate)

    target_lookup = {item["name"]: int(item["population"]) for item in towns}
    output_groups = []
    for name in exact_towns:
        candidates = sorted(grouped[name], key=spread_key)
        classes = Counter(c["urban_class"] for c in candidates)
        kinds = Counter(c["building"] for c in candidates)
        output_groups.append(
            {
                "name": name,
                "source_population": exact_towns[name]["population"],
                "target_population": target_lookup[name],
                "town_tile": [exact_towns[name]["x"], exact_towns[name]["y"]],
                "candidate_count": len(candidates),
                "class_counts": dict(sorted(classes.items())),
                "building_counts": dict(sorted(kinds.items())),
                "candidates": candidates,
            }
        )

    if len(output_groups) != 4:
        raise ValueError("expected exactly four town candidate groups")
    for group in output_groups:
        if group["candidate_count"] < 100:
            raise ValueError(
                f"insufficient OSM building candidates for {group['name']}: "
                f"{group['candidate_count']}"
            )

    return {
        "version": "coimbra-openttd-008-building-plan-v2",
        "source": "pinned bridge_osm_oss_local.json from Coimbra 009A",
        "town_assignment": "OpenTTD 15.3 Manhattan nearest-town semantics",
        "map_size": map_size,
        "radius_tiles": radius_tiles,
        "center_epsg3763": list(center),
        "crop_bbox_epsg3763": list(bounds),
        "unique_candidate_tiles": sum(g["candidate_count"] for g in output_groups),
        "towns": output_groups,
        "rejected": dict(sorted(rejected.items())),
    }


def write_nut(plan: dict, path: Path) -> None:
    lines = [
        "// Generated by openttd/build_osm_building_plan.py",
        "// Pinned OSM building-centroid candidates; do not edit by hand.",
        "::COIMBRA_BUILDING_SITES <- [",
    ]
    for group in plan["towns"]:
        lines.append(f"    [{json.dumps(group['name'], ensure_ascii=False)}, [")
        for c in group["candidates"]:
            lines.append(
                "        ["
                + ", ".join(
                    map(
                        str,
                        [
                            c["x"],
                            c["y"],
                            c["house_id"],
                            c["population"],
                            c["osm_id"],
                        ],
                    )
                )
                + "],"
            )
        lines.append("    ]],")
    lines.append("];")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--osm", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--towns", type=Path, required=True)
    parser.add_argument("--town-log", type=Path, required=True)
    parser.add_argument("--map-size", type=int, default=512)
    parser.add_argument("--radius-tiles", type=int, default=150)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-nut", type=Path, required=True)
    args = parser.parse_args()

    osm = json.loads(args.osm.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    towns = json.loads(args.towns.read_text(encoding="utf-8"))
    exact_towns = parse_town_locations(args.town_log)

    plan = build_plan(
        osm,
        manifest,
        towns,
        exact_towns,
        map_size=args.map_size,
        radius_tiles=args.radius_tiles,
    )
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(plan, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_nut(plan, args.out_nut)

    summary = {
        "version": plan["version"],
        "unique_candidate_tiles": plan["unique_candidate_tiles"],
        "towns": [
            {
                "name": group["name"],
                "candidate_count": group["candidate_count"],
                "class_counts": group["class_counts"],
            }
            for group in plan["towns"]
        ],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
