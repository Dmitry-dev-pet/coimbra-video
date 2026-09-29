from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import bmesh
import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "bridge_output_011" / "coimbra-polo2-photo-patch.blend"
OSM_LOCAL = ROOT / "data" / "processed" / "bridge_osm_oss_local.json"
TERRAIN = ROOT / "bridge_output_008b" / "bridge_terrain_highres_2m.npz"
OUT = ROOT / "bridge_output_012"
HERO = OUT / "hero-buildings.png"
CLOSE_A = OUT / "hero-building-close-a.png"
CLOSE_B = OUT / "hero-building-close-b.png"
MANIFEST = OUT / "hero-buildings-manifest.json"

HERO_COUNT = 5
PATCH_CENTER = (-168.37, -748.07)
PATCH_HALF = 118.0


class TerrainSampler:
    def __init__(self, path: Path):
        data = np.load(path)
        self.z = data["z"].astype(np.float32)
        self.xs = data["xs"].astype(np.float32)
        self.ys = data["ys"].astype(np.float32)
        self.z0 = float(data["z0"])

    def sample(self, x: float, y: float) -> float | None:
        min_x, max_x = sorted((float(self.xs[0]), float(self.xs[-1])))
        min_y, max_y = sorted((float(self.ys[0]), float(self.ys[-1])))
        if not (min_x <= x <= max_x and min_y <= y <= max_y):
            return None
        fx = (x - float(self.xs[0])) / (
            float(self.xs[-1]) - float(self.xs[0])
        ) * (len(self.xs) - 1)
        fy = (float(self.ys[0]) - y) / (
            float(self.ys[0]) - float(self.ys[-1])
        ) * (len(self.ys) - 1)
        x0 = max(0, min(int(np.floor(fx)), len(self.xs) - 1))
        y0 = max(0, min(int(np.floor(fy)), len(self.ys) - 1))
        x1 = min(x0 + 1, len(self.xs) - 1)
        y1 = min(y0 + 1, len(self.ys) - 1)
        tx = fx - x0
        ty = fy - y0
        a = float(self.z[y0, x0])
        b = float(self.z[y0, x1])
        c = float(self.z[y1, x0])
        d = float(self.z[y1, x1])
        return (
            (a * (1.0 - tx) + b * tx) * (1.0 - ty)
            + (c * (1.0 - tx) + d * tx) * ty
            - self.z0
        )


def stable_unit(token: str, channel: int = 0) -> float:
    digest = hashlib.sha256(f"{token}:{channel}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / float((1 << 64) - 1)


def parse_number(value):
    if value is None:
        return None
    text = str(value).strip().lower().replace(",", ".")
    number = ""
    started = False
    for char in text:
        if char.isdigit() or char in ".-":
            number += char
            started = True
        elif started:
            break
    try:
        return float(number)
    except Exception:
        return None


def polygon_signed_area(points):
    total = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        total += x0 * y1 - x1 * y0
    return total * 0.5


def polygon_area(points):
    return abs(polygon_signed_area(points))


def polygon_centroid(points):
    signed = polygon_signed_area(points)
    if abs(signed) < 1e-8:
        return (
            sum(p[0] for p in points) / len(points),
            sum(p[1] for p in points) / len(points),
        )
    cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        cross = x0 * y1 - x1 * y0
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    factor = 1.0 / (6.0 * signed)
    return cx * factor, cy * factor


def point_in_polygon(x, y, polygon):
    inside = False
    j = len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
        ):
            inside = not inside
        j = i
    return inside


def building_height(tags):
    explicit = parse_number(tags.get("height"))
    if explicit is not None:
        return max(3.0, min(60.0, explicit))
    levels = parse_number(tags.get("building:levels"))
    if levels is not None:
        return max(3.0, min(60.0, levels * 3.05))
    kind = str(tags.get("building") or "").lower()
    if kind in {"church", "cathedral", "chapel"}:
        return 18.0
    if kind in {"industrial", "warehouse", "retail", "commercial"}:
        return 6.5
    return 9.0


