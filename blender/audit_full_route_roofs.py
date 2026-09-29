from __future__ import annotations

import colorsys
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import bpy
from statistics import median
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.kdtree import KDTree


ROOT = Path(__file__).resolve().parents[1]
BLENDER_DIR = ROOT / "blender"
if str(BLENDER_DIR) not in sys.path:
    sys.path.insert(0, str(BLENDER_DIR))

import enhance_hero_buildings as hero  # type: ignore


SOURCE = ROOT / "bridge_output_016b" / "coimbra-full-render-new-geometry.blend"
OSM_LOCAL = ROOT / "data" / "processed" / "bridge_osm_oss_local.json"
OUT = ROOT / "bridge_output_018"
OUT_BLEND = OUT / "coimbra-full-route-roof-audit.blend"
MANIFEST = OUT / "roof-audit-manifest.json"

CORRIDOR_RADIUS_M = 550.0
GRID_M = 80.0
NEAR_FLAT_Z = 0.985


def material(name, color, roughness=0.82, metallic=0.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = color
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
    return mat


def ensure_material_slot(obj, mat):
    for index, existing in enumerate(obj.data.materials):
        if existing == mat:
            return index
    obj.data.materials.append(mat)
    return len(obj.data.materials) - 1


def camera_signature(scene, camera):
    original = scene.frame_current
    rows = []
    for frame in (1, 61, 121, 181, 241, 301, 360):
        scene.frame_set(frame)
        rows.append(
            {
                "frame": frame,
                "location": [round(float(v), 6) for v in camera.location],
                "rotation": [round(float(v), 7) for v in camera.rotation_euler],
                "lens": round(float(camera.data.lens), 6),
            }
        )
    scene.frame_set(original)
    return rows


def build_camera_kdtree(scene, camera):
    original = scene.frame_current
    points = []
    for frame in range(1, 361):
        scene.frame_set(frame)
        points.append((float(camera.location.x), float(camera.location.y), frame))
    scene.frame_set(original)

    tree = KDTree(len(points))
    for index, (x, y, _frame) in enumerate(points):
        tree.insert((x, y, 0.0), index)
    tree.balance()
    return tree, points


def footprint_for_way(way, nodes):
    return hero.footprint_for_way(way, nodes)


def classify_tags(tags, footprint):
    raw_shape = str(tags.get("roof:shape") or "").lower()
    flat_shapes = {"flat"}
    pitched_shapes = {
        "gabled", "gable", "hipped", "hip", "skillion", "shed",
        "pyramidal", "mansard", "gambrel", "round", "dome", "onion",
        "saltbox", "half-hipped",
    }
    if raw_shape in flat_shapes:
        return "flat", "osm-roof-shape"
    if raw_shape in pitched_shapes:
        return "pitched", "osm-roof-shape"

    roof_material = str(tags.get("roof:material") or "").lower()
    if any(token in roof_material for token in ("tile", "clay", "ceramic")):
        return "pitched", "osm-roof-material"
    if any(token in roof_material for token in ("metal", "sheet", "steel")):
        return "pitched-metal", "osm-roof-material"

    kind = str(tags.get("building") or "").lower()
    strong_flat = {
        "industrial", "warehouse", "commercial", "retail", "office",
        "school", "university", "hospital", "civic", "public",
        "supermarket", "sports_hall",
    }
    strong_pitched = {
        "house", "detached", "semidetached_house", "terrace",
        "bungalow", "farm", "farm_auxiliary", "chapel", "church",
    }
    if kind in strong_flat:
        return "flat", "building-type"
    if kind in strong_pitched:
        return "pitched", "building-type"

    area = hero.polygon_area(footprint)
    if area >= 500.0:
        return "flat", "large-footprint"
    return "unknown", "ortho-color"


def grid_key(x, y):
    return (int(math.floor(x / GRID_M)), int(math.floor(y / GRID_M)))


def build_building_index(source):
    grid = defaultdict(list)
    records = []
    for way in source["ways"]:
        tags = way.get("tags") or {}
        if "building" not in tags:
            continue
        footprint = footprint_for_way(way, source["nodes"])
        if not footprint:
            continue

        xs = [p[0] for p in footprint]
        ys = [p[1] for p in footprint]
        bbox = (min(xs), min(ys), max(xs), max(ys))
        classification, class_source = classify_tags(tags, footprint)
        record = {
            "way_id": int(way["id"]),
            "tags": tags,
            "footprint": footprint,
            "bbox": bbox,
            "class": classification,
            "class_source": class_source,
            "area": hero.polygon_area(footprint),
        }
        records.append(record)

        gx0, gy0 = grid_key(bbox[0], bbox[1])
        gx1, gy1 = grid_key(bbox[2], bbox[3])
        for gx in range(gx0, gx1 + 1):
            for gy in range(gy0, gy1 + 1):
                grid[(gx, gy)].append(record)
    return grid, records


def match_building(x, y, grid):
    candidates = grid.get(grid_key(x, y), [])
    matches = []
    for record in candidates:
        minx, miny, maxx, maxy = record["bbox"]
        if not (minx - 0.25 <= x <= maxx + 0.25 and miny - 0.25 <= y <= maxy + 0.25):
            continue
        if hero.point_in_polygon(x, y, record["footprint"]):
            matches.append(record)
    if not matches:
        return None
    matches.sort(key=lambda r: r["area"])
    return matches[0]


class OrthoSampler:
    def __init__(self):
        terrain = bpy.data.objects.get("City_Terrain")
        if terrain is None or terrain.type != "MESH":
            raise RuntimeError("City_Terrain missing; cannot locate packed DGT ortho")

        image = None
        for mat in terrain.data.materials:
            if mat is None or not mat.use_nodes or mat.node_tree is None:
                continue
            for node in mat.node_tree.nodes:
                if node.type == "TEX_IMAGE" and node.image is not None:
                    image = node.image
                    break
            if image is not None:
                break

        if image is None:
            raise RuntimeError("Packed DGT orthophoto image node not found")

        if not image.has_data and len(image.packed_files) > 0:
            extracted = OUT / "packed-dgt-ortho.jpg"
            extracted.parent.mkdir(parents=True, exist_ok=True)
            packed_entry = image.packed_files[0]
            raw = bytes(packed_entry.packed_file.data)
            if not raw:
                raise RuntimeError("Embedded DGT orthophoto payload is empty")
            print(json.dumps({
                "packed_image_name": image.name,
                "packed_image_filepath": image.filepath,
                "packed_bytes": len(raw),
                "packed_magic_hex": raw[:16].hex(),
            }))
            extracted.write_bytes(raw)

            # Do not reload the original datablock: its packed/original-path
            # bookkeeping can keep pointing at the missing source path.
            image = bpy.data.images.load(str(extracted), check_existing=False)

        if not image.has_data:
            raise RuntimeError(
                "Extracted DGT orthophoto could not be loaded as a new image datablock"
            )

        self.image = image
        self.width = int(image.size[0])
        self.height = int(image.size[1])
        if self.width <= 0 or self.height <= 0:
            raise RuntimeError("Invalid packed DGT orthophoto dimensions")

        world_corners = [
            terrain.matrix_world @ Vector(corner)
            for corner in terrain.bound_box
        ]
        self.minx = min(float(p.x) for p in world_corners)
        self.maxx = max(float(p.x) for p in world_corners)
        self.miny = min(float(p.y) for p in world_corners)
        self.maxy = max(float(p.y) for p in world_corners)
        self.pixels = image.pixels

    def pixel(self, x_local, y_local):
        if not (self.minx <= x_local <= self.maxx and self.miny <= y_local <= self.maxy):
            return None
        u = (x_local - self.minx) / max(1e-9, self.maxx - self.minx)
        v = (y_local - self.miny) / max(1e-9, self.maxy - self.miny)
        return (
            u * (self.width - 1),
            v * (self.height - 1),
        )

    def rgb_at(self, x, y):
        x = max(0, min(int(x), self.width - 1))
        y = max(0, min(int(y), self.height - 1))
        index = (y * self.width + x) * 4
        return (
            float(self.pixels[index]) * 255.0,
            float(self.pixels[index + 1]) * 255.0,
            float(self.pixels[index + 2]) * 255.0,
        )

    def median_rgb(self, x_local, y_local, radius_px=8):
        point = self.pixel(x_local, y_local)
        if point is None:
            return None
        px, py = point
        # 25 samples across roughly a 4 m square at the original 25 cm DGT
        # resolution. Sparse sampling avoids materializing the full packed
        # ~65M-pixel image as a Python array.
        offsets = (-radius_px, -radius_px // 2, 0, radius_px // 2, radius_px)
        rs, gs, bs = [], [], []
        for dx in offsets:
            for dy in offsets:
                r, g, b = self.rgb_at(round(px + dx), round(py + dy))
                rs.append(r)
                gs.append(g)
                bs.append(b)
        return (median(rs), median(gs), median(bs))


def ortho_roof_signal(rgb):
    if rgb is None:
        return {"tile_like": False, "bucket": "gray", "rgb": None}
    r, g, b = rgb
    # Ignore almost-black deep shadows when deciding tile vs flat.
    value = max(r, g, b)
    tile_like = (
        value > 65
        and r > g * 1.10
        and r > b * 1.16
        and (r - g) > 10
    )

    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    if luminance >= 175:
        bucket = "light"
    elif luminance <= 85:
        bucket = "dark"
    elif r - g > 16 and r > b * 1.08:
        bucket = "warm"
    else:
        bucket = "gray"

    return {
        "tile_like": bool(tile_like),
        "bucket": bucket,
        "rgb": [round(r, 1), round(g, 1), round(b, 1)],
        "luminance": round(luminance, 1),
    }


def choose_final_class(record, signal):
    classification = record["class"]
    if classification == "unknown":
        return ("pitched" if signal["tile_like"] else "flat"), "ortho-color"
    if classification == "pitched" and not signal["tile_like"]:
        roof_material = str(record["tags"].get("roof:material") or "").lower()
        if "tile" not in roof_material and record["class_source"] != "osm-roof-shape":
            # Non-red aerial color is weak evidence against tile, but only
            # override heuristic (not explicit roof:shape) pitched classes.
            return "pitched-metal", "ortho-color"
    return classification, record["class_source"]


def select_tile_slot(obj, bright):
    preferred = "City_Roof_01" if bright else "City_Roof_00"
    for index, mat in enumerate(obj.data.materials):
        if mat and mat.name == preferred:
            return index
    for index, mat in enumerate(obj.data.materials):
        if mat and mat.name.startswith("City_Roof_"):
            return index
    raise RuntimeError("No City_Roof_* material slot found")


def select_review_frames(scene, camera, corrected_centers):
    if not corrected_centers:
        return [1, 90, 180, 270, 360]

    original = scene.frame_current
    scores = []
    stride = max(1, len(corrected_centers) // 350)
    sampled = corrected_centers[::stride]

    for frame in range(1, 361, 5):
        scene.frame_set(frame)
        visible = 0
        weighted = 0.0
        for center in sampled:
            co = world_to_camera_view(scene, camera, Vector(center))
            if co.z <= 0.0:
                continue
            if -0.05 <= co.x <= 1.05 and -0.05 <= co.y <= 1.05:
                visible += 1
                dx = co.x - 0.5
                dy = co.y - 0.5
                weighted += 1.0 / (0.35 + math.hypot(dx, dy))
        scores.append((weighted + visible * 0.15, frame))

    scene.frame_set(original)
    scores.sort(reverse=True)

    chosen = []
    for _score, frame in scores:
        if all(abs(frame - existing) >= 45 for existing in chosen):
            chosen.append(frame)
        if len(chosen) == 5:
            break

    if len(chosen) < 5:
        for frame in (1, 90, 180, 270, 360):
            if all(abs(frame - existing) >= 30 for existing in chosen):
                chosen.append(frame)
            if len(chosen) == 5:
                break
    return sorted(chosen[:5])


def main():
    for required in (SOURCE, OSM_LOCAL):
        if not required.is_file():
            raise SystemExit(f"Missing input: {required}")

    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    scene = bpy.context.scene
    camera = scene.camera
    if camera is None:
        raise RuntimeError("production camera missing")

    camera_before = camera_signature(scene, camera)
    camera_tree, camera_points = build_camera_kdtree(scene, camera)

    source = json.loads(OSM_LOCAL.read_text())
    grid, buildings = build_building_index(source)
    ortho = OrthoSampler()

    city = bpy.data.objects.get("City_Buildings")
    if city is None or city.type != "MESH":
        raise RuntimeError("City_Buildings missing")

    flat_materials = {
        "light": material("Route_Flat_Light", (0.52, 0.50, 0.46, 1.0), 0.92),
        "gray": material("Route_Flat_Gray", (0.30, 0.31, 0.31, 1.0), 0.90),
        "dark": material("Route_Flat_Dark", (0.13, 0.14, 0.14, 1.0), 0.88),
        "warm": material("Route_Flat_Warm", (0.40, 0.34, 0.28, 1.0), 0.91),
    }
    flat_slots = {
        name: ensure_material_slot(city, mat)
        for name, mat in flat_materials.items()
    }
    metal_slot = ensure_material_slot(
        city,
        material("Route_Pitched_Metal", (0.24, 0.27, 0.29, 1.0), 0.58, 0.22),
    )

    matrix = city.matrix_world.copy()
    normal_matrix = matrix.to_3x3().inverted().transposed()

    stats = defaultdict(int)
    sources = defaultdict(int)
    buckets = defaultdict(int)
    corrected_centers = []
    examples = []

    for polygon in city.data.polygons:
        mat = city.data.materials[polygon.material_index]
        if mat is None or not mat.name.startswith("City_Roof_"):
            continue

        world_normal = normal_matrix @ polygon.normal
        if float(world_normal.z) < NEAR_FLAT_Z:
            stats["non_horizontal_tile_faces_untouched"] += 1
            continue

        center_world = matrix @ polygon.center
        _co, _idx, corridor_distance = camera_tree.find(
            (float(center_world.x), float(center_world.y), 0.0)
        )
        if corridor_distance > CORRIDOR_RADIUS_M:
            stats["outside_corridor"] += 1
            continue

        stats["corridor_roof_faces"] += 1
        record = match_building(float(center_world.x), float(center_world.y), grid)
        if record is None:
            stats["unmatched"] += 1
            continue

        stats["matched"] += 1
        signal = ortho_roof_signal(
            ortho.median_rgb(float(center_world.x), float(center_world.y))
        )
        if signal["rgb"] is not None:
            stats["ortho_sampled"] += 1

        final_class, final_source = choose_final_class(record, signal)
        sources[final_source] += 1

        old_name = mat.name
        new_slot = polygon.material_index
        new_class = final_class

        if final_class == "flat":
            bucket = signal["bucket"]
            new_slot = flat_slots[bucket]
            buckets[bucket] += 1
            stats["flat_non_tile"] += 1
        elif final_class == "pitched-metal":
            new_slot = metal_slot
            stats["pitched_non_tile"] += 1
        else:
            bright = (signal.get("luminance") or 0) >= 125
            new_slot = select_tile_slot(city, bright)
            stats["pitched_tile"] += 1

        new_name = city.data.materials[new_slot].name
        if new_slot != polygon.material_index:
            polygon.material_index = new_slot
            stats["faces_changed"] += 1

        if old_name.startswith("City_Roof_") and not new_name.startswith("City_Roof_"):
            stats["tile_removed"] += 1
            corrected_centers.append(tuple(center_world))

        if len(examples) < 40 and (new_name != old_name or final_class != "pitched"):
            examples.append(
                {
                    "way_id": record["way_id"],
                    "building": record["tags"].get("building"),
                    "roof_shape": record["tags"].get("roof:shape"),
                    "classification": final_class,
                    "source": final_source,
                    "ortho": signal,
                    "old_material": old_name,
                    "new_material": new_name,
                    "corridor_distance_m": round(float(corridor_distance), 1),
                }
            )

    city.data.update()

    if stats["matched"] < 50:
        raise RuntimeError(f"Too few route roofs matched to OSM: {dict(stats)}")
    if stats["tile_removed"] < 20:
        raise RuntimeError(f"Roof cleanup changed too few tile faces: {dict(stats)}")

    camera_after = camera_signature(scene, camera)
    if camera_after != camera_before:
        raise RuntimeError("production camera changed during roof audit")

    review_frames = select_review_frames(scene, camera, corrected_centers)

    scene["route_roof_audit_version"] = "coimbra-route-roof-audit-v1"
    scene["route_roof_tile_removed"] = int(stats["tile_removed"])
    scene["route_roof_faces_matched"] = int(stats["matched"])

    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))

    result = {
        "version": "coimbra-route-roof-audit-v1",
        "source_scene": SOURCE.relative_to(ROOT).as_posix(),
        "output_scene": OUT_BLEND.relative_to(ROOT).as_posix(),
        "corridor_radius_m": CORRIDOR_RADIUS_M,
        "horizontal_threshold_normal_z": NEAR_FLAT_Z,
        "buildings_indexed": len(buildings),
        "stats": dict(stats),
        "classification_sources": dict(sources),
        "flat_color_buckets": dict(buckets),
        "review_frames": review_frames,
        "camera_unchanged": camera_before == camera_after,
        "examples": examples,
        "rules": {
            "explicit_roof_shape_wins": True,
            "flat_roof_never_tile": True,
            "unknown_uses_dgt_ortho_color": True,
            "dgt_ortho_from_packed_scene": True,
            "google_not_bulk_scraped": True,
            "full_route_scene": True,
        },
    }
    MANIFEST.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
