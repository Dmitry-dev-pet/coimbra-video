from __future__ import annotations

import json
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "textures" / "COIMBRA-005-polyhaven.json"
DOWNLOAD_MANIFEST = ROOT / "data" / "textures" / "polyhaven" / "download-manifest.json"
BASE = ROOT / "bridge_output_003" / "coimbra-terrain-base.blend"
OUT_DIR = ROOT / "bridge_output_005"
OUT_BLEND = OUT_DIR / "coimbra-textured-base.blend"
TEXTURE_MANIFEST = OUT_DIR / "texture-manifest.json"


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

    normal_tex = nodes.new("ShaderNodeTexImage")
    normal_tex.image = image_for(asset, "normal", downloads)
    normal_tex.projection = "BOX"
    normal_tex.projection_blend = 0.18
    links.new(mapping.outputs["Vector"], normal_tex.inputs["Vector"])

    normal = nodes.new("ShaderNodeNormalMap")
    normal.inputs["Strength"].default_value = float(spec.get("normal_strength", 0.3))
    links.new(normal_tex.outputs["Color"], normal.inputs["Color"])
    links.new(normal.outputs["Normal"], bsdf.inputs["Normal"])

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
        "packed_images": packed,
        "all_file_images_packed": all(packed.values()) if packed else False,
    }
    TEXTURE_MANIFEST.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
