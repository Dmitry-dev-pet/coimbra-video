from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "bridge_output_006" / "coimbra-vegetation-visual-dev.blend"
OUT_DIR = ROOT / "bridge_output_007"
OUT_BLEND = OUT_DIR / "coimbra-details-base.blend"
MANIFEST = OUT_DIR / "details-manifest.json"

DETAIL_VERSION = "coimbra-miniature-details-v1"


def stable_unit(token: str, channel: int = 0) -> float:
    digest = hashlib.sha256(f"{token}:{channel}".encode()).digest()
    value = int.from_bytes(digest[:8], "big")
    return value / float((1 << 64) - 1)


def make_material(name, color, roughness=0.55, metallic=0.0, emission=None):
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.use_nodes = True
    material.diffuse_color = color
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        if emission is not None:
            if "Emission Color" in bsdf.inputs:
                bsdf.inputs["Emission Color"].default_value = emission
                bsdf.inputs["Emission Strength"].default_value = 0.18
            elif "Emission" in bsdf.inputs:
                bsdf.inputs["Emission"].default_value = emission
                bsdf.inputs["Emission Strength"].default_value = 0.18
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


def add_oriented_quad(vertices, faces, material_indices, center, axis_x, axis_y, size_x, size_y, material_index):
    axis_x = axis_x.normalized()
    axis_y = axis_y.normalized()
    hx = axis_x * (size_x * 0.5)
    hy = axis_y * (size_y * 0.5)
    base = len(vertices)
    vertices.extend(
        (
            tuple(center - hx - hy),
            tuple(center + hx - hy),
            tuple(center + hx + hy),
            tuple(center - hx + hy),
        )
    )
    faces.append((base, base + 1, base + 2, base + 3))
    material_indices.append(material_index)


def finalize_object(name, vertices, faces, material_indices, materials, metadata):
    if not faces:
        raise RuntimeError(f"{name} generated no geometry")
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    for material in materials:
        obj.data.materials.append(material)
    for polygon, material_index in zip(obj.data.polygons, material_indices):
        polygon.material_index = material_index
    for key, value in metadata.items():
        obj[key] = value
    return obj


def road_axes(polygon, mesh):
    coords = [mesh.vertices[index].co.copy() for index in polygon.vertices]
    if len(coords) != 4:
        return None
    edges = []
    for i in range(4):
        edge = coords[(i + 1) % 4] - coords[i]
        flat = Vector((edge.x, edge.y, 0.0))
        edges.append((flat.length, flat))
    edges.sort(key=lambda item: item[0], reverse=True)
    long_len, long_axis = edges[0]
    short_len, short_axis = edges[-1]
    if long_len < 2.5 or short_len < 0.5:
        return None
    return long_axis.normalized(), short_axis.normalized(), long_len, short_len


def build_cars():
    car_materials = [
        make_material("Detail_Car_Red", (0.42, 0.025, 0.018, 1.0), 0.34, 0.1),
        make_material("Detail_Car_Blue", (0.025, 0.09, 0.32, 1.0), 0.34, 0.1),
        make_material("Detail_Car_White", (0.72, 0.72, 0.68, 1.0), 0.38, 0.05),
        make_material("Detail_Car_Grey", (0.16, 0.17, 0.18, 1.0), 0.32, 0.25),
        make_material("Detail_Car_Yellow", (0.70, 0.38, 0.02, 1.0), 0.36, 0.05),
        make_material("Detail_Car_Green", (0.03, 0.22, 0.09, 1.0), 0.36, 0.08),
        make_material("Detail_Car_Window", (0.008, 0.015, 0.025, 1.0), 0.14, 0.18),
    ]

    vertices = []
    faces = []
    indices = []
    count = 0
    road_counts = {}

    thresholds = {
        "City_Roads_major": 0.16,
        "City_Roads_local": 0.085,
        "City_Roads_service": 0.025,
    }

    for object_name, threshold in thresholds.items():
        obj = bpy.data.objects.get(object_name)
        if obj is None or obj.type != "MESH":
            continue
        road_count = 0
        mesh = obj.data
        for polygon in mesh.polygons:
            token = f"{object_name}:{polygon.index}"
            if stable_unit(token, 0) >= threshold:
                continue
            axes = road_axes(polygon, mesh)
            if axes is None:
                continue
            axis_x, axis_y, long_len, short_len = axes
            if long_len < 4.5:
                continue

            center = polygon.center.copy()
            center.z = sum(mesh.vertices[i].co.z for i in polygon.vertices) / len(polygon.vertices)
            lane_sign = -1.0 if stable_unit(token, 1) < 0.5 else 1.0
            lane_offset = min(short_len * 0.18, 0.75) * lane_sign
            center += axis_y * lane_offset

            scale = 0.92 + stable_unit(token, 2) * 0.18
            car_length = 4.25 * scale
            car_width = min(1.85 * scale, short_len * 0.64)
            z0 = center.z + 0.05
            body_top = z0 + 1.05 * scale
            color_slot = int(stable_unit(token, 3) * 6.0) % 6

            add_box(
                vertices, faces, indices,
                center, axis_x, axis_y,
                car_length, car_width,
                z0, body_top,
                color_slot,
            )
            roof_center = center + axis_x * (car_length * 0.04)
            add_box(
                vertices, faces, indices,
                roof_center, axis_x, axis_y,
                car_length * 0.48, car_width * 0.78,
                body_top - 0.04, body_top + 0.48 * scale,
                6,
            )

            count += 1
            road_count += 1
        road_counts[object_name] = road_count

    obj = finalize_object(
        "Detail_Cars",
        vertices, faces, indices,
        car_materials,
        {
            "detail_version": DETAIL_VERSION,
            "detail_type": "cars",
            "instance_count": count,
        },
    )
    return {"object": obj.name, "count": count, "by_road": road_counts}


