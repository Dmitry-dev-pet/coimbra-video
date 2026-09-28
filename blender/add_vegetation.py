from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "bridge_output_005" / "coimbra-textures-visual-dev.blend"
TERRAIN = ROOT / "data" / "processed" / "bridge_terrain_6m.npz"
VEGETATION = ROOT / "data" / "processed" / "bridge_vegetation_local.json"
OUT_DIR = ROOT / "bridge_output_006"
OUT_BLEND = OUT_DIR / "coimbra-vegetation-base.blend"
MANIFEST = OUT_DIR / "vegetation-manifest.json"

MAX_TREES = 3800
MIN_TREE_DISTANCE = 4.5


def terrain_sampler():
    terrain = np.load(TERRAIN)
    z = terrain["z"]
    xs = terrain["xs"]
    ys = terrain["ys"]
    z0 = float(terrain["z0"])
    x0, x1 = float(xs[0]), float(xs[-1])
    y0, y1 = float(ys[0]), float(ys[-1])
    width = z.shape[1]
    height = z.shape[0]

    def sample(x: float, y: float):
        if x < min(x0, x1) or x > max(x0, x1) or y < min(y0, y1) or y > max(y0, y1):
            return None
        c = int(round((float(x) - x0) / (x1 - x0) * (width - 1)))
        r = int(round((y0 - float(y)) / (y0 - y1) * (height - 1)))
        c = max(0, min(width - 1, c))
        r = max(0, min(height - 1, r))
        return float(z[r, c] - z0)

    return sample


def stable_unit(token: str, channel: int = 0) -> float:
    digest = hashlib.sha256(f"{token}:{channel}".encode()).digest()
    value = int.from_bytes(digest[:8], "big")
    return value / float((1 << 64) - 1)


def tree_material(name: str, color: tuple[float, float, float, float], roughness: float):
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
    material.diffuse_color = color
    return material


def add_prism(
    vertices,
    faces,
    material_indices,
    *,
    center: Vector,
    radius: float,
    z0: float,
    z1: float,
    sides: int,
    material_index: int,
    rotation: float,
):
    start = len(vertices)
    for ring_z in (z0, z1):
        for i in range(sides):
            angle = rotation + (2.0 * math.pi * i / sides)
            vertices.append(
                (
                    center.x + math.cos(angle) * radius,
                    center.y + math.sin(angle) * radius,
                    ring_z,
                )
            )

    for i in range(sides):
        j = (i + 1) % sides
        faces.append((start + i, start + j, start + sides + j, start + sides + i))
        material_indices.append(material_index)


def add_crown(
    vertices,
    faces,
    material_indices,
    *,
    center: Vector,
    base_z: float,
    height: float,
    radius: float,
    sides: int,
    material_index: int,
    rotation: float,
    variant: int,
):
    start = len(vertices)
    if variant == 0:
        # Broad low-poly ellipsoid: bottom point, two rings, top point.
        vertices.append((center.x, center.y, base_z))
        for frac, scale in ((0.35, 1.0), (0.72, 0.82)):
            z = base_z + height * frac
            for i in range(sides):
                angle = rotation + 2.0 * math.pi * i / sides
                vertices.append(
                    (
                        center.x + math.cos(angle) * radius * scale,
                        center.y + math.sin(angle) * radius * scale,
                        z,
                    )
                )
        top_index = len(vertices)
        vertices.append((center.x, center.y, base_z + height))

        ring1 = start + 1
        ring2 = ring1 + sides
        bottom = start
        for i in range(sides):
            j = (i + 1) % sides
            faces.append((bottom, ring1 + j, ring1 + i))
            material_indices.append(material_index)
            faces.append((ring1 + i, ring1 + j, ring2 + j, ring2 + i))
            material_indices.append(material_index)
            faces.append((ring2 + i, ring2 + j, top_index))
            material_indices.append(material_index)
    else:
        # Taller conifer-like crown.
        base_start = start
        for i in range(sides):
            angle = rotation + 2.0 * math.pi * i / sides
            vertices.append(
                (
                    center.x + math.cos(angle) * radius,
                    center.y + math.sin(angle) * radius,
                    base_z,
                )
            )
        top_index = len(vertices)
        vertices.append((center.x, center.y, base_z + height))
        for i in range(sides):
            j = (i + 1) % sides
            faces.append((base_start + i, base_start + j, top_index))
            material_indices.append(material_index)


def blocked_by_scene(x: float, y: float, depsgraph) -> tuple[bool, str | None]:
    origin = Vector((x, y, 1000.0))
    direction = Vector((0.0, 0.0, -1.0))
    hit, _location, _normal, _index, obj, _matrix = bpy.context.scene.ray_cast(
        depsgraph,
        origin,
        direction,
        distance=2000.0,
    )
    if not hit or obj is None:
        return False, None
    name = obj.name
    blocked = (
        name == "City_Buildings"
        or name.startswith("Facade_")
        or name.startswith("City_Roads_")
    )
    return blocked, name if blocked else None


