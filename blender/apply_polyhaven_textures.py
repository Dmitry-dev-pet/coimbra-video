from __future__ import annotations

import json
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "textures" / "COIMBRA-005-polyhaven.json"
DOWNLOAD_MANIFEST = ROOT / "data" / "textures" / "polyhaven" / "download-manifest.json"
BASE = ROOT / "bridge_output_004" / "coimbra-visual-dev.blend"
OUT_DIR = ROOT / "bridge_output_005"
OUT_BLEND = OUT_DIR / "coimbra-textured-base.blend"
TEXTURE_MANIFEST = OUT_DIR / "texture-manifest.json"


ROAD_OBJECT_PREFIX = "City_Roads_"


def _flat_ribbon_geometry(obj):
    half_width = float(obj.data.bevel_depth)
    vertices = []
    faces = []
    spline_count = 0

    for spline in obj.data.splines:
        if spline.type != "POLY":
            continue

        points = [
            obj.matrix_world @ point.co.to_3d()
            for point in spline.points
        ]
        if len(points) < 2:
            continue

        spline_count += 1
        start = len(vertices)
        for index, point in enumerate(points):
            if index == 0:
                tangent = points[1] - points[0]
            elif index == len(points) - 1:
                tangent = points[-1] - points[-2]
            else:
                tangent = points[index + 1] - points[index - 1]

            tangent.z = 0.0
            if tangent.length < 1e-8:
                tangent = Vector((1.0, 0.0, 0.0))
            else:
                tangent.normalize()

            normal = Vector((-tangent.y, tangent.x, 0.0))
            left = point + normal * half_width
            right = point - normal * half_width
            vertices.extend((tuple(left), tuple(right)))

        for index in range(len(points) - 1):
            a = start + index * 2
            b = a + 1
            c = a + 3
            d = a + 2
            faces.append((a, b, c, d))

    return vertices, faces, half_width, spline_count


def recalculate_building_normals() -> dict:
    obj = bpy.data.objects.get("City_Buildings")
    if obj is None or obj.type != "MESH":
        raise RuntimeError("City_Buildings mesh not found")

    mesh = obj.data
    before_polygons = len(mesh.polygons)
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()

    return {
        "object": obj.name,
        "polygons": before_polygons,
        "mode": "recalculate_outside",
    }


def _window_materials():
    def make_principled(name, base_color, roughness, emission_color=None, emission_strength=0.0):
        material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        nodes.clear()

        output = nodes.new("ShaderNodeOutputMaterial")
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.inputs["Base Color"].default_value = base_color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = 0.08
        if "IOR" in bsdf.inputs:
            bsdf.inputs["IOR"].default_value = 1.45
        if emission_color is not None:
            if "Emission Color" in bsdf.inputs:
                bsdf.inputs["Emission Color"].default_value = emission_color
                bsdf.inputs["Emission Strength"].default_value = emission_strength
            elif "Emission" in bsdf.inputs:
                bsdf.inputs["Emission"].default_value = emission_color
                bsdf.inputs["Emission Strength"].default_value = emission_strength

        links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
        return material

    dark = make_principled(
        "Facade_Window_Dark",
        (0.012, 0.022, 0.032, 1.0),
        0.18,
    )
    warm = make_principled(
        "Facade_Window_Warm",
        (0.18, 0.075, 0.025, 1.0),
        0.28,
        emission_color=(1.0, 0.22, 0.035, 1.0),
        emission_strength=0.35,
    )
    return dark, warm