def roof_basis(polygon, mesh):
    if polygon.material_index < 5 or polygon.normal.z < 0.75:
        return None
    coords = [mesh.vertices[index].co.copy() for index in polygon.vertices]
    if len(coords) < 3:
        return None
    center = polygon.center.copy()
    candidate = None
    candidate_len = 0.0
    for i in range(len(coords)):
        edge = coords[(i + 1) % len(coords)] - coords[i]
        edge.z = 0.0
        if edge.length > candidate_len:
            candidate_len = edge.length
            candidate = edge
    if candidate is None or candidate_len < 2.5:
        return None
    axis_x = candidate.normalized()
    axis_y = Vector((-axis_x.y, axis_x.x, 0.0))
    radius = min((Vector((p.x, p.y, 0.0)) - Vector((center.x, center.y, 0.0))).length for p in coords)
    return center, axis_x, axis_y, radius


def build_rooftop_details():
    building = bpy.data.objects.get("City_Buildings")
    if building is None or building.type != "MESH":
        raise RuntimeError("City_Buildings mesh not found")
    mesh = building.data

    solar_materials = [
        make_material("Detail_Solar_Panel", (0.012, 0.045, 0.12, 1.0), 0.18, 0.15),
        make_material("Detail_Solar_Frame", (0.34, 0.36, 0.38, 1.0), 0.26, 0.55),
    ]
    roof_materials = [
        make_material("Detail_Roof_Vent", (0.46, 0.47, 0.44, 1.0), 0.62, 0.15),
        make_material("Detail_Chimney", (0.36, 0.18, 0.10, 1.0), 0.72, 0.0),
    ]

    sv, sf, si = [], [], []
    rv, rf, ri = [], [], []
    solar_roofs = 0
    panel_count = 0
    roof_fixture_count = 0

    for polygon in mesh.polygons:
        basis = roof_basis(polygon, mesh)
        if basis is None:
            continue
        center, axis_x, axis_y, radius = basis
        token = f"roof:{polygon.index}"

        if polygon.area >= 38.0 and radius >= 2.0 and stable_unit(token, 0) < 0.15:
            solar_roofs += 1
            cols = 2 + int(stable_unit(token, 1) * 2.0)
            rows = 1 + int(stable_unit(token, 2) * 2.0)
            spacing_x = 1.65
            spacing_y = 2.25
            max_cols = max(1, int((radius * 1.6) / spacing_x))
            max_rows = max(1, int((radius * 1.6) / spacing_y))
            cols = min(cols, max_cols)
            rows = min(rows, max_rows)
            for row in range(rows):
                for col in range(cols):
                    offset_x = (col - (cols - 1) / 2.0) * spacing_x
                    offset_y = (row - (rows - 1) / 2.0) * spacing_y
                    panel_center = center + axis_x * offset_x + axis_y * offset_y
                    panel_center.z += 0.16
                    add_box(
                        sv, sf, si,
                        panel_center, axis_x, axis_y,
                        1.38, 2.02,
                        panel_center.z - 0.055,
                        panel_center.z + 0.055,
                        0,
                    )
                    panel_count += 1

        fixture_probability = 0.30 if polygon.area >= 24.0 else 0.14
        if radius >= 1.0 and stable_unit(token, 3) < fixture_probability:
            fixture_count = 1 + (1 if polygon.area > 80.0 and stable_unit(token, 4) < 0.35 else 0)
            for idx in range(fixture_count):
                angle = stable_unit(token, 5 + idx) * math.tau
                distance = radius * (0.18 + stable_unit(token, 8 + idx) * 0.30)
                fixture_center = center + Vector((math.cos(angle), math.sin(angle), 0.0)) * distance
                fixture_center.z += 0.05
                is_chimney = stable_unit(token, 12 + idx) < 0.48
                if is_chimney:
                    size = 0.55 + stable_unit(token, 13 + idx) * 0.35
                    add_box(
                        rv, rf, ri,
                        fixture_center, axis_x, axis_y,
                        size, size,
                        fixture_center.z,
                        fixture_center.z + 1.1 + stable_unit(token, 14 + idx) * 0.7,
                        1,
                    )
                else:
                    size_x = 0.75 + stable_unit(token, 13 + idx) * 0.55
                    size_y = 0.65 + stable_unit(token, 14 + idx) * 0.45
                    add_box(
                        rv, rf, ri,
                        fixture_center, axis_x, axis_y,
                        size_x, size_y,
                        fixture_center.z,
                        fixture_center.z + 0.55 + stable_unit(token, 15 + idx) * 0.45,
                        0,
                    )
                roof_fixture_count += 1

    solar_obj = finalize_object(
        "Detail_Solar",
        sv, sf, si,
        solar_materials,
        {
            "detail_version": DETAIL_VERSION,
            "detail_type": "solar",
            "panel_count": panel_count,
            "roof_count": solar_roofs,
        },
    )
    roof_obj = finalize_object(
        "Detail_Rooftop",
        rv, rf, ri,
        roof_materials,
        {
            "detail_version": DETAIL_VERSION,
            "detail_type": "rooftop",
            "fixture_count": roof_fixture_count,
        },
    )
    return {
        "solar_object": solar_obj.name,
        "solar_roofs": solar_roofs,
        "solar_panels": panel_count,
        "rooftop_object": roof_obj.name,
        "rooftop_fixtures": roof_fixture_count,
    }