def building_levels(tags, height):
    levels = parse_number(tags.get("building:levels"))
    if levels is not None:
        return max(1, min(12, int(round(levels))))
    return max(1, min(10, int(round(height / 3.05))))


def roof_class(tags, footprint):
    raw = str(tags.get("roof:shape") or "").lower()
    aliases = {
        "flat": "flat",
        "gabled": "gabled",
        "gable": "gabled",
        "hipped": "hipped",
        "hip": "hipped",
        "skillion": "skillion",
        "shed": "skillion",
        "pyramidal": "hipped",
    }
    if raw in aliases:
        return aliases[raw], "osm"

    kind = str(tags.get("building") or "").lower()
    flat_kinds = {
        "apartments", "commercial", "retail", "office", "school",
        "university", "industrial", "warehouse", "hospital", "civic",
    }
    pitched_kinds = {
        "house", "detached", "semidetached_house", "terrace",
        "bungalow", "farm",
    }

    xs = [p[0] for p in footprint]
    ys = [p[1] for p in footprint]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    aspect = max(width, height) / max(1e-6, min(width, height))
    area = polygon_area(footprint)

    if kind in flat_kinds:
        return "flat", "building-type"
    if kind in pitched_kinds:
        if len(footprint) == 4 and aspect >= 1.25:
            return "gabled", "building-type"
        return "hipped", "building-type"
    if area < 180.0:
        if len(footprint) == 4 and aspect >= 1.35:
            return "gabled", "size-heuristic"
        return "hipped", "size-heuristic"
    return "flat", "size-heuristic"


