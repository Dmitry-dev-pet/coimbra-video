from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
BLENDER_DIR = ROOT / "blender"
if str(BLENDER_DIR) not in sys.path:
    sys.path.insert(0, str(BLENDER_DIR))

import audit_full_route_roofs as audit  # type: ignore
import enhance_hero_buildings as hero  # type: ignore


SOURCE = ROOT / "bridge_output_018" / "coimbra-full-route-roof-audit.blend"
OSM_LOCAL = ROOT / "data" / "processed" / "bridge_osm_oss_local.json"
HAG = ROOT / "bridge_output_008b" / "bridge_height_above_ground_1m.npz"
OUT = ROOT / "bridge_output_019"
OUT_BLEND = OUT / "coimbra-full-route-pitched-roofs.blend"
MANIFEST = OUT / "pitched-roofs-manifest.json"

CORRIDOR_RADIUS_M = 550.0
NEAR_FLAT_Z = 0.985
MIN_HAG_PITCH_SPREAD_M = 0.70
MAX_SAFE_VERTICES = 8


class HAGSampler:
    def __init__(self, path: Path):
        data = np.load(path)
        self.height = data["height"].astype(np.float32)
        self.xs = data["xs"].astype(np.float32)
        self.ys = data["ys"].astype(np.float32)

    def stats_for_polygon(self, polygon):
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)

        x0 = int(np.searchsorted(self.xs, minx, side="left"))
        x1 = int(np.searchsorted(self.xs, maxx, side="right"))
        if self.ys[0] > self.ys[-1]:
            rev = self.ys[::-1]
            ry0 = int(np.searchsorted(rev, miny, side="left"))
            ry1 = int(np.searchsorted(rev, maxy, side="right"))
            y0 = max(0, len(self.ys) - ry1)
            y1 = min(len(self.ys), len(self.ys) - ry0)
        else:
            y0 = int(np.searchsorted(self.ys, miny, side="left"))
            y1 = int(np.searchsorted(self.ys, maxy, side="right"))

        x0 = max(0, min(x0, len(self.xs)))
        x1 = max(0, min(x1, len(self.xs)))
        y0 = max(0, min(y0, len(self.ys)))
        y1 = max(0, min(y1, len(self.ys)))
        if x1 <= x0 or y1 <= y0:
            return None

        values = []
        stride = 1
        for row in range(y0, y1, stride):
            y = float(self.ys[row])
            for col in range(x0, x1, stride):
                x = float(self.xs[col])
                if hero.point_in_polygon(x, y, polygon):
                    value = float(self.height[row, col])
                    if math.isfinite(value) and value > 1.0:
                        values.append(value)

        if len(values) < 4:
            return None

        arr = np.asarray(values, dtype=np.float32)
        p10, p25, p50, p75, p90 = np.percentile(arr, [10, 25, 50, 75, 90])
        return {
            "samples": int(arr.size),
            "p10": float(p10),
            "p25": float(p25),
            "p50": float(p50),
            "p75": float(p75),
            "p90": float(p90),
            "spread_p90_p25": float(max(0.0, p90 - p25)),
        }


def is_convex_polygon(points):
    if len(points) < 3:
        return False
    sign = 0
    n = len(points)
    for i in range(n):
        ax, ay = points[i]
        bx, by = points[(i + 1) % n]
        cx, cy = points[(i + 2) % n]
        cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
        if abs(cross) < 1e-8:
            continue
        current = 1 if cross > 0 else -1
        if sign == 0:
            sign = current
        elif sign != current:
            return False
    return True


