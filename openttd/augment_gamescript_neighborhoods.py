#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def squirrel_array(items: list[list]) -> str:
    return "[\n" + ",\n".join(
        "  " + json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        for item in items
    ) + "\n]"


def load_anchors(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or len(raw) != 5:
        raise ValueError(f"expected exactly five Coimbra neighborhood anchors, got {len(raw) if isinstance(raw, list) else type(raw)}")
    anchors = []
    seen = set()
    for item in raw:
        name = str(item["name"])
        x = int(item["x"])
        y = int(item["y"])
        source = str(item.get("source", ""))
        if name in seen:
            raise ValueError(f"duplicate neighborhood anchor: {name}")
        if not (1 <= x <= 510 and 1 <= y <= 510):
            raise ValueError(f"anchor outside 512x512 map: {name} {x},{y}")
        seen.add(name)
        anchors.append({"name": name, "x": x, "y": y, "source": source})
    return anchors


def augment_game(game_dir: Path, anchors: list[dict]) -> None:
    main_path = game_dir / "main.nut"
    info_path = game_dir / "info.nut"
    if not main_path.exists() or not info_path.exists():
        raise FileNotFoundError("expected CoimbraBuilder main.nut and info.nut from verified 007")

    payload = [[a["x"], a["y"], a["name"], a["source"]] for a in anchors]
    (game_dir / "neighborhoods.nut").write_text(
        "::COIMBRA_NEIGHBORHOODS <- %s;\n" % squirrel_array(payload),
        encoding="utf-8",
    )

    main = main_path.read_text(encoding="utf-8")
    if "neighborhood_upgrade = false;" in main:
        raise RuntimeError("GameScript already contains the 008 neighborhood layer")

    field_marker = "    density_house_fail = 0;\n"
    if field_marker not in main:
        raise RuntimeError("expected verified 007 density fields")
    main = main.replace(
        field_marker,
        field_marker
        + "    neighborhood_upgrade = false;\n"
        + "    neighborhood_house_ok = 0;\n"
        + "    neighborhood_house_fail = 0;\n",
        1,
    )

    methods = r'''
    function TryPlaceNeighborhoodHouse(tile, ordinal) {
        // 008 is deliberately low-rise: fill real secondary neighborhoods without
        // recreating the apartment-wall problem rejected during 006/007.
        local palette = [0x1A, 0x18, 0x19, 0x06, 0x1A, 0x18];
        local start = ordinal % palette.len();
        for (local j = 0; j < palette.len(); j++) {
            local house_id = palette[(start + j) % palette.len()];
            if (GSTown.PlaceHouse(tile, house_id)) return house_id;
        }
        return -1;
    }

    function PlaceNeighborhoodFabricLocked() {
        require("neighborhoods.nut");
        local before = this.RoadFingerprint();
        local accepted = 0;
        local total_placed = 0;
        GSLog.Info(
            "Coimbra 008 road fingerprint before count=" + before[0] +
            " checksum=" + before[1]
        );

        foreach (i, item in COIMBRA_NEIGHBORHOODS) {
            local base_x = item[0];
            local base_y = item[1];
            local name = item[2];
            local placed = 0;
            local failed = 0;
            local ordinal = 0;

            for (local radius = 0; radius <= 24 && placed < 24; radius++) {
                for (local dx = -radius; dx <= radius && placed < 24; dx++) {
                    for (local dy = -radius; dy <= radius && placed < 24; dy++) {
                        if (radius > 0 && dx != -radius && dx != radius && dy != -radius && dy != radius) continue;

                        local x = base_x + dx;
                        local y = base_y + dy;
                        if (x <= 0 || y <= 0 || x >= GSMap.GetMapSizeX() - 1 || y >= GSMap.GetMapSizeY() - 1) continue;

                        // Preserve visible gaps and avoid replacing forest with a solid wall.
                        if (((x * 5 + y * 7 + i * 11) % 4) == 0) continue;

                        local tile = GSMap.GetTileIndex(x, y);
                        if (!GSMap.IsValidTile(tile) || !GSTile.IsBuildable(tile)) continue;
                        if (!this.HasAdjacentRoad(x, y)) continue;

                        local house_id = this.TryPlaceNeighborhoodHouse(tile, ordinal);
                        ordinal++;
                        if (house_id >= 0) {
                            placed++;
                            this.neighborhood_house_ok++;
                            total_placed++;
                            if (placed % 8 == 0) this.Sleep(1);
                        } else {
                            failed++;
                            this.neighborhood_house_fail++;
                        }
                    }
                }
            }

            GSLog.Info(
                "Coimbra 008 neighborhood: " + name +
                " anchor=" + base_x + "," + base_y +
                " placed=" + placed +
                " failed=" + failed
            );

            if (placed < 8) {
                GSLog.Error("Coimbra 008 neighborhood insufficient fabric: " + name);
                return false;
            }
            accepted++;
        }

        local after = this.RoadFingerprint();
        GSLog.Info(
            "Coimbra 008 road fingerprint after count=" + after[0] +
            " checksum=" + after[1]
        );
        GSLog.Info(
            "Coimbra 008 neighborhoods accepted=" + accepted +
            " houses_placed=" + total_placed +
            " failed_attempts=" + this.neighborhood_house_fail
        );

        if (accepted != COIMBRA_NEIGHBORHOODS.len() || total_placed < 40) {
            GSLog.Error("Coimbra 008 distributed fabric acceptance failed.");
            return false;
        }
        if (before[0] != after[0] || before[1] != after[1]) {
            GSLog.Error(
                "Coimbra 008 road fingerprint changed before=" + before[0] + "/" + before[1] +
                " after=" + after[0] + "/" + after[1]
            );
            return false;
        }

        GSLog.Info("Coimbra 008 road fingerprint preserved.");
        return true;
    }

'''
    method_marker = "    function ValidateTowns() {\n"
    if method_marker not in main:
        raise RuntimeError("could not locate verified 007 town-validation marker")
    main = main.replace(method_marker, methods + method_marker, 1)

    completed_marker = r'''        if (this.completed) {
            GSLog.Info("Coimbra completed save loaded; network rebuild skipped.");
            while (true) this.Sleep(740);
        }

'''
    neighborhood_upgrade = r'''        if (this.neighborhood_upgrade) {
            GSLog.Info("Coimbra 008 distributed urban fabric upgrade from verified 007 save started.");
            if (!this.PlaceNeighborhoodFabricLocked()) return;
            this.neighborhood_upgrade = false;
            this.completed = true;
            GSLog.Info("Coimbra 008 distributed urban fabric upgrade complete.");
            while (true) this.Sleep(740);
        }

        if (this.completed) {
            GSLog.Info("Coimbra completed save loaded; network rebuild skipped.");
            while (true) this.Sleep(740);
        }

'''
    if completed_marker not in main:
        raise RuntimeError("could not locate verified 007 completed-save guard")
    main = main.replace(completed_marker, neighborhood_upgrade, 1)

    load_marker = r'''    function Load(version, data) {
        if ("completed" in data) this.completed = data.completed;
        if (version < 12 && this.completed) {
            this.completed = false;
            this.density_upgrade = true;
        }
    }
'''
    load_upgrade = r'''    function Load(version, data) {
        if ("completed" in data) this.completed = data.completed;
        if (version < 12 && this.completed) {
            this.completed = false;
            this.density_upgrade = true;
        }
        if (version >= 12 && version < 13 && this.completed) {
            this.completed = false;
            this.neighborhood_upgrade = true;
        }
    }
'''
    if load_marker not in main:
        raise RuntimeError("could not locate verified 007 Load()")
    main = main.replace(load_marker, load_upgrade, 1)
    main_path.write_text(main, encoding="utf-8")

    info = info_path.read_text(encoding="utf-8")
    version_marker = "function GetVersion() { return 12; }"
    if version_marker not in info:
        raise RuntimeError("expected verified 007 GameScript version 12")
    info = info.replace(version_marker, "function GetVersion() { return 13; }", 1)
    info = info.replace(
        "Builds population-targeted mixed urban fabric beside the locked Coimbra 005 OSM roads using an editor-only API bridge.",
        "Extends verified Coimbra 007 with low-rise fabric at five OSM-sourced secondary neighborhood anchors while preserving the exact road fingerprint.",
        1,
    )
    info_path.write_text(info, encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--anchors", type=Path, required=True)
    p.add_argument("--game-dir", type=Path, required=True)
    p.add_argument("--out-plan", type=Path, required=True)
    args = p.parse_args()

    anchors = load_anchors(args.anchors)
    augment_game(args.game_dir, anchors)
    args.out_plan.parent.mkdir(parents=True, exist_ok=True)
    args.out_plan.write_text(json.dumps(anchors, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"anchor_count": len(anchors), "anchors": anchors}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