def add_facade_windows() -> dict:
    building = bpy.data.objects.get("City_Buildings")
    if building is None or building.type != "MESH":
        raise RuntimeError("City_Buildings mesh not found")

    dark, warm = _window_materials()
    source_mesh = building.data
    vertices = []
    faces = []
    material_indices = []
    wall_faces = 0
    skipped_faces = 0

    for polygon_index, polygon in enumerate(source_mesh.polygons):
        if len(polygon.vertices) != 4 or abs(float(polygon.normal.z)) > 0.25:
            continue
        # Roof slots start after the five generated wall materials.
        if polygon.material_index >= 5:
            continue

        coords = [source_mesh.vertices[index].co.copy() for index in polygon.vertices]
        coords.sort(key=lambda point: point.z)
        bottom = coords[:2]
        top = coords[2:]

        a, b = bottom
        horizontal = b - a
        horizontal.z = 0.0
        length = horizontal.length
        bottom_z = (bottom[0].z + bottom[1].z) * 0.5
        top_z = (top[0].z + top[1].z) * 0.5
        height = top_z - bottom_z

        if length < 2.2 or height < 2.6:
            skipped_faces += 1
            continue

        horizontal.normalize()
        outward = polygon.normal.copy()
        outward.z = 0.0
        if outward.length < 1e-8:
            skipped_faces += 1
            continue
        outward.normalize()

        floor_count = max(1, min(8, int(height / 3.0)))
        column_count = max(1, min(8, int(length / 3.2)))
        floor_height = height / floor_count
        bay_width = length / column_count
        window_width = min(1.35, bay_width * 0.54)
        window_height = min(1.45, floor_height * 0.48)

        wall_faces += 1
        for floor in range(floor_count):
            center_z = bottom_z + floor_height * (floor + 0.58)
            for column in range(column_count):
                distance = bay_width * (column + 0.5)
                # Anchor at the midpoint of the lower wall edge so small terrain
                # height differences at corners do not shear the facade grid.
                base_mid = (bottom[0] + bottom[1]) * 0.5
                center = (
                    base_mid
                    + horizontal * (distance - length * 0.5)
                    + Vector((0.0, 0.0, center_z - bottom_z))
                    + outward * 0.055
                )

                half_w = horizontal * (window_width * 0.5)
                half_h = Vector((0.0, 0.0, window_height * 0.5))
                start = len(vertices)
                vertices.extend(
                    (
                        tuple(center - half_w - half_h),
                        tuple(center + half_w - half_h),
                        tuple(center + half_w + half_h),
                        tuple(center - half_w + half_h),
                    )
                )
                faces.append((start, start + 1, start + 2, start + 3))

                token = (polygon_index * 131 + floor * 17 + column * 29) % 100
                material_indices.append(1 if token < 7 else 0)

    if not faces:
        raise RuntimeError("Facade window generation produced no geometry")

    mesh = bpy.data.meshes.new("Facade_Windows_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()

    windows = bpy.data.objects.new("Facade_Windows", mesh)
    bpy.context.collection.objects.link(windows)
    windows.data.materials.append(dark)
    windows.data.materials.append(warm)
    for polygon, material_index in zip(windows.data.polygons, material_indices):
        polygon.material_index = material_index

    windows["source"] = "procedural from City_Buildings wall quads"
    windows["facade_version"] = "coimbra-facade-windows-v1"
    windows["window_count"] = len(faces)

    return {
        "object": windows.name,
        "wall_faces": wall_faces,
        "skipped_faces": skipped_faces,
        "window_count": len(faces),
        "dark_windows": material_indices.count(0),
        "warm_windows": material_indices.count(1),
    }


def flatten_road_curves() -> dict:
    converted = {}

    for obj in list(bpy.data.objects):
        if not obj.name.startswith(ROAD_OBJECT_PREFIX) or obj.type != "CURVE":
            continue

        vertices, faces, half_width, spline_count = _flat_ribbon_geometry(obj)
        if not vertices or not faces:
            raise RuntimeError(f"Road curve has no usable polyline geometry: {obj.name}")

        old_name = obj.name
        old_curve = obj.data
        old_props = {key: obj[key] for key in obj.keys()}
        old_materials = list(old_curve.materials)

        mesh = bpy.data.meshes.new(f"{old_name}_FlatMesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()

        flat = bpy.data.objects.new(f"{old_name}_Flat", mesh)
        bpy.context.collection.objects.link(flat)
        for material in old_materials:
            flat.data.materials.append(material)
        for key, value in old_props.items():
            flat[key] = value

        flat["road_geometry"] = "flat-ribbon"
        flat["road_half_width_m"] = half_width
        flat["road_spline_count"] = spline_count

        bpy.data.objects.remove(obj, do_unlink=True)
        if old_curve.users == 0:
            bpy.data.curves.remove(old_curve)
        flat.name = old_name

        converted[old_name] = {
            "half_width_m": half_width,
            "full_width_m": half_width * 2.0,
            "splines": spline_count,
            "vertices": len(vertices),
            "faces": len(faces),
        }

    if not converted:
        raise RuntimeError("No City_Roads_* curve objects were converted")

    return converted


def image_for(asset: str, role: str, downloads: dict):
    relative = downloads["assets"][asset][role]["path"]
    image = bpy.data.images.load(str(ROOT / relative), check_existing=True)
    if role != "diffuse":
        image.colorspace_settings.name = "Non-Color"
    return image


def rebuild_material(material, spec: dict, downloads: dict):
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    texcoord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")

    scale = float(spec.get("scale", 1.0))
    mapping.inputs["Scale"].default_value = (scale, scale, scale)
    links.new(texcoord.outputs["Object"], mapping.inputs["Vector"])

    asset = spec["asset"]
    diffuse = nodes.new("ShaderNodeTexImage")
    diffuse.image = image_for(asset, "diffuse", downloads)
    diffuse.projection = "BOX"
    diffuse.projection_blend = 0.18
    links.new(mapping.outputs["Vector"], diffuse.inputs["Vector"])

    tint = spec.get("tint")
    if tint:
        mix = nodes.new("ShaderNodeMixRGB")
        mix.blend_type = "MULTIPLY"
        mix.inputs["Fac"].default_value = 1.0
        mix.inputs[2].default_value = tint
        links.new(diffuse.outputs["Color"], mix.inputs[1])
        links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        links.new(diffuse.outputs["Color"], bsdf.inputs["Base Color"])

    rough = nodes.new("ShaderNodeTexImage")
    rough.image = image_for(asset, "rough", downloads)
    rough.projection = "BOX"
    rough.projection_blend = 0.18
    links.new(mapping.outputs["Vector"], rough.inputs["Vector"])
    links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])

    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    material["polyhaven_asset"] = asset
    material["polyhaven_license"] = "CC0"
    material["polyhaven_resolution"] = "1k"


