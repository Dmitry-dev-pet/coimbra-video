from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "bridge_output_008c" / "coimbra-highres-terrain-visual-dev.blend"
OSM_LOCAL = ROOT / "data" / "processed" / "bridge_osm_oss_local.json"
TERRAIN = ROOT / "bridge_output_008b" / "bridge_terrain_highres_2m.npz"
OUT = ROOT / "bridge_output_009a"
OUT_BLEND = OUT / "coimbra-mosaiq-benchmark.blend"
MANIFEST = OUT / "mosaiq-benchmark-manifest.json"

MOSAIQ_PARENT = ROOT / "_mosaiq"
if str(MOSAIQ_PARENT) not in sys.path:
    sys.path.insert(0, str(MOSAIQ_PARENT))

import mosaiq_osm_vr  # type: ignore
from mosaiq_osm_vr.src import addon_core as mos_core  # type: ignore


class TerrainSampler:
    def __init__(self, path: Path):
        data = np.load(path)
        self.z = data["z"].astype(np.float32)
        self.xs = data["xs"].astype(np.float32)
        self.ys = data["ys"].astype(np.float32)
        self.z0 = float(data["z0"])

    def sample(self, x: float, y: float) -> float | None:
        if x < float(self.xs[0]) or x > float(self.xs[-1]):
            return None
        if y > float(self.ys[0]) or y < float(self.ys[-1]):
            return None
        fx = (x - float(self.xs[0])) / (float(self.xs[-1]) - float(self.xs[0])) * (len(self.xs) - 1)
        fy = (float(self.ys[0]) - y) / (float(self.ys[0]) - float(self.ys[-1])) * (len(self.ys) - 1)
        x0 = int(np.floor(fx)); y0 = int(np.floor(fy))
        x1 = min(x0 + 1, len(self.xs) - 1)
        y1 = min(y0 + 1, len(self.ys) - 1)
        tx = fx - x0; ty = fy - y0
        a = float(self.z[y0, x0]); b = float(self.z[y0, x1])
        c = float(self.z[y1, x0]); d = float(self.z[y1, x1])
        value = (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty
        return value - self.z0


def line_for_way(way: dict, nodes: dict[str, dict]) -> list[tuple[float, float]]:
    line = []
    for node_id in way.get("nodes") or []:
        node = nodes.get(str(node_id))
        if node:
            x, y = node["xy"]
            line.append((float(x), float(y)))
    return line


def drape_object(obj: bpy.types.Object, terrain: TerrainSampler) -> tuple[int, int]:
    shifted = 0
    skipped = 0
    for vertex in obj.data.vertices:
        z = terrain.sample(float(vertex.co.x), float(vertex.co.y))
        if z is None:
            skipped += 1
            continue
        vertex.co.z += z
        shifted += 1
    obj.data.update()
    return shifted, skipped


def link_object(obj, collection):
    if obj is None:
        return
    if obj.name not in collection.objects:
        collection.objects.link(obj)


def nearest_road_tangent(node_id: int, ways: list[dict], nodes: dict[str, dict]):
    target = nodes.get(str(node_id))
    if target is None:
        return None
    tx, ty = target["xy"]
    best = None
    best_dist = float("inf")
    for way in ways:
        tags = way.get("tags") or {}
        if "highway" not in tags:
            continue
        ids = way.get("nodes") or []
        if node_id not in ids:
            continue
        idx = ids.index(node_id)
        neighbors = []
        if idx > 0:
            neighbors.append(ids[idx - 1])
        if idx + 1 < len(ids):
            neighbors.append(ids[idx + 1])
        for neighbor_id in neighbors:
            neighbor = nodes.get(str(neighbor_id))
            if neighbor is None:
                continue
            nx, ny = neighbor["xy"]
            dx = float(nx) - float(tx)
            dy = float(ny) - float(ty)
            dist = math.hypot(dx, dy)
            if dist > 1e-6 and dist < best_dist:
                best_dist = dist
                best = ((dx / dist, dy / dist), mos_core.highway_width_m(tags), way["id"])
    return best


def join_objects(objects: list[bpy.types.Object], name: str):
    objects = [obj for obj in objects if obj and obj.name in bpy.data.objects]
    if not objects:
        return None
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    result = objects[0]
    result.name = name
    result.data.name = name + "_Mesh"
    return result


def render_preview(scene, frame: int, path: Path):
    scene.frame_set(frame)
    scene.render.filepath = str(path)
    scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)


