from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "bridge_output_007" / "coimbra-details-visual-dev.blend"
DETECTIONS = ROOT / "data" / "processed" / "bridge_cars_ortho_2025.json"
OUT_DIR = ROOT / "bridge_output_008a"
OUT_BLEND = OUT_DIR / "coimbra-car-reality-base.blend"
MANIFEST = OUT_DIR / "car-reality-manifest.json"

VERSION = "coimbra-car-reality-v1"


def make_material(name, color, roughness=0.35, metallic=0.08):
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.use_nodes = True
    material.diffuse_color = color
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
    return material


def add_box(vertices, faces, material_indices, center, axis_x, axis_y, size_x, size_y, z0, z1, material_index):
    axis_x = axis_x.normalized()
    axis_y = axis_y.normalized()
    hx = axis_x * (size_x * 0.5)
    hy = axis_y * (size_y * 0.5)
    base = len(vertices)
    for z in (z0, z1):
        p = Vector((center.x, center.y, z))
        vertices.extend(
            (
                tuple(p - hx - hy),
                tuple(p + hx - hy),
                tuple(p + hx + hy),
                tuple(p - hx + hy),
            )
        )
    faces.extend(
        (
            (base, base + 1, base + 2, base + 3),
            (base + 4, base + 7, base + 6, base + 5),
            (base, base + 4, base + 5, base + 1),
            (base + 1, base + 5, base + 6, base + 2),
            (base + 2, base + 6, base + 7, base + 3),
            (base + 3, base + 7, base + 4, base),
        )
    )
    material_indices.extend([material_index] * 6)


def ground_height(x: float, y: float, depsgraph):
    origin = Vector((x, y, 1000.0))
    direction = Vector((0.0, 0.0, -1.0))
    hit, location, _normal, _index, obj, _matrix = bpy.context.scene.ray_cast(
        depsgraph,
        origin,
        direction,
        distance=2000.0,
    )
    if not hit or obj is None:
        return None, "no-hit"
    name = obj.name
    if (
        name == "City_Buildings"
        or name.startswith("Facade_")
        or name.startswith("Vegetation_")
        or name.startswith("Detail_Solar")
        or name.startswith("Detail_Rooftop")
        or name.startswith("Detail_HVAC")
    ):
        return None, name
    return float(location.z), name


def main() -> None:
    if not BASE.is_file() or not DETECTIONS.is_file():
        raise SystemExit("Missing 007 baseline or car detections")

    bpy.ops.wm.open_mainfile(filepath=str(BASE))
    old = bpy.data.objects.get("Detail_Cars")
    if old is not None:
        old_mesh = old.data
        bpy.data.objects.remove(old, do_unlink=True)
        if old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)

    data = json.loads(DETECTIONS.read_text())
    depsgraph = bpy.context.evaluated_depsgraph_get()

    palette = [
        make_material("Detail_Car_Ortho_Red", (0.42, 0.025, 0.018, 1.0)),
        make_material("Detail_Car_Ortho_Blue", (0.025, 0.09, 0.32, 1.0)),
        make_material("Detail_Car_Ortho_White", (0.72, 0.72, 0.68, 1.0)),
        make_material("Detail_Car_Ortho_Grey", (0.16, 0.17, 0.18, 1.0), metallic=0.22),
        make_material("Detail_Car_Ortho_Yellow", (0.70, 0.38, 0.02, 1.0)),
        make_material("Detail_Car_Ortho_Green", (0.03, 0.22, 0.09, 1.0)),
        make_material("Detail_Car_Ortho_Window", (0.008, 0.015, 0.025, 1.0), roughness=0.14, metallic=0.18),
    ]

    vertices, faces, indices = [], [], []
    accepted = 0
    rejected = {}
    small_count = 0
    large_count = 0

    for detection in data["detections"]:
        x, y = map(float, detection["center_local"])
        z, surface = ground_height(x, y, depsgraph)
        if z is None:
            rejected[surface] = rejected.get(surface, 0) + 1
            continue

        angle = float(detection["angle_rad"])
        axis_x = Vector((math.cos(angle), math.sin(angle), 0.0))
        axis_y = Vector((-math.sin(angle), math.cos(angle), 0.0))

        class_name = detection["class"]
        if class_name == "small vehicle":
            length = min(5.6, max(3.4, float(detection["length_m"])))
            width = min(2.2, max(1.55, float(detection["width_m"])))
            height = 1.25
            small_count += 1
        else:
            length = min(10.5, max(5.2, float(detection["length_m"])))
            width = min(2.8, max(1.9, float(detection["width_m"])))
            height = 1.75
            large_count += 1

        center = Vector((x, y, z + 0.05))
        slot = int(detection["palette_slot"]) % 6
        add_box(
            vertices, faces, indices,
            center, axis_x, axis_y,
            length, width,
            center.z, center.z + height,
            slot,
        )
        roof_center = center + axis_x * (length * 0.03)
        add_box(
            vertices, faces, indices,
            roof_center, axis_x, axis_y,
            length * 0.48, width * 0.77,
            center.z + height - 0.06,
            center.z + height + (0.42 if class_name == "small vehicle" else 0.52),
            6,
        )
        accepted += 1

    if accepted == 0:
        raise RuntimeError("No ortho-detected cars survived scene placement")

    mesh = bpy.data.meshes.new("Detail_Cars_Ortho_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Detail_Cars_Ortho", mesh)
    bpy.context.collection.objects.link(obj)
    for material in palette:
        obj.data.materials.append(material)
    for polygon, material_index in zip(obj.data.polygons, indices):
        polygon.material_index = material_index

    obj["detail_version"] = VERSION
    obj["detail_type"] = "cars-from-ortho"
    obj["detector"] = data["detector"]
    obj["vehicle_count"] = accepted

    scene = bpy.context.scene
    scene["city_car_source"] = "DGT Orthophotos 2025 + DOTAv1 OBB detector"
    scene["city_car_detector"] = str(data["detector"])
    scene["city_car_version"] = VERSION
    scene["city_car_detected_count"] = int(accepted)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))

    result = {
        "version": VERSION,
        "source": scene["city_car_source"],
        "detector": data["detector"],
        "raw_detection_count": int(data["total"]),
        "accepted_count": accepted,
        "small_vehicle_count": small_count,
        "large_vehicle_count": large_count,
        "rejected": rejected,
        "output_scene": OUT_BLEND.relative_to(ROOT).as_posix(),
    }
    MANIFEST.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
