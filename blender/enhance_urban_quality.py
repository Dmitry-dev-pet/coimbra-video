from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "bridge_output_009d" / "coimbra-urban-details-visual-dev.blend"
OSM_LOCAL = ROOT / "data" / "processed" / "bridge_osm_oss_local.json"
TERRAIN = ROOT / "bridge_output_008b" / "bridge_terrain_highres_2m.npz"
OUT = ROOT / "bridge_output_010"
OUT_BLEND = OUT / "coimbra-urban-quality.blend"
MANIFEST = OUT / "urban-quality-manifest.json"

MOSAIQ_PARENT = ROOT / "_mosaiq"
if str(MOSAIQ_PARENT) not in sys.path:
    sys.path.insert(0, str(MOSAIQ_PARENT))

from mosaiq_osm_vr.src import addon_core as mos_core  # type: ignore
from mosaiq_osm_vr.src import addon_ui as mos_ui  # type: ignore


VERSION = "coimbra-urban-quality-v1"
SIDEWALK_WIDTH = 1.75
CURB_WIDTH = 0.16
CURB_HEIGHT = 0.14
MARKING_WIDTH = 0.11
MARKING_DASH = 3.0
MARKING_GAP = 5.0

QA_VIEWS = [
    {
        "name": "sanches-brasil",
        "location_xy": (-293.37, 851.60),
        "target_xy": (-692.18, 331.73),
        "lens": 34.0,
    },
    {
        "name": "polo-ii",
        "location_xy": (-168.37, -748.07),
        "target_xy": (463.44, -912.82),
        "lens": 36.0,
    },
    {
        "name": "portela",
        "location_xy": (463.44, -912.82),
        "target_xy": (666.22, -901.08),
        "lens": 38.0,
    },
]


class TerrainSampler:
    def __init__(self, path: Path):
        data = np.load(path)
        self.z = data["z"].astype(np.float32)
        self.xs = data["xs"].astype(np.float32)
        self.ys = data["ys"].astype(np.float32)
        self.z0 = float(data["z0"])

    def sample(self, x: float, y: float) -> float | None:
        min_x = min(float(self.xs[0]), float(self.xs[-1]))
        max_x = max(float(self.xs[0]), float(self.xs[-1]))
        min_y = min(float(self.ys[0]), float(self.ys[-1]))
        max_y = max(float(self.ys[0]), float(self.ys[-1]))
        if x < min_x or x > max_x or y < min_y or y > max_y:
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


def material(
    name: str,
    color: tuple[float, float, float, float],
    roughness: float = 0.65,
    metallic: float = 0.0,
    emission: tuple[float, float, float, float] | None = None,
    emission_strength: float = 0.0,
):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = color
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        if emission is not None:
            key = "Emission Color" if "Emission Color" in bsdf.inputs else "Emission"
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = emission
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat


def add_box(
    vertices,
    faces,
    material_indices,
    cx: float,
    cy: float,
    z0: float,
    sx: float,
    sy: float,
    sz: float,
    angle: float,
    material_index: int,
):
    ax = Vector((math.cos(angle), math.sin(angle), 0.0))
    ay = Vector((-math.sin(angle), math.cos(angle), 0.0))
    center = Vector((cx, cy, z0 + sz * 0.5))
    hx = ax * (sx * 0.5)
    hy = ay * (sy * 0.5)
    hz = Vector((0.0, 0.0, sz * 0.5))
    base = len(vertices)
    for dz in (-hz, hz):
        vertices.extend(
            [
                tuple(center - hx - hy + dz),
                tuple(center + hx - hy + dz),
                tuple(center + hx + hy + dz),
                tuple(center - hx + hy + dz),
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
    material_indices.extend([material_index] * 6)


def add_prism(
    vertices,
    faces,
    material_indices,
    cx: float,
    cy: float,
    z0: float,
    radius: float,
    height: float,
    sides: int,
    material_index: int,
):
    base = len(vertices)
    for z in (z0, z0 + height):
        for i in range(sides):
            angle = math.tau * i / sides
            vertices.append(
                (
                    cx + math.cos(angle) * radius,
                    cy + math.sin(angle) * radius,
                    z,
                )
            )
    for i in range(sides):
        j = (i + 1) % sides
        faces.append((base + i, base + j, base + sides + j, base + sides + i))
        material_indices.append(material_index)
    faces.append(tuple(base + i for i in reversed(range(sides))))
    material_indices.append(material_index)
    faces.append(tuple(base + sides + i for i in range(sides)))
    material_indices.append(material_index)


def add_vertical_plate(
    vertices,
    faces,
    material_indices,
    *,
    cx: float,
    cy: float,
    cz: float,
    radius: float,
    thickness: float,
    sides: int,
    angle: float,
    material_index: int,
    rotation: float = 0.0,
):
    normal = Vector((math.cos(angle), math.sin(angle), 0.0))
    side = Vector((-math.sin(angle), math.cos(angle), 0.0))
    center = Vector((cx, cy, cz))
    base = len(vertices)

    for depth in (-thickness * 0.5, thickness * 0.5):
        for i in range(sides):
            theta = rotation + math.tau * i / sides
            local_side = math.cos(theta) * radius
            local_z = math.sin(theta) * radius
            point = center + side * local_side + Vector((0.0, 0.0, local_z))
            point += normal * depth
            vertices.append(tuple(point))

    faces.append(tuple(base + i for i in reversed(range(sides))))
    material_indices.append(material_index)
    faces.append(tuple(base + sides + i for i in range(sides)))
    material_indices.append(material_index)
    for i in range(sides):
        j = (i + 1) % sides
        faces.append((base + i, base + j, base + sides + j, base + sides + i))
        material_indices.append(material_index)


def add_segment_prism(
    vertices,
    faces,
    material_indices,
    *,
    p0: tuple[float, float],
    p1: tuple[float, float],
    offset: float,
    width: float,
    base_height: float,
    height: float,
    terrain: TerrainSampler,
    material_index: int,
):
    x0, y0 = p0
    x1, y1 = p1
    dx = x1 - x0
    dy = y1 - y0
    length = math.hypot(dx, dy)
    if length < 0.15:
        return False
    nx = -dy / length
    ny = dx / length

    points = []
    for x, y in ((x0, y0), (x1, y1)):
        sx = x + nx * offset
        sy = y + ny * offset
        z = terrain.sample(sx, sy)
        if z is None:
            return False
        points.append((sx, sy, z + base_height))

    base = len(vertices)
    half = width * 0.5
    for x, y, z in points:
        vertices.append((x - nx * half, y - ny * half, z))
        vertices.append((x + nx * half, y + ny * half, z))
    for x, y, z in points:
        vertices.append((x - nx * half, y - ny * half, z + height))
        vertices.append((x + nx * half, y + ny * half, z + height))

    faces.extend(
        [
            (base, base + 1, base + 3, base + 2),
            (base + 4, base + 6, base + 7, base + 5),
            (base, base + 4, base + 5, base + 1),
            (base + 2, base + 3, base + 7, base + 6),
            (base, base + 2, base + 6, base + 4),
            (base + 1, base + 5, base + 7, base + 3),
        ]
    )
    material_indices.extend([material_index] * 6)
    return True


def finalize(name, vertices, faces, indices, materials):
    if not faces:
        return None
    mesh = bpy.data.meshes.new(name + "_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    for mat in materials:
        mesh.materials.append(mat)
    for polygon, index in zip(mesh.polygons, indices):
        polygon.material_index = index
    obj["urban_quality_version"] = VERSION
    return obj


def line_for_way(way, nodes):
    result = []
    for node_id in way.get("nodes") or []:
        node = nodes.get(str(node_id))
        if node is not None:
            x, y = node["xy"]
            result.append((float(x), float(y)))
    return result


def heading(tags, token: str) -> float:
    raw = str(tags.get("direction") or "").strip()
    try:
        return math.radians(float(raw))
    except Exception:
        return stable_unit(token, 0) * math.tau


def local_xy(
    x: float,
    y: float,
    angle: float,
    forward: float = 0.0,
    side: float = 0.0,
) -> tuple[float, float]:
    return (
        x + math.cos(angle) * forward - math.sin(angle) * side,
        y + math.sin(angle) * forward + math.cos(angle) * side,
    )


def parse_lanes(tags) -> float:
    try:
        return float(tags.get("lanes") or 0.0)
    except Exception:
        return 0.0


def add_curbs(nodes, ways, terrain, materials):
    vertices = []
    faces = []
    indices = []
    segment_count = 0

    for way in ways:
        tags = way.get("tags") or {}
        if "highway" not in tags:
            continue
        line = line_for_way(way, nodes)
        if len(line) < 2:
            continue
        road_width = mos_core.highway_width_m(tags)
        parking = mos_ui.parse_parking_lanes(tags)
        sidewalks = mos_ui.parse_sidewalks(tags)

        for side in sidewalks:
            sign = 1.0 if side == "left" else -1.0
            parking_width = float((parking.get(side) or {}).get("width", 0.0))
            street_edge = sign * (road_width * 0.5 + parking_width + 0.18)
            for p0, p1 in zip(line[:-1], line[1:]):
                if add_segment_prism(
                    vertices,
                    faces,
                    indices,
                    p0=p0,
                    p1=p1,
                    offset=street_edge,
                    width=CURB_WIDTH,
                    base_height=0.025,
                    height=CURB_HEIGHT,
                    terrain=terrain,
                    material_index=0,
                ):
                    segment_count += 1

    obj = finalize("Urban_Curbs", vertices, faces, indices, materials)
    return obj, {
        "segments": segment_count,
        "vertices": len(vertices),
        "faces": len(faces),
    }


def point_on_polyline(line, distance: float):
    remaining = distance
    for p0, p1 in zip(line[:-1], line[1:]):
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        segment = math.hypot(dx, dy)
        if segment <= 1e-6:
            continue
        if remaining <= segment:
            t = remaining / segment
            return (
                p0[0] + dx * t,
                p0[1] + dy * t,
                math.atan2(dy, dx),
            )
        remaining -= segment
    if len(line) >= 2:
        p0, p1 = line[-2], line[-1]
        return p1[0], p1[1], math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    return None


def polyline_length(line) -> float:
    return sum(
        math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        for p0, p1 in zip(line[:-1], line[1:])
    )


def add_road_markings(nodes, ways, terrain, materials):
    vertices = []
    faces = []
    indices = []
    dash_count = 0
    way_count = 0

    marked_highways = {
        "trunk",
        "primary",
        "secondary",
        "tertiary",
        "trunk_link",
        "primary_link",
        "secondary_link",
        "tertiary_link",
    }

    for way in ways:
        tags = way.get("tags") or {}
        highway = str(tags.get("highway") or "").lower()
        if highway not in marked_highways:
            continue
        if str(tags.get("oneway") or "").lower() in {"yes", "1", "true"}:
            continue
        if parse_lanes(tags) == 1:
            continue

        line = line_for_way(way, nodes)
        total = polyline_length(line)
        if total < 12.0:
            continue

        way_count += 1
        distance = 2.0
        while distance + MARKING_DASH * 0.5 < total:
            point = point_on_polyline(line, distance)
            if point is None:
                break
            x, y, angle = point
            z = terrain.sample(x, y)
            if z is not None:
                add_box(
                    vertices,
                    faces,
                    indices,
                    x,
                    y,
                    z + 0.07,
                    MARKING_DASH,
                    MARKING_WIDTH,
                    0.014,
                    angle,
                    0,
                )
                dash_count += 1
            distance += MARKING_DASH + MARKING_GAP

    obj = finalize("Urban_RoadMarkings", vertices, faces, indices, materials)
    return obj, {
        "ways": way_count,
        "dashes": dash_count,
        "vertices": len(vertices),
        "faces": len(faces),
    }


def rebuild_fixtures(nodes, terrain, materials):
    old = bpy.data.objects.get("Urban_Fixtures")
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)

    vertices = []
    faces = []
    indices = []
    counts = {
        "street_lamps": 0,
        "benches": 0,
        "waste": 0,
        "bicycle_parking": 0,
        "traffic_signals": 0,
        "stop_signs": 0,
        "give_way_signs": 0,
    }

    for node_id, node in nodes.items():
        tags = node.get("tags") or {}
        x, y = map(float, node["xy"])
        z = terrain.sample(x, y)
        if z is None:
            continue
        angle = heading(tags, f"node:{node_id}")
        highway = str(tags.get("highway") or "").lower()
        amenity = str(tags.get("amenity") or "").lower()

        if highway == "street_lamp":
            # 12-sided tapered-looking pole, short outreach arm, luminaire and
            # a separate emissive underside. Slight deterministic variation
            # avoids a cloned-toy appearance while keeping exact OSM anchors.
            height = 5.1 + stable_unit(str(node_id), 1) * 0.65
            add_prism(vertices, faces, indices, x, y, z + 0.02, 0.072, height, 10, 0)
            arm_x, arm_y = local_xy(x, y, angle, forward=0.30)
            add_box(
                vertices,
                faces,
                indices,
                arm_x,
                arm_y,
                z + height - 0.02,
                0.72,
                0.085,
                0.085,
                angle,
                0,
            )
            head_x, head_y = local_xy(x, y, angle, forward=0.64)
            add_box(
                vertices,
                faces,
                indices,
                head_x,
                head_y,
                z + height - 0.09,
                0.46,
                0.20,
                0.14,
                angle,
                1,
            )
            add_box(
                vertices,
                faces,
                indices,
                head_x,
                head_y,
                z + height - 0.112,
                0.35,
                0.13,
                0.025,
                angle,
                2,
            )
            counts["street_lamps"] += 1

        elif amenity == "bench":
            # Four seat slats, three back slats and metal legs/supports.
            for side_offset in (-0.24, -0.08, 0.08, 0.24):
                sx, sy = local_xy(x, y, angle, side=side_offset)
                add_box(
                    vertices,
                    faces,
                    indices,
                    sx,
                    sy,
                    z + 0.44,
                    1.72,
                    0.11,
                    0.075,
                    angle,
                    3,
                )
            for h in (0.74, 0.93, 1.12):
                bx, by = local_xy(x, y, angle, side=0.31)
                add_box(
                    vertices,
                    faces,
                    indices,
                    bx,
                    by,
                    z + h,
                    1.72,
                    0.075,
                    0.12,
                    angle,
                    3,
                )
            for forward in (-0.58, 0.58):
                lx, ly = local_xy(x, y, angle, forward=forward)
                add_box(
                    vertices,
                    faces,
                    indices,
                    lx,
                    ly,
                    z + 0.04,
                    0.09,
                    0.40,
                    0.48,
                    angle,
                    0,
                )
                sx, sy = local_xy(lx, ly, angle, side=0.27)
                add_box(
                    vertices,
                    faces,
                    indices,
                    sx,
                    sy,
                    z + 0.45,
                    0.09,
                    0.09,
                    0.67,
                    angle,
                    0,
                )
            counts["benches"] += 1

        elif amenity in {"waste_basket", "waste_disposal", "recycling"}:
            if amenity == "waste_basket":
                add_prism(vertices, faces, indices, x, y, z + 0.03, 0.27, 0.78, 10, 4)
                add_prism(vertices, faces, indices, x, y, z + 0.80, 0.31, 0.10, 10, 0)
                opening_x, opening_y = local_xy(x, y, angle, forward=0.265)
                add_box(
                    vertices,
                    faces,
                    indices,
                    opening_x,
                    opening_y,
                    z + 0.58,
                    0.18,
                    0.035,
                    0.17,
                    angle,
                    5,
                )
            else:
                body_w = 0.92 if amenity == "recycling" else 1.05
                body_d = 0.70
                add_box(
                    vertices,
                    faces,
                    indices,
                    x,
                    y,
                    z + 0.03,
                    body_w,
                    body_d,
                    1.02,
                    angle,
                    4,
                )
                add_box(
                    vertices,
                    faces,
                    indices,
                    x,
                    y,
                    z + 1.05,
                    body_w + 0.06,
                    body_d + 0.06,
                    0.11,
                    angle,
                    6 if amenity == "recycling" else 0,
                )
            counts["waste"] += 1

        elif amenity == "bicycle_parking":
            # Three readable inverted-U racks instead of three isolated poles.
            for forward in (-0.70, 0.0, 0.70):
                rx, ry = local_xy(x, y, angle, forward=forward)
                for side_offset in (-0.30, 0.30):
                    px, py = local_xy(rx, ry, angle, side=side_offset)
                    add_prism(
                        vertices,
                        faces,
                        indices,
                        px,
                        py,
                        z + 0.025,
                        0.035,
                        0.80,
                        8,
                        0,
                    )
                add_box(
                    vertices,
                    faces,
                    indices,
                    rx,
                    ry,
                    z + 0.78,
                    0.08,
                    0.67,
                    0.08,
                    angle,
                    0,
                )
            counts["bicycle_parking"] += 1

        elif highway == "traffic_signals":
            add_prism(vertices, faces, indices, x, y, z + 0.02, 0.065, 3.35, 10, 0)
            head_x, head_y = local_xy(x, y, angle, forward=0.12)
            add_box(
                vertices,
                faces,
                indices,
                head_x,
                head_y,
                z + 2.48,
                0.30,
                0.26,
                0.98,
                angle,
                5,
            )
            for z0, material_index in ((3.20, 7), (2.91, 8), (2.62, 9)):
                pip_x, pip_y = local_xy(x, y, angle, forward=0.275)
                add_box(
                    vertices,
                    faces,
                    indices,
                    pip_x,
                    pip_y,
                    z + z0,
                    0.16,
                    0.045,
                    0.16,
                    angle,
                    material_index,
                )
            counts["traffic_signals"] += 1

        elif highway in {"stop", "give_way"}:
            add_prism(vertices, faces, indices, x, y, z + 0.02, 0.045, 2.25, 8, 0)
            if highway == "stop":
                # White slightly larger backing creates the readable border.
                add_vertical_plate(
                    vertices,
                    faces,
                    indices,
                    cx=x,
                    cy=y,
                    cz=z + 2.31,
                    radius=0.42,
                    thickness=0.055,
                    sides=8,
                    angle=angle,
                    material_index=10,
                    rotation=math.pi / 8.0,
                )
                fx, fy = local_xy(x, y, angle, forward=0.033)
                add_vertical_plate(
                    vertices,
                    faces,
                    indices,
                    cx=fx,
                    cy=fy,
                    cz=z + 2.31,
                    radius=0.37,
                    thickness=0.035,
                    sides=8,
                    angle=angle,
                    material_index=11,
                    rotation=math.pi / 8.0,
                )
                counts["stop_signs"] += 1
            else:
                add_vertical_plate(
                    vertices,
                    faces,
                    indices,
                    cx=x,
                    cy=y,
                    cz=z + 2.28,
                    radius=0.45,
                    thickness=0.055,
                    sides=3,
                    angle=angle,
                    material_index=11,
                    rotation=-math.pi / 2.0,
                )
                fx, fy = local_xy(x, y, angle, forward=0.033)
                add_vertical_plate(
                    vertices,
                    faces,
                    indices,
                    cx=fx,
                    cy=fy,
                    cz=z + 2.28,
                    radius=0.34,
                    thickness=0.035,
                    sides=3,
                    angle=angle,
                    material_index=10,
                    rotation=-math.pi / 2.0,
                )
                counts["give_way_signs"] += 1

    obj = finalize("Urban_Fixtures", vertices, faces, indices, materials)
    return obj, counts, {
        "vertices": len(vertices),
        "faces": len(faces),
    }


def point_at(camera, target):
    camera.rotation_euler = (
        Vector(target) - camera.location
    ).to_track_quat("-Z", "Y").to_euler()


def production_camera_signature(scene) -> str:
    camera = bpy.data.objects.get("Camera")
    if camera is None or camera.type != "CAMERA":
        raise RuntimeError("production Camera missing")
    original_frame = scene.frame_current
    checkpoints = []
    for frame in (1, 61, 121, 181, 241, 301, 360):
        scene.frame_set(frame)
        checkpoints.append(
            {
                "frame": frame,
                "location": [round(float(v), 6) for v in camera.location],
                "rotation": [round(float(v), 7) for v in camera.rotation_euler],
                "lens": round(float(camera.data.lens), 6),
                "dof": bool(camera.data.dof.use_dof),
                "focus_distance": round(float(camera.data.dof.focus_distance), 6),
                "fstop": round(float(camera.data.dof.aperture_fstop), 6),
            }
        )
    scene.frame_set(original_frame)
    payload = json.dumps(checkpoints, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def render_production_previews(scene):
    original_camera = scene.camera
    original_resolution = (
        scene.render.resolution_x,
        scene.render.resolution_y,
        scene.render.resolution_percentage,
    )
    paths = []
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"

    for frame in (1, 181, 360):
        scene.frame_set(frame)
        path = OUT / f"production-{frame:03d}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        paths.append(path.relative_to(ROOT).as_posix())

    scene.camera = original_camera
    (
        scene.render.resolution_x,
        scene.render.resolution_y,
        scene.render.resolution_percentage,
    ) = original_resolution
    return paths


def nearest_road_pose(anchor_xy, desired_target_xy, nodes, ways):
    ax, ay = anchor_xy
    desired = Vector((
        float(desired_target_xy[0]) - float(ax),
        float(desired_target_xy[1]) - float(ay),
    ))
    skip = {
        "footway", "path", "cycleway", "steps", "track",
        "construction", "proposed",
    }
    best = None

    for way in ways:
        tags = way.get("tags") or {}
        highway = str(tags.get("highway") or "").lower()
        if not highway or highway in skip:
            continue
        line = line_for_way(way, nodes)
        for p0, p1 in zip(line[:-1], line[1:]):
            x0, y0 = p0
            x1, y1 = p1
            dx = x1 - x0
            dy = y1 - y0
            length2 = dx * dx + dy * dy
            if length2 < 1e-6:
                continue
            t = ((ax - x0) * dx + (ay - y0) * dy) / length2
            t = max(0.0, min(1.0, t))
            px = x0 + dx * t
            py = y0 + dy * t
            distance2 = (px - ax) ** 2 + (py - ay) ** 2
            if best is None or distance2 < best["distance2"]:
                tangent = Vector((dx, dy))
                tangent.normalize()
                if desired.length > 1e-6 and tangent.dot(desired.normalized()) < 0.0:
                    tangent = -tangent
                best = {
                    "distance2": distance2,
                    "xy": (px, py),
                    "tangent": tangent,
                    "way_id": int(way.get("id") or 0),
                    "highway": highway,
                }
    return best


def render_qa_previews(scene, terrain, nodes, ways):
    original_camera = scene.camera
    original_frame = scene.frame_current
    original_resolution = (
        scene.render.resolution_x,
        scene.render.resolution_y,
        scene.render.resolution_percentage,
    )
    camera_data = bpy.data.cameras.new("QA_Street_Camera")
    camera = bpy.data.objects.new("QA_Street_Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.data.sensor_width = 36.0
    camera.data.dof.use_dof = False
    camera.data.clip_start = 0.18
    camera.data.clip_end = 3500.0

    # Street QA is an inspection render, not a production-lighting preview.
    # Add a temporary neutral sun so shadowed street furniture remains readable.
    fill_data = bpy.data.lights.new("QA_Street_Fill", type="SUN")
    fill_data.energy = 1.35
    fill_data.angle = math.radians(12.0)
    fill_data.color = (0.93, 0.96, 1.0)
    fill = bpy.data.objects.new("QA_Street_Fill", fill_data)
    bpy.context.collection.objects.link(fill)
    fill.rotation_euler = (
        math.radians(42.0),
        math.radians(-18.0),
        math.radians(-32.0),
    )

    scene.camera = camera
    scene.frame_set(181)
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"

    results = []
    for view in QA_VIEWS:
        pose = nearest_road_pose(
            view["location_xy"],
            view["target_xy"],
            nodes,
            ways,
        )
        if pose is None:
            results.append({"name": view["name"], "rendered": False})
            continue

        x, y = pose["xy"]
        tangent = pose["tangent"]
        z = terrain.sample(x, y)
        target_x = x + float(tangent.x) * 32.0
        target_y = y + float(tangent.y) * 32.0
        target_z = terrain.sample(target_x, target_y)
        if z is None:
            results.append({"name": view["name"], "rendered": False})
            continue
        if target_z is None:
            target_z = z

        # Put the camera just off the centreline so the lane itself and the
        # street edge both remain readable.  The lateral offset is small enough
        # to stay inside ordinary urban carriageways.
        side = Vector((-tangent.y, tangent.x))
        camera_x = x + float(side.x) * 0.85
        camera_y = y + float(side.y) * 0.85
        camera_z = terrain.sample(camera_x, camera_y)
        if camera_z is None:
            camera_x, camera_y, camera_z = x, y, z

        camera.location = (camera_x, camera_y, camera_z + 2.65)
        camera.data.lens = float(view["lens"])
        point_at(camera, (target_x, target_y, target_z + 1.55))
        path = OUT / f"street-{view['name']}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        results.append(
            {
                "name": view["name"],
                "rendered": True,
                "path": path.relative_to(ROOT).as_posix(),
                "location": [camera_x, camera_y, camera_z + 2.65],
                "target": [target_x, target_y, target_z + 1.55],
                "lens": float(view["lens"]),
                "road_way_id": pose["way_id"],
                "highway": pose["highway"],
                "anchor_distance_m": math.sqrt(float(pose["distance2"])),
            }
        )

    bpy.data.objects.remove(camera, do_unlink=True)
    bpy.data.objects.remove(fill, do_unlink=True)
    scene.camera = original_camera
    scene.frame_set(original_frame)
    (
        scene.render.resolution_x,
        scene.render.resolution_y,
        scene.render.resolution_percentage,
    ) = original_resolution
    return results


def main():
    for required in (BASE, OSM_LOCAL, TERRAIN):
        if not required.is_file():
            raise SystemExit(f"Missing input: {required}")

    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(BASE))
    camera_hash_before = production_camera_signature(bpy.context.scene)

    data = json.loads(OSM_LOCAL.read_text())
    nodes = data["nodes"]
    ways = data["ways"]
    terrain = TerrainSampler(TERRAIN)

    fixture_materials = [
        material("UrbanQ_Metal", (0.055, 0.065, 0.075, 1.0), 0.28, 0.72),
        material("UrbanQ_LampHousing", (0.12, 0.13, 0.14, 1.0), 0.32, 0.58),
        material(
            "UrbanQ_LampGlow",
            (0.95, 0.72, 0.30, 1.0),
            0.22,
            0.0,
            (1.0, 0.55, 0.16, 1.0),
            3.0,
        ),
        material("UrbanQ_Wood", (0.28, 0.105, 0.035, 1.0), 0.68),
        material("UrbanQ_Bin", (0.055, 0.12, 0.075, 1.0), 0.54, 0.12),
        material("UrbanQ_SignalDark", (0.018, 0.022, 0.024, 1.0), 0.32, 0.22),
        material("UrbanQ_RecycleLid", (0.05, 0.20, 0.30, 1.0), 0.42, 0.10),
        material(
            "UrbanQ_RedLight",
            (0.42, 0.006, 0.004, 1.0),
            0.24,
            0.0,
            (0.72, 0.006, 0.004, 1.0),
            1.8,
        ),
        material(
            "UrbanQ_AmberLight",
            (0.52, 0.16, 0.003, 1.0),
            0.24,
            0.0,
            (0.82, 0.20, 0.003, 1.0),
            1.8,
        ),
        material(
            "UrbanQ_GreenLight",
            (0.003, 0.26, 0.035, 1.0),
            0.24,
            0.0,
            (0.003, 0.55, 0.045, 1.0),
            1.8,
        ),
        material("UrbanQ_SignWhite", (0.88, 0.88, 0.84, 1.0), 0.40),
        material("UrbanQ_SignRed", (0.58, 0.018, 0.012, 1.0), 0.40),
    ]
    curb_materials = [
        material("UrbanQ_Curb", (0.32, 0.31, 0.29, 1.0), 0.86)
    ]
    marking_materials = [
        material("UrbanQ_RoadWhite", (0.83, 0.82, 0.74, 1.0), 0.62)
    ]

    fixture_obj, fixture_counts, fixture_geometry = rebuild_fixtures(
        nodes,
        terrain,
        fixture_materials,
    )
    curb_obj, curb_stats = add_curbs(nodes, ways, terrain, curb_materials)
    marking_obj, marking_stats = add_road_markings(
        nodes,
        ways,
        terrain,
        marking_materials,
    )

    for obj in (fixture_obj, curb_obj, marking_obj):
        if obj is not None:
            obj["source"] = "OpenStreetMap exact anchors + Coimbra 010 procedural quality"
            obj["mosaiq_semantics_commit"] = (
                "f73d030aecd3289007472a887d78aae2e74b6ea0"
            )

    scene = bpy.context.scene
    scene["city_urban_quality_version"] = VERSION
    scene["city_urban_quality_source"] = "OSM + MOSAIQ semantics + procedural Blender geometry"
    scene["city_urban_quality_curb_segments"] = int(curb_stats["segments"])
    scene["city_urban_quality_marking_dashes"] = int(marking_stats["dashes"])
    scene["city_urban_quality_fixture_count"] = int(sum(fixture_counts.values()))

    camera_hash_after = production_camera_signature(scene)
    if camera_hash_after != camera_hash_before:
        raise RuntimeError(
            "production camera changed during 010 preparation: "
            f"{camera_hash_before} != {camera_hash_after}"
        )

    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))

    production_previews = render_production_previews(scene)
    street_previews = render_qa_previews(scene, terrain, nodes, ways)

    result = {
        "version": VERSION,
        "base": BASE.relative_to(ROOT).as_posix(),
        "output": OUT_BLEND.relative_to(ROOT).as_posix(),
        "fixture_counts": fixture_counts,
        "fixture_geometry": fixture_geometry,
        "curbs": curb_stats,
        "road_markings": marking_stats,
        "production_previews": production_previews,
        "street_previews": street_previews,
        "protected_production_camera_unchanged": camera_hash_after == camera_hash_before,
        "production_camera_hash_before": camera_hash_before,
        "production_camera_hash_after": camera_hash_after,
        "notes": [
            "009D sidewalks, parking strips and crosswalks are preserved.",
            "Urban_Fixtures is rebuilt at the same exact OSM node anchors.",
            "Street QA cameras and neutral QA fill light are temporary render-only objects and are not saved in the output blend.",
            "No external GLB asset pack is required.",
        ],
    }
    MANIFEST.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