def main() -> None:
    for required in (BASE, OSM_LOCAL, TERRAIN):
        if not required.is_file():
            raise SystemExit(f"Missing input: {required}")

    bpy.ops.wm.open_mainfile(filepath=str(BASE))
    data = json.loads(OSM_LOCAL.read_text())
    nodes = data["nodes"]
    ways = data["ways"]
    terrain = TerrainSampler(TERRAIN)

    collection = bpy.data.collections.new("OSS_MOSAIQ")
    bpy.context.scene.collection.children.link(collection)

    sidewalk_objects = []
    parking_objects = []
    crosswalk_objects = []
    stats = {
        "roads_considered": 0,
        "sidewalk_strips": 0,
        "parking_strips": 0,
        "crosswalks": 0,
        "drape_vertices": 0,
        "drape_skipped": 0,
    }

    sidewalk_mat = mos_core.ensure_sidewalk_slab_material()
    parking_mat = mos_core.ensure_parking_material()
    crosswalk_mat = mos_core.ensure_crosswalk_material()

    for way in ways:
        tags = way.get("tags") or {}
        if "highway" not in tags:
            continue
        line = line_for_way(way, nodes)
        if len(line) < 2:
            continue
        stats["roads_considered"] += 1
        road_width = mos_core.highway_width_m(tags)

        parking = mos_core.parse_parking_lanes(tags)
        sidewalks = mos_core.parse_sidewalks(tags)

        for side in sidewalks:
            sign = 1.0 if side == "left" else -1.0
            parking_width = float((parking.get(side) or {}).get("width", 0.0))
            width = 2.8
            offset = sign * (road_width * 0.5 + parking_width + 0.2 + width * 0.5)
            obj = mos_core.create_offset_strip(
                f"mos_sidewalk_{way['id']}_{side}",
                line,
                width_m=width,
                offset_m=offset,
                z=0.04,
                mat=sidewalk_mat,
            )
            if obj:
                link_object(obj, collection)
                sidewalk_objects.append(obj)
                stats["sidewalk_strips"] += 1

        for side, spec in parking.items():
            sign = 1.0 if side == "left" else -1.0
            width = float(spec.get("width", 2.4))
            offset = sign * (road_width * 0.5 + width * 0.5 + 0.08)
            obj = mos_core.create_offset_strip(
                f"mos_parking_{way['id']}_{side}",
                line,
                width_m=width,
                offset_m=offset,
                z=0.035,
                mat=parking_mat,
            )
            if obj:
                link_object(obj, collection)
                parking_objects.append(obj)
                stats["parking_strips"] += 1

    for node_id_str, node in nodes.items():
        tags = node.get("tags") or {}
        if (tags.get("highway") or "").lower() != "crossing" and not tags.get("crossing"):
            continue
        node_id = int(node_id_str)
        match = nearest_road_tangent(node_id, ways, nodes)
        if match is None:
            continue
        tangent, road_width, way_id = match
        center = tuple(float(v) for v in node["xy"])
        obj = mos_core.create_crosswalk_mesh(
            f"mos_crosswalk_{node_id}",
            center,
            tangent,
            road_width,
            z=0.055,
            mat=crosswalk_mat,
        )
        if obj:
            link_object(obj, collection)
            crosswalk_objects.append(obj)
            stats["crosswalks"] += 1

    all_objects = sidewalk_objects + parking_objects + crosswalk_objects
    for obj in all_objects:
        shifted, skipped = drape_object(obj, terrain)
        stats["drape_vertices"] += shifted
        stats["drape_skipped"] += skipped

    joined = {
        "sidewalks": join_objects(sidewalk_objects, "OSS_MOSAIQ_Sidewalks"),
        "parking": join_objects(parking_objects, "OSS_MOSAIQ_Parking"),
        "crosswalks": join_objects(crosswalk_objects, "OSS_MOSAIQ_Crosswalks"),
    }

    for kind, obj in joined.items():
        if obj:
            obj["source"] = "MOSAIQ OpenStreetMap to Blender Add-On"
            obj["upstream_commit"] = "f73d030aecd3289007472a887d78aae2e74b6ea0"
            obj["license"] = "Apache-2.0"
            obj["benchmark_layer"] = kind

    scene = bpy.context.scene
    scene["oss_mosaiq_commit"] = "f73d030aecd3289007472a887d78aae2e74b6ea0"
    scene["oss_mosaiq_license"] = "Apache-2.0"
    scene["oss_mosaiq_benchmark"] = True

    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))

    for frame in (1, 181, 360):
        render_preview(scene, frame, OUT / f"preview-{frame:03d}.png")

    manifest = {
        "upstream": {
            "repository": "TUMFTM/MOSAIQ-OpenStreetMap-to-Blender-Add-On",
            "commit": "f73d030aecd3289007472a887d78aae2e74b6ea0",
            "license": "Apache-2.0",
        },
        "base_scene": BASE.relative_to(ROOT).as_posix(),
        "output_scene": OUT_BLEND.relative_to(ROOT).as_posix(),
        "stats": stats,
        "objects": {key: (obj.name if obj else None) for key, obj in joined.items()},
        "note": "Benchmark layer only; MOSAIQ vehicles are intentionally disabled in favor of ortho-detected cars.",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
