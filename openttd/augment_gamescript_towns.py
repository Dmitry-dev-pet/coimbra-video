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
        "    town_fail = 0;\n"
        "    town_ids = [];\n",
        1,
    )

    old_bridge = r'''    function BuildBridge(item) {
        local start = GSMap.GetTileIndex(item[0], item[1]);
        local end = GSMap.GetTileIndex(item[2], item[3]);
        local length = item[4];
        local list = GSBridgeList_Length(length);
        if (list.IsEmpty()) return false;
        local bridge_type = list.Begin();
        return GSBridge.BuildBridge(GSVehicle.VT_ROAD, bridge_type, start, end);
    }

'''
    new_bridge = r'''    function TryBridgeCandidate(x0, y0, x1, y1) {
        if (x0 < 1 || y0 < 1 || x1 < 1 || y1 < 1) return false;
        if (x0 >= GSMap.GetMapSizeX() - 1 || x1 >= GSMap.GetMapSizeX() - 1) return false;
        if (y0 >= GSMap.GetMapSizeY() - 1 || y1 >= GSMap.GetMapSizeY() - 1) return false;
        if (x0 != x1 && y0 != y1) return false;

        local length = abs(x0 - x1) + abs(y0 - y1);
        if (length < 2) return false;
        local list = GSBridgeList_Length(length);
        if (list.IsEmpty()) return false;

        local start = GSMap.GetTileIndex(x0, y0);
        local end = GSMap.GetTileIndex(x1, y1);
        local bridge_type = list.Begin();
        if (!GSBridge.BuildBridge(GSVehicle.VT_ROAD, bridge_type, start, end)) return false;

        GSLog.Info(
            "Coimbra bridge built: " + x0 + "," + y0 + "->" + x1 + "," + y1 +
            " length=" + length
        );
        return true;
    }

    function BuildBridge(item) {
        local x0 = item[0];
        local y0 = item[1];
        local x1 = item[2];
        local y1 = item[3];

        if (this.TryBridgeCandidate(x0, y0, x1, y1)) return true;

        local dx = x1 > x0 ? 1 : (x1 < x0 ? -1 : 0);
        local dy = y1 > y0 ? 1 : (y1 < y0 ? -1 : 0);

        for (local trim = 1; trim <= 2; trim++) {
            local ax = x0 + dx * trim;
            local ay = y0 + dy * trim;
            local bx = x1 - dx * trim;
            local by = y1 - dy * trim;
            if (this.TryBridgeCandidate(ax, ay, bx, by)) return true;
        }

        local px = dx == 0 ? 1 : 0;
        local py = dy == 0 ? 1 : 0;
        for (local shift = 1; shift <= 3; shift++) {
            if (this.TryBridgeCandidate(
                x0 + px * shift, y0 + py * shift,
                x1 + px * shift, y1 + py * shift
            )) return true;
            if (this.TryBridgeCandidate(
                x0 - px * shift, y0 - py * shift,
                x1 - px * shift, y1 - py * shift
            )) return true;
        }
        return false;
    }

'''
    if old_bridge not in main:
        raise RuntimeError("could not locate generated BuildBridge()")
    main = main.replace(old_bridge, new_bridge, 1)

    old_tunnel = r'''    function BuildTunnel(item) {
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

'''
    new_tunnel = r'''    function TunnelEndNear(tile, expected_x, expected_y, radius) {
        if (tile == GSMap.TILE_INVALID) return false;
        local dx = abs(GSMap.GetTileX(tile) - expected_x);
        local dy = abs(GSMap.GetTileY(tile) - expected_y);
        return dx + dy <= radius;
    }

    function TryTunnelPortal(x, y, expected_x, expected_y, end_radius) {
        if (x < 1 || y < 1 || x >= GSMap.GetMapSizeX() - 1 || y >= GSMap.GetMapSizeY() - 1) return false;
        local start = GSMap.GetTileIndex(x, y);
        local actual = GSTunnel.GetOtherTunnelEnd(start);
        if (!this.TunnelEndNear(actual, expected_x, expected_y, end_radius)) return false;
        if (!GSTunnel.BuildTunnel(GSVehicle.VT_ROAD, start)) return false;

        GSLog.Info(
            "Coimbra tunnel built: portal=" + x + "," + y +
            " exit=" + GSMap.GetTileX(actual) + "," + GSMap.GetTileY(actual)
        );
        return true;
    }

    function BuildTunnel(item) {
        local x0 = item[0];
        local y0 = item[1];
        local x1 = item[2];
        local y1 = item[3];

        for (local radius = 0; radius <= 3; radius++) {
            for (local dx = -radius; dx <= radius; dx++) {
                for (local dy = -radius; dy <= radius; dy++) {
                    if (radius > 0 && dx != -radius && dx != radius && dy != -radius && dy != radius) continue;
                    if (this.TryTunnelPortal(x0 + dx, y0 + dy, x1, y1, 3)) return true;
                }
            }
        }
        for (local radius = 0; radius <= 3; radius++) {
            for (local dx = -radius; dx <= radius; dx++) {
                for (local dy = -radius; dy <= radius; dy++) {
                    if (radius > 0 && dx != -radius && dx != radius && dy != -radius && dy != radius) continue;
                    if (this.TryTunnelPortal(x1 + dx, y1 + dy, x0, y0, 3)) return true;
                }
            }
        }
        return false;
    }

'''
    if old_tunnel not in main:
        raise RuntimeError("could not locate generated BuildTunnel()")
    main = main.replace(old_tunnel, new_tunnel, 1)

    town_methods = r'''
    function TryFoundTown(item) {
        local edge_margin = 40;
        local base_x = max(edge_margin, min(GSMap.GetMapSizeX() - edge_margin - 1, item[0]));
        local base_y = max(edge_margin, min(GSMap.GetMapSizeY() - edge_margin - 1, item[1]));
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
                        GSTown.TOWN_SIZE_SMALL,
                        is_city,
                        GSTown.ROAD_LAYOUT_ORIGINAL,
                        town_name
                    )) {
                        local town_id = GSTile.GetClosestTown(tile);
                        if (!GSTown.IsValidTown(town_id)) break;
                        this.town_ids.append(town_id);
                        GSLog.Info(
                            "Coimbra town founded: " + town_name +
                            " population=" + GSTown.GetPopulation(town_id) +
                            " tile=" + x + "," + y
                        );
                        return true;
                    }
                }
            }
        }

        this.town_ids.append(-1);
        GSLog.Warning("Coimbra town failed: " + town_name);
        return false;
    }

    function FoundTowns() {
        require("towns.nut");
        foreach (item in COIMBRA_TOWNS) {
            this.TryFoundTown(item);
            this.Sleep(1);
        }
        GSLog.Info("Coimbra compact town anchors founded.");
    }

    function ValidateTowns() {
        local minimum_population = 1;

        foreach (i, item in COIMBRA_TOWNS) {
            local target_population = item[2];
            local town_name = item[4];
            local town_id = this.town_ids[i];

            if (!GSTown.IsValidTown(town_id)) {
                this.town_fail++;
                GSLog.Warning("Coimbra town invalid after OSM transport build: " + town_name);
                continue;
            }

            local final_population = GSTown.GetPopulation(town_id);
            local tile = GSTown.GetLocation(town_id);
            local x = GSMap.GetTileX(tile);
            local y = GSMap.GetTileY(tile);

            GSLog.Info(
                "Coimbra town built: " + town_name +
                " population=" + final_population +
                " target=" + target_population +
                " minimum=" + minimum_population +
                " tile=" + x + "," + y
            );

            if (final_population < minimum_population) {
                this.town_fail++;
                GSLog.Warning("Coimbra town below minimum urban population: " + town_name);
            } else {
                this.town_ok++;
            }
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
        '        // 005: build the OSM transport network before any town exists.\n'
        '        GSRoad.SetCurrentRoadType(GSRoad.ROADTYPE_ROAD);\n',
        1,
    )

    completion_marker = '        this.completed = true;\n'
    if completion_marker not in main:
        raise RuntimeError("could not locate network completion marker")
    main = main.replace(
        completion_marker,
        '        // 005: found compact town anchors only after OSM transport is complete.\n'
        '        this.FoundTowns();\n'
        '        this.ValidateTowns();\n'
        '        this.completed = true;\n',
        1,
    )

    main_path.write_text(main, encoding="utf-8")

    info = info_path.read_text(encoding="utf-8")
    info = info.replace(
        'function GetDescription() { return "Builds the quantized real Coimbra road, bridge and tunnel network."; }',
        'function GetDescription() { return "Builds the real Coimbra OSM network first, then adds compact town anchors without expansion."; }',
        1,
    )
    info = info.replace("function GetVersion() { return 2; }", "function GetVersion() { return 5; }", 1)
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
