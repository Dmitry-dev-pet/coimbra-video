from __future__ import annotations

import json
from pathlib import Path

import bpy
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
        "flattened_roads": flattened_roads,
        "packed_images": packed,
        "all_file_images_packed": all(packed.values()) if packed else False,
    }
    TEXTURE_MANIFEST.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