def collect_tree_points(data: dict):
    points = []
    occupied = set()
    cell = MIN_TREE_DISTANCE

    def admit(x: float, y: float, token: str, source: str, kind: str | None):
        key = (int(round(x / cell)), int(round(y / cell)))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if (key[0] + dx, key[1] + dy) in occupied:
                    return
        occupied.add(key)
        points.append(
            {
                "x": float(x),
                "y": float(y),
                "token": token,
                "source": source,
                "kind": kind,
            }
        )

    for item in data.get("exact_tree_nodes", []):
        x, y = item["xy"]
        admit(x, y, f"node:{item['id']}", "natural=tree", item.get("species") or item.get("genus"))

    for item in data.get("sampled_green_points", []):
        if len(points) >= MAX_TREES:
            break
        x, y = item["xy"]
        admit(x, y, f"way:{item['way_id']}:{x:.2f}:{y:.2f}", "green-area", item.get("kind"))

    return points[:MAX_TREES]


def main():
    for required in (BASE, TERRAIN, VEGETATION):
        if not required.is_file():
            raise SystemExit(f"Missing input: {required}")

    bpy.ops.wm.open_mainfile(filepath=str(BASE))
    data = json.loads(VEGETATION.read_text())
    sample_height = terrain_sampler()
    points = collect_tree_points(data)

    vertices = []
    faces = []
    material_indices = []
    accepted = []
    counts = {"natural=tree": 0, "green-area": 0}
    obstacle_skips = {"City_Buildings": 0, "Facade": 0, "City_Roads": 0}
    depsgraph = bpy.context.evaluated_depsgraph_get()

    for item in points:
        z = sample_height(item["x"], item["y"])
        if z is None:
            continue

        blocked, blocker = blocked_by_scene(item["x"], item["y"], depsgraph)
        if blocked:
            if blocker == "City_Buildings":
                obstacle_skips["City_Buildings"] += 1
            elif blocker and blocker.startswith("Facade_"):
                obstacle_skips["Facade"] += 1
            elif blocker and blocker.startswith("City_Roads_"):
                obstacle_skips["City_Roads"] += 1
            continue

        u0 = stable_unit(item["token"], 0)
        u1 = stable_unit(item["token"], 1)
        u2 = stable_unit(item["token"], 2)
        u3 = stable_unit(item["token"], 3)

        is_conifer = (
            "conifer" in str(item.get("kind") or "").lower()
            or u3 < 0.12
        )
        total_height = 5.0 + u0 * 8.0
        if item["source"] == "green-area":
            total_height *= 0.82 + u1 * 0.22

        trunk_height = total_height * (0.30 if not is_conifer else 0.22)
        trunk_radius = 0.13 + total_height * 0.018
        crown_height = total_height - trunk_height * 0.65
        crown_radius = total_height * (0.30 if not is_conifer else 0.21)
        rotation = u2 * math.tau

        center = Vector((item["x"], item["y"], z))
        add_prism(
            vertices,
            faces,
            material_indices,
            center=center,
            radius=trunk_radius,
            z0=z + 0.05,
            z1=z + trunk_height,
            sides=6,
            material_index=0,
            rotation=rotation,
        )
        crown_slot = 1 + int(u3 * 3.0) % 3
        add_crown(
            vertices,
            faces,
            material_indices,
            center=center,
            base_z=z + trunk_height * 0.65,
            height=crown_height,
            radius=crown_radius,
            sides=8,
            material_index=crown_slot,
            rotation=rotation,
            variant=1 if is_conifer else 0,
        )

        counts[item["source"]] += 1
        accepted.append(
            {
                "source": item["source"],
                "kind": item.get("kind"),
                "location": [item["x"], item["y"], z],
                "height": total_height,
                "conifer": is_conifer,
            }
        )

    if not accepted:
        raise RuntimeError("Vegetation generation produced no trees")

    mesh = bpy.data.meshes.new("Vegetation_Trees_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()

    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()

    trees = bpy.data.objects.new("Vegetation_Trees", mesh)
    bpy.context.collection.objects.link(trees)

    materials = [
        tree_material("Vegetation_Trunk", (0.16, 0.08, 0.03, 1.0), 0.88),
        tree_material("Vegetation_Leaves_A", (0.05, 0.22, 0.055, 1.0), 0.92),
        tree_material("Vegetation_Leaves_B", (0.09, 0.32, 0.07, 1.0), 0.90),
        tree_material("Vegetation_Leaves_C", (0.17, 0.36, 0.08, 1.0), 0.90),
    ]
    for material in materials:
        trees.data.materials.append(material)
    for polygon, material_index in zip(trees.data.polygons, material_indices):
        polygon.material_index = material_index
        polygon.use_smooth = material_index != 0

    trees["source"] = "OpenStreetMap + deterministic green-area sampling"
    trees["vegetation_version"] = "coimbra-vegetation-v2"
    trees["tree_count"] = len(accepted)

    scene = bpy.context.scene
    scene["city_vegetation_source"] = "OpenStreetMap natural=tree + green areas"
    scene["city_vegetation_license"] = "ODbL"
    scene["city_vegetation_version"] = "coimbra-vegetation-v2"
    scene["city_tree_count"] = len(accepted)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))

    result = {
        "source": scene["city_vegetation_source"],
        "license": scene["city_vegetation_license"],
        "version": scene["city_vegetation_version"],
        "output_scene": OUT_BLEND.relative_to(ROOT).as_posix(),
        "tree_count": len(accepted),
        "source_counts": counts,
        "obstacle_skips": obstacle_skips,
        "mesh": {
            "vertices": len(vertices),
            "faces": len(faces),
        },
        "osm_counts": data.get("counts", {}),
    }
    MANIFEST.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