def main() -> None:
    if not BASE.is_file():
        raise SystemExit(f"Missing base scene: {BASE}")
    if not DOWNLOAD_MANIFEST.is_file():
        raise SystemExit(f"Missing downloaded texture manifest: {DOWNLOAD_MANIFEST}")

    plan = json.loads(PLAN_PATH.read_text())
    downloads = json.loads(DOWNLOAD_MANIFEST.read_text())
    bpy.ops.wm.open_mainfile(filepath=str(BASE))
    building_normals = recalculate_building_normals()
    facade_windows = add_facade_windows()
    flattened_roads = flatten_road_curves()

    applied = {}
    for material_name, spec in plan["materials"].items():
        material = bpy.data.materials.get(material_name)
        if material is None:
            raise RuntimeError(f"Material not found in Coimbra base: {material_name}")
        rebuild_material(material, spec, downloads)
        applied[material_name] = spec

    scene = bpy.context.scene
    scene["city_pbr_provider"] = plan["provider"]
    scene["city_pbr_license"] = plan["license"]
    scene["city_pbr_plan"] = plan["id"]
    scene["city_pbr_resolution"] = plan["resolution"]
    scene["city_facade_version"] = "coimbra-facade-windows-v1"
    scene["city_facade_window_count"] = int(facade_windows["window_count"])

    bpy.ops.file.pack_all()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))

    packed = {
        image.name: bool(image.packed_file)
        for image in bpy.data.images
        if image.source == "FILE"
    }
    result = {
        "plan": plan["id"],
        "provider": plan["provider"],
        "license": plan["license"],
        "resolution": plan["resolution"],
        "output_scene": OUT_BLEND.relative_to(ROOT).as_posix(),
        "materials": applied,
        "building_normals": building_normals,
        "facade_windows": facade_windows,
        "flattened_roads": flattened_roads,
        "packed_images": packed,
        "all_file_images_packed": all(packed.values()) if packed else False,
    }
    TEXTURE_MANIFEST.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
