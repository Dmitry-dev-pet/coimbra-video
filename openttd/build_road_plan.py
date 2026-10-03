#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw
from pyproj import Transformer


def norm_edge(a, b):
    return (a, b) if a <= b else (b, a)


def manhattan_segment(a, b):
    """Return a 4-connected approximation including both endpoints."""
    x0, y0 = a
    x1, y1 = b
    x, y = x0, y0
    out = [(x, y)]
    dx = x1 - x0
    dy = y1 - y0
    sx = 1 if dx > 0 else -1
    sy = 1 if dy > 0 else -1
    ax = abs(dx)
    ay = abs(dy)
    moved_x = 0
    moved_y = 0
    while (x, y) != (x1, y1):
        if x == x1:
            y += sy
            moved_y += 1
        elif y == y1:
            x += sx
            moved_x += 1
        else:
            # Choose the next axis that best preserves progress along the
            # original segment. This alternates cleanly for diagonal lines.
            tx = (moved_x + 1) / ax if ax else 1e9
            ty = (moved_y + 1) / ay if ay else 1e9
            if tx <= ty:
                x += sx
                moved_x += 1
            else:
                y += sy
                moved_y += 1
        out.append((x, y))
    return out


def polyline_cells(points):
    out = []
    for i in range(len(points) - 1):
        part = manhattan_segment(points[i], points[i + 1])
        if out and part and out[-1] == part[0]:
            part = part[1:]
        out.extend(part)
    return out


def compress_cells(cells):
    if len(cells) < 2:
        return []
    runs = []
    start = cells[0]
    prev = cells[0]
    direction = None
    for cur in cells[1:]:
        step = (cur[0] - prev[0], cur[1] - prev[1])
        if direction is None:
            direction = step
        elif step != direction:
            runs.append((start, prev))
            start = prev
            direction = step
        prev = cur
    if start != prev:
        runs.append((start, prev))
    return runs


def classify_structure(props, config):
    layer_raw = props.get("layer")
    try:
        layer = int(layer_raw) if layer_raw not in (None, "") else 0
    except ValueError:
        layer = 0
    bridge = props.get("bridge")
    tunnel = props.get("tunnel")
    if tunnel not in (None, "", "no"):
        return "tunnel", layer
    if bridge not in (None, "", "no"):
        return "bridge", layer
    if config.get("tunnel_from_negative_layer") and layer < 0:
        return "tunnel", layer
    if config.get("bridge_from_positive_layer") and layer > 0:
        return "bridge", layer
    return "ground", layer


def projector(bounds, map_size):
    xmin, ymin, xmax, ymax = bounds
    to3763 = Transformer.from_crs("EPSG:4326", "EPSG:3763", always_xy=True)

    def to_tile(lon, lat):
        e, n = to3763.transform(float(lon), float(lat))
        col = round((e - xmin) / (xmax - xmin) * (map_size - 1))
        row = round((ymax - n) / (ymax - ymin) * (map_size - 1))
        # OpenTTD axes are swapped relative to image rows/columns.
        x = max(0, min(map_size - 1, int(row)))
        y = max(0, min(map_size - 1, int(col)))
        return (x, y)

    return to_tile