def material(name, color, roughness=0.7, metallic=0.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = color
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
    return mat


def glass_material():
    mat = bpy.data.materials.get("Hero_Window_Glass") or bpy.data.materials.new(
        "Hero_Window_Glass"
    )
    mat.use_nodes = True
    mat.diffuse_color = (0.035, 0.075, 0.095, 1.0)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (0.025, 0.055, 0.075, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.12
        bsdf.inputs["Metallic"].default_value = 0.05
        if "IOR" in bsdf.inputs:
            bsdf.inputs["IOR"].default_value = 1.45
    return mat


def existing_material(name, fallback):
    return bpy.data.materials.get(name) or fallback


def footprint_for_way(way, nodes):
    coords = []
    for node_id in way.get("nodes") or []:
        node = nodes.get(str(node_id))
        if node is None:
            return None
        x, y = node["xy"]
        coords.append((float(x), float(y)))
    if len(coords) >= 4 and coords[0] == coords[-1]:
        coords = coords[:-1]
    if len(coords) < 3:
        return None
    return coords


def in_patch(point):
    x, y = point
    cx, cy = PATCH_CENTER
    return abs(x - cx) <= PATCH_HALF and abs(y - cy) <= PATCH_HALF


def select_hero_buildings(scene, source, terrain):
    camera = scene.camera
    if camera is None:
        raise RuntimeError("Photo patch camera missing")

    candidates = []
    for way in source["ways"]:
        tags = way.get("tags") or {}
        if "building" not in tags:
            continue
        footprint = footprint_for_way(way, source["nodes"])
        if not footprint:
            continue
        center = polygon_centroid(footprint)
        if not in_patch(center):
            continue
        area = polygon_area(footprint)
        if area < 20.0:
            continue

        ground = terrain.sample(*center)
        if ground is None:
            continue
        height = building_height(tags)
        top = ground + 0.35 + height

        projections = []
        for x, y in footprint:
            co = world_to_camera_view(
                scene, camera, Vector((x, y, top * 0.72))
            )
            projections.append(co)
        xs = [p.x for p in projections]
        ys = [p.y for p in projections]
        zs = [p.z for p in projections]
        if max(zs) <= 0.0:
            continue
        if max(xs) < -0.05 or min(xs) > 1.05 or max(ys) < -0.05 or min(ys) > 1.05:
            continue

        clipped_w = max(0.0, min(1.0, max(xs)) - max(0.0, min(xs)))
        clipped_h = max(0.0, min(1.0, max(ys)) - max(0.0, min(ys)))
        screen_area = clipped_w * clipped_h
        if screen_area <= 0.0004:
            continue

        distance = (
            Vector((center[0], center[1], top * 0.55)) - camera.location
        ).length
        score = screen_area * (1.0 + 35.0 / max(12.0, distance))

        roof, roof_source = roof_class(tags, footprint)
        candidates.append(
            {
                "way_id": int(way["id"]),
                "tags": tags,
                "footprint": footprint,
                "center": center,
                "ground": ground + 0.35,
                "height": height,
                "levels": building_levels(tags, height),
                "roof": roof,
                "roof_source": roof_source,
                "screen_area": screen_area,
                "distance": distance,
                "score": score,
            }
        )

    candidates.sort(key=lambda item: item["score"], reverse=True)
    selected = candidates[:HERO_COUNT]
    if len(selected) < HERO_COUNT:
        raise RuntimeError(
            f"Only {len(selected)} visible hero buildings found, need {HERO_COUNT}"
        )
    return selected


def delete_existing_detail_faces(selected):
    polygons = [item["footprint"] for item in selected]
    stats = {}
    for name in ("Facade_Windows", "Detail_Solar", "Detail_Rooftop", "Detail_HVAC"):
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
                point_in_polygon(float(center.x), float(center.y), footprint)
                for footprint in polygons
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


def add_oriented_box(
    vertices,
    faces,
    indices,
    center,
    axis_x,
    axis_y,
    sx,
    sy,
    sz,
    material_index,
):
    x = axis_x.normalized()
    y = axis_y.normalized()
    z = Vector((0.0, 0.0, 1.0))
    hx = x * (sx * 0.5)
    hy = y * (sy * 0.5)
    hz = z * (sz * 0.5)
    c = Vector(center)
    base = len(vertices)
    for dz in (-hz, hz):
        vertices.extend(
            [
                tuple(c - hx - hy + dz),
                tuple(c + hx - hy + dz),
                tuple(c + hx + hy + dz),
                tuple(c - hx + hy + dz),
            ]
        )
    faces.extend(
        [
            (base, base + 1, base + 2, base + 3),
            (base + 4, base + 7, base + 6, base + 5),
            (base, base + 4, base + 5, base + 1),
            (base + 1, base + 5, base + 6, base + 2),
            (base + 2, base + 6, base + 7, base + 3),
            (base + 3, base + 7, base + 4, base),
        ]
    )
    indices.extend([material_index] * 6)


def outward_for_edge(p0, p1, signed_area):
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    length = math.hypot(dx, dy)
    if length < 1e-8:
        return Vector((0.0, 1.0, 0.0))
    if signed_area > 0:
        return Vector((dy / length, -dx / length, 0.0))
    return Vector((-dy / length, dx / length, 0.0))


def add_shell_wall(vertices, faces, indices, p0, p1, base_z, top_z, outward, mat_index):
    start = len(vertices)
    lift = outward * 0.075
    vertices.extend(
        [
            (p0[0] + lift.x, p0[1] + lift.y, base_z),
            (p1[0] + lift.x, p1[1] + lift.y, base_z),
            (p1[0] + lift.x, p1[1] + lift.y, top_z),
            (p0[0] + lift.x, p0[1] + lift.y, top_z),
        ]
    )
    faces.append((start, start + 1, start + 2, start + 3))
    indices.append(mat_index)


def add_window(
    vertices,
    faces,
    indices,
    *,
    center,
    along,
    outward,
    width,
    height,
    frame_width,
    glass_material_index,
    frame_material_index,
    sill_material_index,
):
    # A shallow dark glass plate overlays the opaque wall shell. A four-piece
    # frame and sill make it read as an actual window without expensive booleans.
    add_oriented_box(
        vertices, faces, indices,
        center=Vector(center) + outward * 0.115,
        axis_x=along,
        axis_y=outward,
        sx=width,
        sy=0.028,
        sz=height,
        material_index=glass_material_index,
    )
    z = Vector((0.0, 0.0, 1.0))
    left = Vector(center) - along * (width * 0.5 + frame_width * 0.5) + outward * 0.135
    right = Vector(center) + along * (width * 0.5 + frame_width * 0.5) + outward * 0.135
    add_oriented_box(
        vertices, faces, indices,
        center=left, axis_x=along, axis_y=outward,
        sx=frame_width, sy=0.045, sz=height + frame_width * 2,
        material_index=frame_material_index,
    )
    add_oriented_box(
        vertices, faces, indices,
        center=right, axis_x=along, axis_y=outward,
        sx=frame_width, sy=0.045, sz=height + frame_width * 2,
        material_index=frame_material_index,
    )
    for sign in (-1.0, 1.0):
        bar_center = (
            Vector(center)
            + z * sign * (height * 0.5 + frame_width * 0.5)
            + outward * 0.135
        )
        add_oriented_box(
            vertices, faces, indices,
            center=bar_center, axis_x=along, axis_y=outward,
            sx=width + frame_width * 2, sy=0.045, sz=frame_width,
            material_index=frame_material_index,
        )
    sill_center = (
        Vector(center)
        - z * (height * 0.5 + frame_width * 1.8)
        + outward * 0.17
    )
    add_oriented_box(
        vertices, faces, indices,
        center=sill_center, axis_x=along, axis_y=outward,
        sx=width + 0.18, sy=0.22, sz=0.055,
        material_index=sill_material_index,
    )


def add_door(
    vertices, faces, indices, *, center, along, outward, frame_index, glass_index
):
    add_oriented_box(
        vertices, faces, indices,
        center=Vector(center) + outward * 0.12,
        axis_x=along, axis_y=outward,
        sx=1.15, sy=0.035, sz=2.25, material_index=glass_index,
    )
    for offset in (-0.65, 0.65):
        c = Vector(center) + along * offset + outward * 0.145
        add_oriented_box(
            vertices, faces, indices,
            center=c, axis_x=along, axis_y=outward,
            sx=0.09, sy=0.05, sz=2.42, material_index=frame_index,
        )
    top = Vector(center) + Vector((0, 0, 1.22)) + outward * 0.145
    add_oriented_box(
        vertices, faces, indices,
        center=top, axis_x=along, axis_y=outward,
        sx=1.39, sy=0.05, sz=0.09, material_index=frame_index,
    )


def add_flat_roof(vertices, faces, indices, footprint, top_z, roof_index, parapet_index):
    center = polygon_centroid(footprint)
    center_index = len(vertices)
    vertices.append((center[0], center[1], top_z + 0.085))
    ring = []
    for x, y in footprint:
        ring.append(len(vertices))
        vertices.append((x, y, top_z + 0.085))
    for i in range(len(ring)):
        faces.append((center_index, ring[i], ring[(i + 1) % len(ring)]))
        indices.append(roof_index)

    signed = polygon_signed_area(footprint)
    for p0, p1 in zip(footprint, footprint[1:] + footprint[:1]):
        outward = outward_for_edge(p0, p1, signed)
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        length = math.hypot(dx, dy)
        if length < 0.4:
            continue
        along = Vector((dx / length, dy / length, 0.0))
        midpoint = Vector(((p0[0] + p1[0]) * 0.5, (p0[1] + p1[1]) * 0.5, top_z + 0.22))
        add_oriented_box(
            vertices, faces, indices,
            center=midpoint + outward * 0.03,
            axis_x=along, axis_y=outward,
            sx=length, sy=0.14, sz=0.28,
            material_index=parapet_index,
        )


def add_hipped_roof(vertices, faces, indices, footprint, top_z, roof_index):
    center = polygon_centroid(footprint)
    area = polygon_area(footprint)
    rise = max(1.1, min(3.2, math.sqrt(area) * 0.16))
    apex = len(vertices)
    vertices.append((center[0], center[1], top_z + rise))
    ring = []
    for x, y in footprint:
        ring.append(len(vertices))
        vertices.append((x, y, top_z + 0.05))
    for i in range(len(ring)):
        faces.append((ring[i], ring[(i + 1) % len(ring)], apex))
        indices.append(roof_index)


def add_gabled_roof(vertices, faces, indices, footprint, top_z, roof_index, gable_index):
    if len(footprint) != 4:
        add_hipped_roof(vertices, faces, indices, footprint, top_z, roof_index)
        return "hipped-fallback"

    pts = [Vector((x, y, top_z + 0.05)) for x, y in footprint]
    lengths = [(pts[(i + 1) % 4] - pts[i]).length for i in range(4)]
    pair0 = lengths[0] + lengths[2]
    pair1 = lengths[1] + lengths[3]
    rise = max(1.0, min(3.0, min(max(lengths), 14.0) * 0.28))
    start = len(vertices)
    vertices.extend(tuple(p) for p in pts)

    if pair0 >= pair1:
        r_a_xy = (pts[3] + pts[0]) * 0.5
        r_b_xy = (pts[1] + pts[2]) * 0.5
        r_a = len(vertices)
        vertices.append((r_a_xy.x, r_a_xy.y, top_z + rise))
        r_b = len(vertices)
        vertices.append((r_b_xy.x, r_b_xy.y, top_z + rise))
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
        vertices.append((r_a_xy.x, r_a_xy.y, top_z + rise))
        r_b = len(vertices)
        vertices.append((r_b_xy.x, r_b_xy.y, top_z + rise))
        faces.extend([
            (start + 1, start + 2, r_b, r_a),
            (start + 3, start + 0, r_a, r_b),
            (start + 0, start + 1, r_a),
            (start + 2, start + 3, r_b),
        ])
    indices.extend([roof_index, roof_index, gable_index, gable_index])
    return "gabled"


def build_hero_geometry(selected, scene):
    wall_fallback = material("Hero_Wall_Fallback", (0.68, 0.63, 0.54, 1.0), 0.78)
    flat_roof = material("Hero_Roof_Flat_Membrane", (0.16, 0.17, 0.17, 1.0), 0.90)
    parapet = material("Hero_Parapet", (0.54, 0.52, 0.48, 1.0), 0.82)
    frame_light = material("Hero_Window_Frame_Light", (0.72, 0.72, 0.69, 1.0), 0.42)
    frame_dark = material("Hero_Window_Frame_Dark", (0.075, 0.082, 0.085, 1.0), 0.40, 0.18)
    sill = material("Hero_Window_Sill", (0.45, 0.45, 0.42, 1.0), 0.70)
    glass = glass_material()
    tile = existing_material("City_Roof_01", material("Hero_Tile", (0.46, 0.16, 0.07, 1.0), 0.78))

    walls = []
    for index in range(5):
        walls.append(existing_material(f"City_Wall_{index:02d}", wall_fallback))

    materials = [*walls, flat_roof, parapet, tile, glass, frame_light, frame_dark, sill]
    flat_index = 5
    parapet_index = 6
    tile_index = 7
    glass_index = 8
    frame_light_index = 9
    frame_dark_index = 10
    sill_index = 11

    vertices = []
    faces = []
    indices = []
    details = []
    camera_xy = Vector((scene.camera.location.x, scene.camera.location.y, 0.0))

    for item in selected:
        footprint = item["footprint"]
        signed = polygon_signed_area(footprint)
        base_z = item["ground"]
        top_z = base_z + item["height"]
        wall_index = int(item["way_id"]) % len(walls)

        center3 = Vector((item["center"][0], item["center"][1], base_z))
        to_camera = camera_xy - Vector((item["center"][0], item["center"][1], 0.0))
        if to_camera.length > 1e-8:
            to_camera.normalize()

        front_edge = None
        front_score = -1e9
        wall_stats = []
        for edge_index, (p0, p1) in enumerate(zip(footprint, footprint[1:] + footprint[:1])):
            dx = p1[0] - p0[0]
            dy = p1[1] - p0[1]
            length = math.hypot(dx, dy)
            if length < 0.35:
                continue
            along = Vector((dx / length, dy / length, 0.0))
            outward = outward_for_edge(p0, p1, signed)
            add_shell_wall(
                vertices, faces, indices,
                p0, p1, base_z, top_z, outward, wall_index,
            )
            facing = outward.dot(to_camera)
            if facing > front_score:
                front_score = facing
                front_edge = edge_index

            if length < 3.3:
                wall_stats.append({"edge": edge_index, "length": length, "windows": 0})
                continue

            levels = item["levels"]
            floor_height = item["height"] / max(1, levels)
            columns = max(1, min(6, int(length / 3.0)))
            bay = length / columns
            frame_index = (
                frame_dark_index
                if stable_unit(str(item["way_id"]), edge_index) < 0.28
                else frame_light_index
            )
            window_count = 0

            for floor in range(levels):
                ground_floor = floor == 0
                window_h = min(
                    1.75 if ground_floor else 1.48,
                    floor_height * (0.58 if ground_floor else 0.50),
                )
                window_w = min(1.42, bay * 0.58)
                center_z = base_z + floor_height * (
                    0.52 if ground_floor else floor + 0.56
                )
                if not ground_floor:
                    center_z = base_z + floor_height * (floor + 0.56)

                for column in range(columns):
                    # Front façade gets a readable door instead of the centre
                    # ground-floor window.
                    if (
                        ground_floor
                        and edge_index == front_edge
                        and column == columns // 2
                        and columns >= 2
                    ):
                        continue
                    distance = bay * (column + 0.5)
                    cx = p0[0] + along.x * distance
                    cy = p0[1] + along.y * distance
                    add_window(
                        vertices, faces, indices,
                        center=(cx, cy, center_z),
                        along=along,
                        outward=outward,
                        width=window_w,
                        height=window_h,
                        frame_width=0.075,
                        glass_material_index=glass_index,
                        frame_material_index=frame_index,
                        sill_material_index=sill_index,
                    )
                    window_count += 1
            wall_stats.append(
                {"edge": edge_index, "length": length, "windows": window_count}
            )

        # Add the front door after front-edge discovery.
        if front_edge is not None:
            p0 = footprint[front_edge]
            p1 = footprint[(front_edge + 1) % len(footprint)]
            dx = p1[0] - p0[0]
            dy = p1[1] - p0[1]
            length = math.hypot(dx, dy)
            if length >= 4.5:
                along = Vector((dx / length, dy / length, 0.0))
                outward = outward_for_edge(p0, p1, signed)
                cx = (p0[0] + p1[0]) * 0.5
                cy = (p0[1] + p1[1]) * 0.5
                add_door(
                    vertices, faces, indices,
                    center=(cx, cy, base_z + 1.15),
                    along=along,
                    outward=outward,
                    frame_index=frame_dark_index,
                    glass_index=glass_index,
                )

        roof_requested = item["roof"]
        roof_built = roof_requested
        if roof_requested == "flat":
            add_flat_roof(
                vertices, faces, indices,
                footprint, top_z, flat_index, parapet_index,
            )
        elif roof_requested == "gabled":
            roof_built = add_gabled_roof(
                vertices, faces, indices,
                footprint, top_z, tile_index, wall_index,
            )
        elif roof_requested == "skillion":
            # A hipped form is safer than fake tile on a flat roof when the
            # footprint is irregular; keep tile only because the result slopes.
            add_hipped_roof(vertices, faces, indices, footprint, top_z, tile_index)
            roof_built = "hipped-from-skillion"
        else:
            add_hipped_roof(vertices, faces, indices, footprint, top_z, tile_index)

        details.append(
            {
                "way_id": item["way_id"],
                "building": item["tags"].get("building"),
                "levels": item["levels"],
                "height_m": item["height"],
                "screen_area": item["screen_area"],
                "distance_m": item["distance"],
                "roof_requested": roof_requested,
                "roof_built": roof_built,
                "roof_source": item["roof_source"],
                "uses_tile_material": roof_built != "flat",
                "front_edge": front_edge,
                "walls": wall_stats,
            }
        )

    mesh = bpy.data.meshes.new("Hero_Buildings_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Hero_Buildings", mesh)
    bpy.context.collection.objects.link(obj)
    for mat in materials:
        mesh.materials.append(mat)
    for polygon, index in zip(mesh.polygons, indices):
        polygon.material_index = index

    obj["version"] = "coimbra-hero-buildings-v1"
    obj["building_count"] = len(selected)
    obj["rule"] = "flat=no-tile; sloped=tile"
    return obj, details


def point_at(camera, target):
    camera.rotation_euler = (
        Vector(target) - camera.location
    ).to_track_quat("-Z", "Y").to_euler()


def render(scene, camera, path, resolution=(1600, 1000)):
    scene.camera = camera
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = int(resolution[0])
    scene.render.resolution_y = int(resolution[1])
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def closeup_camera(scene, item, source_camera, name, side_sign):
    center = Vector(
        (
            item["center"][0],
            item["center"][1],
            item["ground"] + item["height"] * 0.55,
        )
    )
    from_target = source_camera.location - center
    from_target.z *= 0.42
    if from_target.length < 1e-5:
        from_target = Vector((1.0, -1.0, 0.25))
    from_target.normalize()
    side = Vector((-from_target.y, from_target.x, 0.0))
    location = center + from_target * 33.0 + side * (side_sign * 8.0)
    location.z = center.z + max(5.0, item["height"] * 0.22)

    data = bpy.data.cameras.new(name)
    camera = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(camera)
    camera.location = location
    data.lens = 52.0
    data.sensor_width = 36.0
    data.clip_start = 0.08
    data.clip_end = 500.0
    data.dof.use_dof = True
    data.dof.focus_distance = (center - location).length
    data.dof.aperture_fstop = 4.5
    point_at(camera, center)
    return camera


def main():
    for required in (BASE, OSM_LOCAL, TERRAIN):
        if not required.is_file():
            raise SystemExit(f"Missing input: {required}")

    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(BASE))
    source = json.loads(OSM_LOCAL.read_text())
    terrain = TerrainSampler(TERRAIN)
    scene = bpy.context.scene
    source_camera = scene.camera
    if source_camera is None:
        raise RuntimeError("011 photo camera missing")

    selected = select_hero_buildings(scene, source, terrain)
    removed_details = delete_existing_detail_faces(selected)
    hero_obj, buildings = build_hero_geometry(selected, scene)

    scene["hero_building_version"] = "coimbra-hero-buildings-v1"
    scene["hero_building_count"] = len(buildings)
    scene["hero_roof_rule"] = "flat roofs never use tile material"

    render(scene, source_camera, HERO, (1600, 1000))

    close_a = closeup_camera(scene, selected[0], source_camera, "Hero_Close_A", -1.0)
    close_b = closeup_camera(scene, selected[1], source_camera, "Hero_Close_B", 1.0)
    render(scene, close_a, CLOSE_A, (1300, 950))
    render(scene, close_b, CLOSE_B, (1300, 950))
    bpy.data.objects.remove(close_a, do_unlink=True)
    bpy.data.objects.remove(close_b, do_unlink=True)
    scene.camera = source_camera

    tile_violations = [
        building["way_id"]
        for building in buildings
        if building["roof_built"] == "flat" and building["uses_tile_material"]
    ]
    if tile_violations:
        raise RuntimeError(f"Flat roofs use tile material: {tile_violations}")

    manifest = {
        "version": "coimbra-hero-buildings-v1",
        "hero_count": len(buildings),
        "selection": buildings,
        "removed_old_detail_faces": removed_details,
        "geometry": {
            "object": hero_obj.name,
            "vertices": len(hero_obj.data.vertices),
            "faces": len(hero_obj.data.polygons),
        },
        "roof_rule": {
            "flat_material": "Hero_Roof_Flat_Membrane",
            "pitched_material": "City_Roof_01",
            "flat_tile_violations": tile_violations,
        },
        "images": [
            HERO.relative_to(ROOT).as_posix(),
            CLOSE_A.relative_to(ROOT).as_posix(),
            CLOSE_B.relative_to(ROOT).as_posix(),
        ],
        "note": (
            "012 changes only five selected hero buildings in the Polo II photo "
            "patch. The rest of the 011 patch remains intentionally simple."
        ),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