def footprint_aspect(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    return max(width, height) / max(1e-6, min(width, height))


def explicit_roof_form(tags):
    raw = str(tags.get("roof:shape") or "").lower()
    if raw in {"gabled", "gable", "gambrel", "saltbox"}:
        return "gabled"
    if raw in {"hipped", "hip", "pyramidal", "half-hipped", "mansard"}:
        return "hipped"
    if raw in {"skillion", "shed"}:
        return "skillion"
    return None


def choose_roof_form(record):
    footprint = record["footprint"]
    explicit = explicit_roof_form(record["tags"])
    if explicit:
        return explicit
    if len(footprint) == 4 and footprint_aspect(footprint) >= 1.16:
        return "gabled"
    return "hipped"


def estimate_rise(record, hag_stats):
    area = max(1.0, float(record["area"]))
    default = max(0.85, min(3.0, math.sqrt(area) * 0.12))
    if hag_stats is None:
        return default
    spread = float(hag_stats["spread_p90_p25"])
    if spread <= 0.0:
        return default
    return max(0.75, min(3.8, spread * 0.92))


def add_gabled(vertices, faces, indices, footprint, eave_z, rise, roof_index, gable_index):
    if len(footprint) != 4:
        return False
    pts = [Vector((x, y, eave_z)) for x, y in footprint]
    lengths = [(pts[(i + 1) % 4] - pts[i]).length for i in range(4)]
    start = len(vertices)
    vertices.extend(tuple(p) for p in pts)

    if lengths[0] + lengths[2] >= lengths[1] + lengths[3]:
        r_a_xy = (pts[3] + pts[0]) * 0.5
        r_b_xy = (pts[1] + pts[2]) * 0.5
        r_a = len(vertices)
        vertices.append((r_a_xy.x, r_a_xy.y, eave_z + rise))
        r_b = len(vertices)
        vertices.append((r_b_xy.x, r_b_xy.y, eave_z + rise))
        faces.extend([
            (start + 0, start + 1, r_b, r_a),
            (start + 2, start + 3, r_a, r_b),
            (start + 1, start + 2, r_b),
            (start + 3, start + 0, r_a),
        ])
    else:
        r_a_xy = (pts[0] + pts[1]) * 0.5
        r_b_xy = (pts[2] + pts[3]) * 0.5
        r_a = len(vertices)
        vertices.append((r_a_xy.x, r_a_xy.y, eave_z + rise))
        r_b = len(vertices)
        vertices.append((r_b_xy.x, r_b_xy.y, eave_z + rise))
        faces.extend([
            (start + 1, start + 2, r_b, r_a),
            (start + 3, start + 0, r_a, r_b),
            (start + 0, start + 1, r_a),
            (start + 2, start + 3, r_b),
        ])
    indices.extend([roof_index, roof_index, gable_index, gable_index])
    return True


def add_hipped(vertices, faces, indices, footprint, eave_z, rise, roof_index):
    if not is_convex_polygon(footprint):
        return False
    center = hero.polygon_centroid(footprint)
    apex = len(vertices)
    vertices.append((center[0], center[1], eave_z + rise))
    ring = []
    for x, y in footprint:
        ring.append(len(vertices))
        vertices.append((x, y, eave_z))
    for i in range(len(ring)):
        faces.append((ring[i], ring[(i + 1) % len(ring)], apex))
        indices.append(roof_index)
    return True


def add_skillion(vertices, faces, indices, footprint, eave_z, rise, roof_index):
    if not is_convex_polygon(footprint):
        return False
    xs = [p[0] for p in footprint]
    ys = [p[1] for p in footprint]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    use_x = width <= height
    lo = min(xs) if use_x else min(ys)
    hi = max(xs) if use_x else max(ys)
    denom = max(1e-6, hi - lo)

    start = len(vertices)
    for x, y in footprint:
        coord = x if use_x else y
        z = eave_z + rise * ((coord - lo) / denom)
        vertices.append((x, y, z))

    # Convex polygons are safe to fan from an interior centroid projected to
    # the same skillion plane.
    cx, cy = hero.polygon_centroid(footprint)
    coord = cx if use_x else cy
    cz = eave_z + rise * ((coord - lo) / denom)
    center = len(vertices)
    vertices.append((cx, cy, cz))
    for i in range(len(footprint)):
        faces.append((center, start + i, start + (i + 1) % len(footprint)))
        indices.append(roof_index)
    return True


def delete_detail_faces(footprints):
    stats = {}
    for name in ("Detail_Solar", "Detail_Rooftop", "Detail_HVAC"):
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            continue
        matrix = obj.matrix_world.copy()
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        before = len(bm.faces)
        doomed = []
        for face in bm.faces:
            center = matrix @ face.calc_center_median()
            if any(
                hero.point_in_polygon(float(center.x), float(center.y), fp)
                for fp in footprints
            ):
                doomed.append(face)
        if doomed:
            bmesh.ops.delete(bm, geom=doomed, context="FACES")
        loose_edges = [edge for edge in bm.edges if not edge.link_faces]
        if loose_edges:
            bmesh.ops.delete(bm, geom=loose_edges, context="EDGES")
        loose_verts = [vertex for vertex in bm.verts if not vertex.link_faces]
        if loose_verts:
            bmesh.ops.delete(bm, geom=loose_verts, context="VERTS")
        after = len(bm.faces)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        stats[name] = {"before_faces": before, "after_faces": after}
    return stats


def main():
    for required in (SOURCE, OSM_LOCAL, HAG):
        if not required.is_file():
            raise SystemExit(f"Missing input: {required}")

    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    scene = bpy.context.scene
    camera = scene.camera
    if camera is None:
        raise RuntimeError("production camera missing")

    camera_before = audit.camera_signature(scene, camera)
    camera_tree, _camera_points = audit.build_camera_kdtree(scene, camera)

    source = json.loads(OSM_LOCAL.read_text())
    grid, buildings = audit.build_building_index(source)
    ortho = audit.OrthoSampler()
    hag = HAGSampler(HAG)

    city = bpy.data.objects.get("City_Buildings")
    if city is None or city.type != "MESH":
        raise RuntimeError("City_Buildings missing")

    # Reuse accepted materials from 018.
    tile_dark = bpy.data.materials.get("City_Roof_00")
    tile_bright = bpy.data.materials.get("City_Roof_01") or tile_dark
    metal = bpy.data.materials.get("Route_Pitched_Metal")
    flat_warm = bpy.data.materials.get("Route_Flat_Warm")
    flat_gray = bpy.data.materials.get("Route_Flat_Gray")
    if None in (tile_dark, tile_bright, metal, flat_warm, flat_gray):
        raise RuntimeError("Expected 018 roof materials missing")

    wall_materials = []
    fallback_wall = hero.material("Route_Gable_Wall", (0.56, 0.53, 0.48, 1.0), 0.82)
    for i in range(5):
        wall_materials.append(bpy.data.materials.get(f"City_Wall_{i:02d}") or fallback_wall)

    overlay_materials = [*wall_materials, tile_dark, tile_bright, metal]
    TILE_DARK = 5
    TILE_BRIGHT = 6
    METAL = 7

    matrix = city.matrix_world.copy()
    normal_matrix = matrix.to_3x3().inverted().transposed()

    bm = bmesh.new()
    bm.from_mesh(city.data)
    bm.faces.ensure_lookup_table()

    candidates = {}
    stats = defaultdict(int)
    class_sources = defaultdict(int)

    for face in bm.faces:
        mat_index = int(face.material_index)
        if mat_index < 0 or mat_index >= len(city.data.materials):
            continue
        mat = city.data.materials[mat_index]
        if mat is None:
            continue
        name = mat.name
        if not (name.startswith("City_Roof_") or name == "Route_Pitched_Metal"):
            continue

        world_normal = normal_matrix @ face.normal
        if float(world_normal.z) < NEAR_FLAT_Z:
            stats["already_sloped_faces"] += 1
            continue

        center_world = matrix @ face.calc_center_median()
        _co, _idx, corridor_distance = camera_tree.find(
            (float(center_world.x), float(center_world.y), 0.0)
        )
        if corridor_distance > CORRIDOR_RADIUS_M:
            stats["outside_corridor"] += 1
            continue

        record = audit.match_building(
            float(center_world.x), float(center_world.y), grid
        )
        if record is None:
            # Safety-first fallback: an unmatched horizontal slab in the route
            # corridor may never retain a tile texture. Without a building
            # footprint we cannot construct a trustworthy slope, so use neutral
            # flat roofing instead.
            flat_slot = audit.ensure_material_slot(city, flat_gray)
            if face.material_index != flat_slot:
                face.material_index = flat_slot
                stats["unmatched_tile_removed"] += 1
            stats["unmatched"] += 1
            continue

        signal = audit.ortho_roof_signal(
            ortho.median_rgb(float(center_world.x), float(center_world.y))
        )
        final_class, final_source = audit.choose_final_class(record, signal)
        hag_stats = hag.stats_for_polygon(record["footprint"])

        # Unknown/ortho-only tile decisions need actual LiDAR relief evidence.
        if (
            final_class == "pitched"
            and final_source == "ortho-color"
            and (
                hag_stats is None
                or hag_stats["spread_p90_p25"] < MIN_HAG_PITCH_SPREAD_M
            )
        ):
            final_class = "flat"
            final_source = "lidar-flat-override"

        class_sources[final_source] += 1
        way_id = int(record["way_id"])

        if final_class == "flat":
            # Safety net: a horizontal face must never retain tile after 019.
            bucket = signal["bucket"]
            target = flat_warm if bucket == "warm" else flat_gray
            slot = audit.ensure_material_slot(city, target)
            if face.material_index != slot:
                face.material_index = slot
                stats["late_flat_material_fixes"] += 1
            stats["flat_kept"] += 1
            continue

        top_z = max(float((matrix @ vertex.co).z) for vertex in face.verts)
        item = candidates.setdefault(
            way_id,
            {
                "record": record,
                "signal": signal,
                "class": final_class,
                "source": final_source,
                "hag": hag_stats,
                "faces": [],
                "top_z": top_z,
                "corridor_distance_m": float(corridor_distance),
            },
        )
        item["faces"].append(face)
        item["top_z"] = max(float(item["top_z"]), top_z)
        item["corridor_distance_m"] = min(
            float(item["corridor_distance_m"]), float(corridor_distance)
        )

    vertices = []
    faces = []
    indices = []
    delete_faces = []
    converted = []
    fallback_flat = []
    changed_centers = []

    for way_id, item in sorted(candidates.items()):
        record = item["record"]
        footprint = record["footprint"]
        hag_stats = item["hag"]
        final_class = item["class"]
        roof_form = choose_roof_form(record)
        rise = estimate_rise(record, hag_stats)

        safe = (
            len(footprint) <= MAX_SAFE_VERTICES
            and is_convex_polygon(footprint)
        )
        if roof_form == "gabled":
            safe = safe and len(footprint) == 4

        signal = item["signal"]
        bright = (signal.get("luminance") or 0.0) >= 125.0
        roof_index = (
            METAL
            if final_class == "pitched-metal"
            else (TILE_BRIGHT if bright else TILE_DARK)
        )
        gable_index = int(way_id) % len(wall_materials)

        built = False
        eave_z = float(item["top_z"]) + 0.035
        if safe:
            if roof_form == "gabled":
                built = add_gabled(
                    vertices, faces, indices,
                    footprint, eave_z, rise, roof_index, gable_index,
                )
            elif roof_form == "skillion":
                built = add_skillion(
                    vertices, faces, indices,
                    footprint, eave_z, rise, roof_index,
                )
            else:
                built = add_hipped(
                    vertices, faces, indices,
                    footprint, eave_z, rise, roof_index,
                )

        if built:
            delete_faces.extend(item["faces"])
            center = hero.polygon_centroid(footprint)
            changed_centers.append((center[0], center[1], eave_z + rise * 0.5))
            stats["buildings_converted"] += 1
            stats[f"form_{roof_form}"] += 1
            stats[f"class_{final_class}"] += 1
            converted.append(
                {
                    "way_id": way_id,
                    "building": record["tags"].get("building"),
                    "roof_shape": record["tags"].get("roof:shape"),
                    "class": final_class,
                    "source": item["source"],
                    "roof_form": roof_form,
                    "footprint_vertices": len(footprint),
                    "roof_rise_m": round(float(rise), 2),
                    "hag": hag_stats,
                    "corridor_distance_m": round(float(item["corridor_distance_m"]), 1),
                }
            )
        else:
            # Complex/concave footprints stay non-tile until a building:part
            # decomposition exists. Never leave tile on a horizontal slab.
            signal_bucket = signal["bucket"]
            target = flat_warm if signal_bucket == "warm" else flat_gray
            target_slot = audit.ensure_material_slot(city, target)
            for face in item["faces"]:
                face.material_index = target_slot
            stats["complex_non_tile_fallback"] += 1
            fallback_flat.append(
                {
                    "way_id": way_id,
                    "building": record["tags"].get("building"),
                    "roof_shape": record["tags"].get("roof:shape"),
                    "requested_class": final_class,
                    "source": item["source"],
                    "footprint_vertices": len(footprint),
                    "convex": is_convex_polygon(footprint),
                }
            )

    if delete_faces:
        bmesh.ops.delete(bm, geom=delete_faces, context="FACES")
    loose_edges = [edge for edge in bm.edges if not edge.link_faces]
    if loose_edges:
        bmesh.ops.delete(bm, geom=loose_edges, context="EDGES")
    loose_verts = [vertex for vertex in bm.verts if not vertex.link_faces]
    if loose_verts:
        bmesh.ops.delete(bm, geom=loose_verts, context="VERTS")

    bm.to_mesh(city.data)
    bm.free()
    city.data.update()

    mesh = bpy.data.meshes.new("Route_Pitched_Roofs_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    overlay = bpy.data.objects.new("Route_Pitched_Roofs", mesh)
    bpy.context.collection.objects.link(overlay)
    for mat in overlay_materials:
        mesh.materials.append(mat)
    for polygon, material_index in zip(mesh.polygons, indices):
        polygon.material_index = material_index
    overlay["version"] = "coimbra-route-pitched-roofs-v1"
    overlay["building_count"] = int(stats["buildings_converted"])

    removed_details = delete_detail_faces(
        [item["record"]["footprint"] for item in candidates.values()]
    )

    # Hard invariant: no horizontal City_Roof_* tile face may remain in the
    # route corridor after this pass.
    remaining_horizontal_tile = 0
    matrix = city.matrix_world.copy()
    normal_matrix = matrix.to_3x3().inverted().transposed()
    for polygon in city.data.polygons:
        mat = city.data.materials[polygon.material_index]
        if mat is None or not mat.name.startswith("City_Roof_"):
            continue
        world_normal = normal_matrix @ polygon.normal
        if float(world_normal.z) < NEAR_FLAT_Z:
            continue
        center = matrix @ polygon.center
        _co, _idx, distance = camera_tree.find(
            (float(center.x), float(center.y), 0.0)
        )
        if distance <= CORRIDOR_RADIUS_M:
            remaining_horizontal_tile += 1

    stats["remaining_horizontal_tile_faces"] = remaining_horizontal_tile
    stats["new_roof_vertices"] = len(vertices)
    stats["new_roof_faces"] = len(faces)

    if stats["buildings_converted"] < 40:
        raise RuntimeError(
            f"Too few pitched buildings converted: {dict(stats)}"
        )
    if remaining_horizontal_tile != 0:
        raise RuntimeError(
            f"Horizontal tile faces remain in route corridor: {remaining_horizontal_tile}"
        )

    camera_after = audit.camera_signature(scene, camera)
    if camera_after != camera_before:
        raise RuntimeError("production camera changed during pitched-roof pass")

    review_frames = audit.select_review_frames(scene, camera, changed_centers)

    scene["route_pitched_roofs_version"] = "coimbra-route-pitched-roofs-v1"
    scene["route_pitched_roofs_buildings"] = int(stats["buildings_converted"])
    scene["route_horizontal_tile_remaining"] = int(remaining_horizontal_tile)

    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))

    result = {
        "version": "coimbra-route-pitched-roofs-v1",
        "source_scene": SOURCE.relative_to(ROOT).as_posix(),
        "output_scene": OUT_BLEND.relative_to(ROOT).as_posix(),
        "corridor_radius_m": CORRIDOR_RADIUS_M,
        "horizontal_threshold_normal_z": NEAR_FLAT_Z,
        "min_hag_pitch_spread_m": MIN_HAG_PITCH_SPREAD_M,
        "stats": dict(stats),
        "classification_sources": dict(class_sources),
        "converted_examples": converted[:80],
        "complex_fallback_examples": fallback_flat[:40],
        "removed_old_rooftop_detail_faces": removed_details,
        "review_frames": review_frames,
        "camera_unchanged": camera_before == camera_after,
        "rules": {
            "horizontal_tile_faces_in_corridor": 0,
            "flat_never_tile": True,
            "tile_requires_real_slope_geometry": True,
            "unknown_tile_color_requires_lidar_relief": True,
            "complex_concave_roof_falls_back_non_tile": True,
            "dgt_ortho_used": True,
            "dgt_lidar_hag_used": True,
        },
    }
    MANIFEST.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