def build_plan(network, manifest, config):
    map_size = int(config["map_size"])
    bounds = manifest["crop_bbox_epsg3763"]
    to_tile = projector(bounds, map_size)
    allowed = set(config["include_highways"])
    ground_edges = {}
    structures = []
    excluded = defaultdict(int)

    for feature in network.get("features", []):
        props = feature.get("properties") or {}
        highway = props.get("highway")
        if highway not in allowed:
            excluded[str(highway)] += 1
            continue
        coords = feature.get("geometry", {}).get("coordinates") or []
        snapped = []
        for lon, lat in coords:
            p = to_tile(lon, lat)
            if not snapped or snapped[-1] != p:
                snapped.append(p)
        if len(snapped) < 2:
            excluded["collapsed"] += 1
            continue

        cells = polyline_cells(snapped)
        structure, layer = classify_structure(props, config)
        meta = {
            "osm_id": props.get("osm_id"),
            "highway": highway,
            "name": props.get("name"),
            "layer": layer,
        }

        if structure == "ground":
            for a, b in zip(cells, cells[1:]):
                if a == b:
                    continue
                key = norm_edge(a, b)
                if key not in ground_edges:
                    ground_edges[key] = meta
        else:
            for a, b in compress_cells(cells):
                length = abs(a[0] - b[0]) + abs(a[1] - b[1])
                if length < int(config["minimum_structure_tiles"]):
                    excluded[f"{structure}_too_short"] += 1
                    continue
                structures.append({
                    **meta,
                    "kind": structure,
                    "start": list(a),
                    "end": list(b),
                    "length_tiles": length,
                })

    edges = [
        {
            "start": list(a),
            "end": list(b),
            **meta,
        }
        for (a, b), meta in sorted(ground_edges.items())
    ]

    # Keep exact structure duplicates out without ever flattening them to ground.
    unique_structures = {}
    for item in structures:
        key = (
            item["kind"],
            tuple(item["start"]),
            tuple(item["end"]),
            item["layer"],
        )
        reverse = (
            item["kind"],
            tuple(item["end"]),
            tuple(item["start"]),
            item["layer"],
        )
        if reverse in unique_structures:
            continue
        unique_structures[key] = item

    bridges = [v for v in unique_structures.values() if v["kind"] == "bridge"]
    tunnels = [v for v in unique_structures.values() if v["kind"] == "tunnel"]
    return {
        "version": config["version"],
        "map_size": [map_size, map_size],
        "ground_edges": edges,
        "bridges": bridges,
        "tunnels": tunnels,
        "excluded": dict(sorted(excluded.items())),
        "rules": {
            "grade_separated_edges_never_demoted_to_ground": True,
            "axes_swapped_for_openttd": True,
            "four_connected_quantization": True,
        },
    }


def squirrel_array(items):
    return "[\n" + ",\n".join("  " + json.dumps(i, separators=(",", ":")) for i in items) + "\n]"


def write_gamescript(plan, out_dir, api_version):
    game = out_dir / "game" / "CoimbraBuilder"
    game.mkdir(parents=True, exist_ok=True)
    roads = [[*x["start"], *x["end"]] for x in plan["ground_edges"]]
    bridges = [[*x["start"], *x["end"], x["length_tiles"]] for x in plan["bridges"]]
    tunnels = [[*x["start"], *x["end"], x["length_tiles"]] for x in plan["tunnels"]]

    (game / "plan.nut").write_text(
        "::COIMBRA_MAP_X <- %d;\n::COIMBRA_MAP_Y <- %d;\n"
        "::COIMBRA_ROADS <- %s;\n::COIMBRA_BRIDGES <- %s;\n::COIMBRA_TUNNELS <- %s;\n"
        % (
            plan["map_size"][0],
            plan["map_size"][1],
            squirrel_array(roads),
            squirrel_array(bridges),
            squirrel_array(tunnels),
        ),
        encoding="utf-8",
    )

    (game / "info.nut").write_text(
        f'''class CoimbraBuilderInfo extends GSInfo {{
    function GetAuthor() {{ return "Dmitry-dev-pet"; }}
    function GetName() {{ return "Coimbra Builder"; }}
    function GetShortName() {{ return "COIM"; }}
    function GetDescription() {{ return "Builds the quantized real Coimbra road, bridge and tunnel network."; }}
    function GetVersion() {{ return 2; }}
    function MinVersionToLoad() {{ return 2; }}
    function GetDate() {{ return "2026-10-03"; }}
    function CreateInstance() {{ return "CoimbraBuilder"; }}
    function GetAPIVersion() {{ return "{api_version}"; }}
}}
RegisterGS(CoimbraBuilderInfo());
''',
        encoding="utf-8",
    )

    (game / "main.nut").write_text(
        '''require("plan.nut");

class CoimbraBuilder extends GSController {
    function BuildBridge(item) {
        local start = GSMap.GetTileIndex(item[0], item[1]);
        local end = GSMap.GetTileIndex(item[2], item[3]);
        local length = item[4];
        local list = GSBridgeList_Length(length);
        if (list.IsEmpty()) return false;
        local bridge_type = list.Begin();
        return GSBridge.BuildBridge(GSVehicle.VT_ROAD, bridge_type, start, end);
    }

    function BuildTunnel(item) {
        local start = GSMap.GetTileIndex(item[0], item[1]);
        local expected = GSMap.GetTileIndex(item[2], item[3]);
        local actual = GSTunnel.GetOtherTunnelEnd(start);
        if (actual == expected) return GSTunnel.BuildTunnel(GSVehicle.VT_ROAD, start);

        local reverse_start = expected;
        local reverse_expected = start;
        actual = GSTunnel.GetOtherTunnelEnd(reverse_start);
        if (actual == reverse_expected) return GSTunnel.BuildTunnel(GSVehicle.VT_ROAD, reverse_start);
        return false;
    }

    function Start() {
        if (GSMap.GetMapSizeX() != COIMBRA_MAP_X || GSMap.GetMapSizeY() != COIMBRA_MAP_Y) {
            GSLog.Error("Coimbra Builder requires the matching 512x512 Coimbra heightmap.");
            return;
        }

        GSRoad.SetCurrentRoadType(GSRoad.ROADTYPE_ROAD);
        local bridge_ok = 0;
        local bridge_fail = 0;
        local tunnel_ok = 0;
        local tunnel_fail = 0;
        local road_ok = 0;
        local road_fail = 0;
        local op = 0;

        foreach (item in COIMBRA_BRIDGES) {
            if (this.BuildBridge(item)) bridge_ok++; else bridge_fail++;
            if (++op % 100 == 0) this.Sleep(1);
        }
        foreach (item in COIMBRA_TUNNELS) {
            if (this.BuildTunnel(item)) tunnel_ok++; else tunnel_fail++;
            if (++op % 100 == 0) this.Sleep(1);
        }
        foreach (item in COIMBRA_ROADS) {
            local start = GSMap.GetTileIndex(item[0], item[1]);
            local end = GSMap.GetTileIndex(item[2], item[3]);
            if (GSRoad.AreRoadTilesConnected(start, end) || GSRoad.BuildRoad(start, end)) {
                road_ok++;
            } else {
                road_fail++;
            }
            if (++op % 200 == 0) this.Sleep(1);
        }

        GSLog.Info("Coimbra network build complete.");
        GSLog.Info("roads ok=" + road_ok + " fail=" + road_fail);
        GSLog.Info("bridges ok=" + bridge_ok + " fail=" + bridge_fail);
        GSLog.Info("tunnels ok=" + tunnel_ok + " fail=" + tunnel_fail);

        while (true) this.Sleep(740);
    }

    function Save() {
        return {};
    }

    function Load(version, data) {
    }
}
''',
        encoding="utf-8",
    )
    (game / "README.txt").write_text(
        "Coimbra Builder GameScript\n"
        "Install this CoimbraBuilder directory in your OpenTTD game/ directory.\n"
        "Select 'Coimbra Builder' before starting the matching 512x512 Coimbra map.\n"
        "The script builds structures first, then surface roads. Bridge/tunnel candidates\n"
        "that cannot be represented by the imported terrain are skipped, never flattened.\n",
        encoding="utf-8",
    )
    return game


