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
        "    density_upgrade = false;\n"
        "    density_house_ok = 0;\n"
        "    density_house_fail = 0;\n"
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
    function HasAdjacentRoad(x, y) {
        local neighbours = [[x - 1, y], [x + 1, y], [x, y - 1], [x, y + 1]];
        foreach (p in neighbours) {
            if (p[0] <= 0 || p[1] <= 0 || p[0] >= GSMap.GetMapSizeX() - 1 || p[1] >= GSMap.GetMapSizeY() - 1) continue;
            local road_tile = GSMap.GetTileIndex(p[0], p[1]);
            if (GSMap.IsValidTile(road_tile) && GSRoad.IsRoadTile(road_tile)) return true;
        }
        return false;
    }

    function TryFoundTown(item) {
        local edge_margin = 40;
        local base_x = max(edge_margin, min(GSMap.GetMapSizeX() - edge_margin - 1, item[0]));
        local base_y = max(edge_margin, min(GSMap.GetMapSizeY() - edge_margin - 1, item[1]));
        local is_city = item[3];
        local town_name = item[4];

        for (local pass = 0; pass < 2; pass++) {
            local require_road = pass == 0;
            local max_radius = require_road ? 24 : 12;

            for (local radius = 0; radius <= max_radius; radius++) {
                for (local dx = -radius; dx <= radius; dx++) {
                    for (local dy = -radius; dy <= radius; dy++) {
                        if (radius > 0 && dx != -radius && dx != radius && dy != -radius && dy != radius) continue;

                        local x = base_x + dx;
                        local y = base_y + dy;
                        if (x <= 0 || y <= 0 || x >= GSMap.GetMapSizeX() - 1 || y >= GSMap.GetMapSizeY() - 1) continue;

                        local tile = GSMap.GetTileIndex(x, y);
                        if (!GSMap.IsValidTile(tile) || !GSTile.IsBuildable(tile)) continue;
                        if (require_road && !this.HasAdjacentRoad(x, y)) continue;

                        if (GSTown.FoundTown(
                            tile,
                            GSTown.TOWN_SIZE_SMALL,
                            is_city,
                            GSTown.ROAD_LAYOUT_ORIGINAL,
                            town_name
                        )) {
                            local town_id = GSTile.GetClosestTown(tile);
                            if (!GSTown.IsValidTown(town_id)) break;

                            GSTown.SetGrowthRate(town_id, GSTown.TOWN_GROWTH_NONE);

                            this.town_ids.append(town_id);
                            GSLog.Info(
                                "Coimbra town founded: " + town_name +
                                " population=" + GSTown.GetPopulation(town_id) +
                                " tile=" + x + "," + y +
                                " adjacent_osm_road=" + (require_road ? "yes" : "fallback")
                            );
                            return true;
                        }
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

    function AttachExistingTowns() {
        require("towns.nut");
        this.town_ids = [];
        local towns = GSTownList();

        foreach (item in COIMBRA_TOWNS) {
            local wanted_name = item[4];
            local found_id = -1;

            for (local town_id = towns.Begin(); !towns.IsEnd(); town_id = towns.Next()) {
                if (GSTown.GetName(town_id) == wanted_name) {
                    found_id = town_id;
                    break;
                }
            }

            this.town_ids.append(found_id);
            if (!GSTown.IsValidTown(found_id)) {
                GSLog.Error("Coimbra 008 source town missing: " + wanted_name);
                return false;
            }

            GSLog.Info(
                "Coimbra 008 source town attached: " + wanted_name +
                " population=" + GSTown.GetPopulation(found_id) +
                " tile=" + GSMap.GetTileX(GSTown.GetLocation(found_id)) + "," +
                GSMap.GetTileY(GSTown.GetLocation(found_id))
            );
        }

        GSLog.Info("Coimbra 008 attached all four towns from verified 005 save.");
        return true;
    }

    function RoadFingerprint() {
        local count = 0;
        local checksum = 0;
        local size_x = GSMap.GetMapSizeX();
        local size_y = GSMap.GetMapSizeY();
        local scanned = 0;

        for (local y = 0; y < size_y; y++) {
            for (local x = 0; x < size_x; x++) {
                local tile = GSMap.GetTileIndex(x, y);
                if (GSRoad.IsRoadTile(tile)) {
                    count++;
                    checksum = (checksum + tile) % 2147483647;
                }
                scanned++;
                if (scanned % 4096 == 0) this.Sleep(1);
            }
        }
        return [count, checksum];
    }

    function FindBuildingSites(town_name) {
        foreach (group in COIMBRA_BUILDING_SITES) {
            if (group[0] == town_name) return group[1];
        }
        return null;
    }

    function HouseClass(house_id) {
        if (house_id == 0x1B || house_id == 0x0E) return 2;
        if (house_id == 0x03) return 3;
        return 1;
    }

    function PlaceOsmFootprintFabricLocked() {
        local before = this.RoadFingerprint();
        GSLog.Info(
            "Coimbra 008 road fingerprint before count=" + before[0] +
            " checksum=" + before[1]
        );

        require("building-sites.nut");

        foreach (i, item in COIMBRA_TOWNS) {
            local town_id = this.town_ids[i];
            if (!GSTown.IsValidTown(town_id)) continue;

            local town_name = item[4];
            local target_population = item[2];
            local population_before = GSTown.GetPopulation(town_id);
            local sites = this.FindBuildingSites(town_name);
            if (sites == null || sites.len() < 100) {
                GSLog.Error("Coimbra 008 OSM site plan missing or too small: " + town_name);
                return false;
            }

            local placed = 0;
            local low_rise = 0;
            local medium_rise = 0;
            local civic = 0;
            local source_low_rise = 0;
            local source_medium_rise = 0;
            local source_civic = 0;
            local source_sites_checked = 0;
            local wrong_town = 0;
            local blocked = 0;

            foreach (site in sites) {
                local x = site[0];
                local y = site[1];
                local house_id = site[2];
                local expected_population = site[3];
                local osm_id = site[4];
                source_sites_checked++;

                if (x <= 0 || y <= 0 || x >= GSMap.GetMapSizeX() - 1 || y >= GSMap.GetMapSizeY() - 1) continue;
                local tile = GSMap.GetTileIndex(x, y);
                if (!GSMap.IsValidTile(tile) || !GSTile.IsBuildable(tile)) {
                    blocked++;
                    continue;
                }

                // build_osm_building_plan.py mirrors OpenTTD 15.3's Manhattan
                // nearest-town rule. Keep this runtime check as falsification evidence.
                if (GSTile.GetClosestTown(tile) != town_id) {
                    wrong_town++;
                    continue;
                }

                local house_class = this.HouseClass(house_id);
                if (house_class == 2) {
                    source_medium_rise++;
                } else if (house_class == 3) {
                    source_civic++;
                } else {
                    source_low_rise++;
                }

                if (GSTown.GetPopulation(town_id) >= target_population) {
                    if (source_sites_checked % 128 == 0) this.Sleep(1);
                    continue;
                }

                local remaining = target_population - GSTown.GetPopulation(town_id);
                if (remaining <= 15 && expected_population > 15) continue;
                if (remaining > 15 && remaining <= 35 && expected_population > 35) continue;
                if (remaining > 35 && expected_population > remaining + 25) continue;

                local population_at_site = GSTown.GetPopulation(town_id);
                if (!GSTown.PlaceHouse(tile, house_id)) {
                    this.density_house_fail++;
                    continue;
                }

                local population_after_site = GSTown.GetPopulation(town_id);
                if (population_after_site <= population_at_site) {
                    GSLog.Error(
                        "Coimbra 008 placed OSM house without source-town population gain: " +
                        town_name + " osm_id=" + osm_id
                    );
                    return false;
                }

                placed++;
                this.density_house_ok++;
                if (house_class == 2) {
                    medium_rise++;
                } else if (house_class == 3) {
                    civic++;
                } else {
                    low_rise++;
                }

                if (placed % 12 == 0) this.Sleep(1);
            }

            local population_after = GSTown.GetPopulation(town_id);
            local source_mix = source_low_rise + source_medium_rise;
            local placed_mix = low_rise + medium_rise;
            local mix_delta_pp = 0;
            if (source_mix > 0 && placed_mix > 0) {
                local mix_delta = low_rise * source_mix - source_low_rise * placed_mix;
                if (mix_delta < 0) mix_delta = -mix_delta;
                mix_delta_pp = mix_delta * 100 / (source_mix * placed_mix);
            }

            GSLog.Info(
                "Coimbra 008 OSM fabric: " + town_name +
                " placed=" + placed +
                " low_rise=" + low_rise +
                " medium_rise=" + medium_rise +
                " civic=" + civic +
                " source_low_rise=" + source_low_rise +
                " source_medium_rise=" + source_medium_rise +
                " source_civic=" + source_civic +
                " mix_delta_pp=" + mix_delta_pp +
                " sites_checked=" + source_sites_checked +
                " blocked=" + blocked +
                " wrong_town=" + wrong_town +
                " population_before=" + population_before +
                " target=" + target_population +
                " population_after=" + population_after
            );

            if (wrong_town != 0) {
                GSLog.Error("Coimbra 008 nearest-town assignment mismatch: " + town_name);
                return false;
            }
            if (placed <= 0 || placed_mix <= 0) {
                GSLog.Error("Coimbra 008 OSM urban fabric produced no residential mix: " + town_name);
                return false;
            }
            if (source_low_rise * 10 >= source_mix && low_rise == 0) {
                GSLog.Error("Coimbra 008 OSM low-rise class disappeared from placed mix: " + town_name);
                return false;
            }
            if (source_medium_rise * 10 >= source_mix && medium_rise == 0) {
                GSLog.Error("Coimbra 008 OSM medium-rise class disappeared from placed mix: " + town_name);
                return false;
            }
            if (mix_delta_pp > 35) {
                GSLog.Error(
                    "Coimbra 008 OSM placed mix diverges from source footprints: " +
                    town_name + " delta_pp=" + mix_delta_pp
                );
                return false;
            }
            if (population_after < target_population || population_after > target_population + 120) {
                GSLog.Error(
                    "Coimbra 008 population outside target band: " + town_name +
                    " target=" + target_population +
                    " actual=" + population_after
                );
                return false;
            }
            GSTown.SetGrowthRate(town_id, GSTown.TOWN_GROWTH_NONE);
        }

        local after = this.RoadFingerprint();
        GSLog.Info(
            "Coimbra 008 road fingerprint after count=" + after[0] +
            " checksum=" + after[1]
        );
        GSLog.Info(
            "Coimbra 008 houses placed=" + this.density_house_ok +
            " failed_attempts=" + this.density_house_fail
        );

        if (before[0] != after[0] || before[1] != after[1]) {
            GSLog.Error(
                "Coimbra 008 road fingerprint changed before=" + before[0] + "/" + before[1] +
                " after=" + after[0] + "/" + after[1]
            );
            return false;
        }

        ::COIMBRA_BUILDING_SITES = null;
        GSLog.Info("Coimbra 008 road fingerprint preserved.");
        return true;
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

    completed_marker = r'''        if (this.completed) {
            GSLog.Info("Coimbra completed save loaded; network rebuild skipped.");
            while (true) this.Sleep(740);
        }

'''
    upgrade_block = r'''        if (this.density_upgrade) {
            GSLog.Info("Coimbra 008 OSM-footprint urban fabric upgrade from verified 005 save started.");
            if (!this.AttachExistingTowns()) return;
            if (!this.PlaceOsmFootprintFabricLocked()) return;
            this.ValidateTowns();
            if (this.town_fail != 0) {
                GSLog.Error("Coimbra 008 source town validation failed.");
                return;
            }
            this.density_upgrade = false;
            this.completed = true;
            GSLog.Info("Coimbra 008 OSM-footprint urban fabric upgrade complete.");
            while (true) this.Sleep(740);
        }

        if (this.completed) {
            GSLog.Info("Coimbra completed save loaded; network rebuild skipped.");
            while (true) this.Sleep(740);
        }

'''
    if completed_marker not in main:
        raise RuntimeError("could not locate completed-save guard")
    main = main.replace(completed_marker, upgrade_block, 1)

    road_marker = '        GSRoad.SetCurrentRoadType(GSRoad.ROADTYPE_ROAD);\n'
    if road_marker not in main:
        raise RuntimeError("could not locate road initialization in generated GameScript")
    main = main.replace(
        road_marker,
        '        // 008: preserve the accepted 005 OSM-first transport build.\n'
        '        GSRoad.SetCurrentRoadType(GSRoad.ROADTYPE_ROAD);\n',
        1,
    )

    completion_marker = (
        '        this.completed = true;\n'
        '        GSLog.Info("Coimbra network build complete.");\n'
    )
    if completion_marker not in main:
        raise RuntimeError("could not locate unique network completion marker")
    main = main.replace(
        completion_marker,
        '        // 008 fresh-map fallback; migration of verified 005 uses the one-shot block above.\n'
        '        this.FoundTowns();\n'
        '        if (!this.PlaceOsmFootprintFabricLocked()) return;\n'
        '        this.ValidateTowns();\n'
        '        this.completed = true;\n'
        '        GSLog.Info("Coimbra network build complete.");\n',
        1,
    )

    info = info_path.read_text(encoding="utf-8")
    info = info.replace(
        'function GetDescription() { return "Builds the quantized real Coimbra road, bridge and tunnel network."; }',
        'function GetDescription() { return "Places population-targeted OpenTTD houses on pinned real Coimbra OSM building-footprint centroids while preserving the locked 005 roads."; }',
        1,
    )
    info = info.replace("function GetVersion() { return 2; }", "function GetVersion() { return 13; }", 1)
    info_path.write_text(info, encoding="utf-8")

    load_marker = r'''    function Load(version, data) {
        if ("completed" in data) this.completed = data.completed;
    }
'''
    load_upgrade = r'''    function Load(version, data) {
        if ("completed" in data) this.completed = data.completed;
        if (version < 13 && this.completed) {
            this.completed = false;
            this.density_upgrade = true;
        }
    }
'''
    if load_marker not in main:
        raise RuntimeError("could not locate GameScript Load()")
    main = main.replace(load_marker, load_upgrade, 1)
    main_path.write_text(main, encoding="utf-8")


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
    print(json.dumps({
        "town_count": len(plan),
        "towns": plan,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
