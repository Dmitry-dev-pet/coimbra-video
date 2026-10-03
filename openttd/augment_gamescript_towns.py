#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def clamp_tile(value: float, map_size: int) -> int:
    return max(1, min(map_size - 2, round(float(value) * (map_size - 1))))


def build_town_plan(towns: list[dict], map_size: int) -> list[dict]:
    plan = []
    for town in towns:
        plan.append(
            {
                "name": str(town["name"]),
                "x": clamp_tile(town["x"], map_size),
                "y": clamp_tile(town["y"], map_size),
                "population": int(town["population"]),
                "city": bool(town.get("city", False)),
            }
        )
    return plan


def squirrel_array(items: list[list]) -> str:
    return "[\n" + ",\n".join(
        "  " + json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        for item in items
    ) + "\n]"


def augment_game(game_dir: Path, plan: list[dict]) -> None:
    main_path = game_dir / "main.nut"
    info_path = game_dir / "info.nut"
    if not main_path.exists() or not info_path.exists():
        raise FileNotFoundError("expected generated CoimbraBuilder main.nut and info.nut")

    town_items = [
        [t["x"], t["y"], t["population"], t["city"], t["name"]]
        for t in plan
    ]
    (game_dir / "towns.nut").write_text(
        "::COIMBRA_TOWNS <- %s;\n" % squirrel_array(town_items),
        encoding="utf-8",
    )

    main = main_path.read_text(encoding="utf-8")
    if "town_ok = 0;" in main:
        raise RuntimeError("GameScript already contains the 004 town layer")

    main = main.replace(
        "    completed = false;\n",
        "    completed = false;\n"
        "    town_ok = 0;\n"
        "    town_fail = 0;\n",
        1,
    )

    town_methods = r'''
    function TryFoundTown(item) {
        // Keep large towns enough room to grow at the cropped map edge.
        // The original normalized coordinate remains the anchor; this guard
        // only nudges an edge town inward before the bounded local search.
        local edge_margin = 40;
        local base_x = max(edge_margin, min(GSMap.GetMapSizeX() - edge_margin - 1, item[0]));
        local base_y = max(edge_margin, min(GSMap.GetMapSizeY() - edge_margin - 1, item[1]));
        local target_population = item[2];
        local is_city = item[3];
        local town_name = item[4];

        for (local radius = 0; radius <= 12; radius++) {
            for (local dx = -radius; dx <= radius; dx++) {
                for (local dy = -radius; dy <= radius; dy++) {
                    if (radius > 0 && dx != -radius && dx != radius && dy != -radius && dy != radius) continue;

                    local x = base_x + dx;
                    local y = base_y + dy;
                    if (x <= 0 || y <= 0 || x >= GSMap.GetMapSizeX() - 1 || y >= GSMap.GetMapSizeY() - 1) continue;

                    local tile = GSMap.GetTileIndex(x, y);
                    if (!GSMap.IsValidTile(tile) || !GSTile.IsBuildable(tile)) continue;

                    if (GSTown.FoundTown(
                        tile,
                        GSTown.TOWN_SIZE_LARGE,
                        is_city,
                        GSTown.ROAD_LAYOUT_ORIGINAL,
                        town_name
                    )) {
                        local town_id = GSTile.GetClosestTown(tile);
                        if (!GSTown.IsValidTown(town_id)) return true;

                        for (local grow_round = 0; grow_round < 256; grow_round++) {
                            if (GSTown.GetPopulation(town_id) >= target_population) break;
                            GSTown.ExpandTown(town_id, 50);
                            this.Sleep(1);
                        }

                        local final_population = GSTown.GetPopulation(town_id);
                        GSLog.Info(
                            "Coimbra town built: " + town_name +
                            " population=" + final_population +
                            " target=" + target_population +
                            " tile=" + x + "," + y
                        );
                        if (final_population < target_population) {
                            GSLog.Warning("Coimbra town below target: " + town_name);
                            return false;
                        }
                        return true;
                    }
                }
            }
        }

        GSLog.Warning("Coimbra town failed: " + town_name);
        return false;
    }

    function BuildTowns() {
        require("towns.nut");
        foreach (item in COIMBRA_TOWNS) {
            if (this.TryFoundTown(item)) this.town_ok++; else this.town_fail++;
            this.Sleep(1);
        }
        ::COIMBRA_TOWNS = null;
        GSLog.Info("Coimbra urban layer complete.");
        GSLog.Info("towns ok=" + this.town_ok + " fail=" + this.town_fail);
    }

'''
    marker = "    function Start() {\n"
    if marker not in main:
        raise RuntimeError("could not locate Start() in generated GameScript")
    main = main.replace(marker, town_methods + marker, 1)

    road_marker = '        GSRoad.SetCurrentRoadType(GSRoad.ROADTYPE_ROAD);\n'
    if road_marker not in main:
        raise RuntimeError("could not locate road initialization in generated GameScript")
    main = main.replace(
        road_marker,
        '        // Build towns first while terrain is still open; OSM transport follows.\n'
        '        this.BuildTowns();\n'
        '        GSRoad.SetCurrentRoadType(GSRoad.ROADTYPE_ROAD);\n',
        1,
    )
    main_path.write_text(main, encoding="utf-8")

    info = info_path.read_text(encoding="utf-8")
    info = info.replace(
        'function GetDescription() { return "Builds the quantized real Coimbra road, bridge and tunnel network."; }',
        'function GetDescription() { return "Builds the real Coimbra transport network plus four named urban districts."; }',
        1,
    )
    info = info.replace("function GetVersion() { return 2; }", "function GetVersion() { return 3; }", 1)
    info_path.write_text(info, encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--towns", type=Path, required=True)
    p.add_argument("--game-dir", type=Path, required=True)
    p.add_argument("--map-size", type=int, default=512)
    p.add_argument("--out-plan", type=Path, required=True)
    args = p.parse_args()

    towns = json.loads(args.towns.read_text(encoding="utf-8"))
    plan = build_town_plan(towns, args.map_size)
    if len(plan) != 4:
        raise ValueError(f"expected exactly 4 Coimbra towns, got {len(plan)}")

    augment_game(args.game_dir, plan)
    args.out_plan.parent.mkdir(parents=True, exist_ok=True)
    args.out_plan.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"town_count": len(plan), "towns": plan}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