def draw_preview(heightmap_path, plan, out):
    image = Image.open(heightmap_path).convert("RGB")
    draw = ImageDraw.Draw(image)

    def imgxy(tile):
        return (tile[1], tile[0])

    for e in plan["ground_edges"]:
        draw.line([imgxy(e["start"]), imgxy(e["end"])], fill=(245, 220, 120), width=1)
    for item in plan["bridges"]:
        draw.line([imgxy(item["start"]), imgxy(item["end"])], fill=(80, 210, 255), width=2)
    for item in plan["tunnels"]:
        draw.line([imgxy(item["start"]), imgxy(item["end"])], fill=(255, 110, 110), width=2)

    image.save(out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--network", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--heightmap", type=Path, required=True)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    network = json.loads(args.network.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    config = json.loads(args.config.read_text(encoding="utf-8"))
    plan = build_plan(network, manifest, config)

    args.out.mkdir(parents=True, exist_ok=True)
    plan_path = args.out / "coimbra-road-plan.json"
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    draw_preview(args.heightmap, plan, args.out / "coimbra-road-preview.png")
    write_gamescript(plan, args.out, config["gamescript_api_version"])

    summary = {
        "version": config["version"],
        "openttd_target": config["openttd_target"],
        "map_size": plan["map_size"],
        "ground_edges": len(plan["ground_edges"]),
        "bridge_candidates": len(plan["bridges"]),
        "tunnel_candidates": len(plan["tunnels"]),
        "excluded": plan["excluded"],
        "gamescript": "game/CoimbraBuilder",
        "runtime_note": "GameScript attempts bridges/tunnels first and never demotes failed grade-separated structures to ground roads."
    }
    (args.out / "road-plan-manifest.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