def build_hvac():
    building = bpy.data.objects.get("City_Buildings")
    if building is None or building.type != "MESH":
        raise RuntimeError("City_Buildings mesh not found")
    mesh = building.data

    materials = [
        make_material("Detail_HVAC_White", (0.70, 0.71, 0.68, 1.0), 0.68, 0.02),
        make_material("Detail_HVAC_Grille", (0.05, 0.055, 0.06, 1.0), 0.40, 0.25),
    ]
    vertices, faces, indices = [], [], []
    count = 0
    walls = 0

    for polygon in mesh.polygons:
        if polygon.material_index >= 5 or len(polygon.vertices) != 4 or abs(polygon.normal.z) > 0.25:
            continue
        token = f"wall:{polygon.index}"
        if stable_unit(token, 0) >= 0.028:
            continue

        coords = [mesh.vertices[index].co.copy() for index in polygon.vertices]
        coords.sort(key=lambda p: p.z)
        bottom = coords[:2]
        top = coords[2:]
        horizontal = bottom[1] - bottom[0]
        horizontal.z = 0.0
        length = horizontal.length
        bottom_z = (bottom[0].z + bottom[1].z) * 0.5
        top_z = (top[0].z + top[1].z) * 0.5
        height = top_z - bottom_z
        if length < 3.0 or height < 4.2:
            continue

        horizontal.normalize()
        outward = polygon.normal.copy()
        outward.z = 0.0
        if outward.length < 1e-8:
            continue
        outward.normalize()
        vertical = Vector((0.0, 0.0, 1.0))

        unit_count = 1 + (1 if length > 9.0 and stable_unit(token, 1) < 0.35 else 0)
        base_mid = (bottom[0] + bottom[1]) * 0.5
        for idx in range(unit_count):
            offset = (stable_unit(token, 2 + idx) - 0.5) * max(0.0, length - 2.0)
            z = bottom_z + min(height - 1.0, 2.5 + stable_unit(token, 5 + idx) * max(0.5, height - 3.4))
            center = base_mid + horizontal * offset + vertical * (z - bottom_z) + outward * 0.32

            add_box(
                vertices, faces, indices,
                center, horizontal, outward,
                1.0, 0.42,
                z - 0.36, z + 0.36,
                0,
            )
            front_center = center + outward * 0.225 + vertical * 0.01
            add_oriented_quad(
                vertices, faces, indices,
                front_center, horizontal, vertical,
                0.68, 0.46,
                1,
            )
            count += 1
        walls += 1

    obj = finalize_object(
        "Detail_HVAC",
        vertices, faces, indices,
        materials,
        {
            "detail_version": DETAIL_VERSION,
            "detail_type": "hvac",
            "unit_count": count,
            "wall_count": walls,
        },
    )
    return {"object": obj.name, "count": count, "walls": walls}


def main():
    if not BASE.is_file():
        raise SystemExit(f"Missing input: {BASE}")

    bpy.ops.wm.open_mainfile(filepath=str(BASE))

    cars = build_cars()
    rooftop = build_rooftop_details()
    hvac = build_hvac()

    scene = bpy.context.scene
    scene["city_detail_version"] = DETAIL_VERSION
    scene["city_car_count"] = int(cars["count"])
    scene["city_solar_panel_count"] = int(rooftop["solar_panels"])
    scene["city_rooftop_fixture_count"] = int(rooftop["rooftop_fixtures"])
    scene["city_hvac_count"] = int(hvac["count"])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))

    result = {
        "version": DETAIL_VERSION,
        "output_scene": OUT_BLEND.relative_to(ROOT).as_posix(),
        "cars": cars,
        "rooftop": rooftop,
        "hvac": hvac,
    }
    MANIFEST.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
