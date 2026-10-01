from __future__ import annotations

import hashlib
import shutil
import json
import math
from pathlib import Path
import sys
import time

import bpy
import bmesh
import numpy as np
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))

import build_dgt_terrain_scene as terrain_builder

CONFIG = ROOT / "config" / "coimbra_v2_001.json"
SOURCE_MANIFEST = ROOT / "bridge_output_v2_001" / "photogrammetry" / "source-manifest.json"
REGISTRATION = ROOT / "bridge_output_v2_001" / "registration" / "registration.json"
INSPECTION = ROOT / "bridge_output_v2_001" / "registration" / "photogrammetry-inspection.json"
DGT_ROOT = ROOT / "bridge_output_v2_001" / "dgt"
ORTHO = DGT_ROOT / "ortho" / "coimbra-v2-001-ortho-2025.jpg"
TERRAIN = DGT_ROOT / "prepared" / "coimbra-v2-001-terrain-2m.npz"
OUT = ROOT / "bridge_output_v2_001" / "hero"
IMAGE = OUT / "coimbra-v2-001-hero.png"
MANIFEST = OUT / "hero-manifest.json"
ATTRIBUTION = OUT / "ATTRIBUTION.txt"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def look_at(obj, target) -> None:
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def configure_metal(scene) -> list[str]:
    addon = bpy.context.preferences.addons.get("cycles")
    if addon is None:
        raise RuntimeError("Cycles addon unavailable")
    prefs = addon.preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()
    names = []
    for device in prefs.devices:
        device.use = device.type == "METAL"
        if device.use:
            names.append(device.name)
    if not names:
        raise RuntimeError("No Cycles METAL device detected")
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    return names


def import_photogrammetry(model: Path, registration: dict):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(model))
    imported = [obj for obj in bpy.context.scene.objects if obj not in before]
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("V2 photogrammetry import has no meshes")

    root = bpy.data.objects.new("V2_001_Photogrammetry_Root", None)
    bpy.context.collection.objects.link(root)
    for obj in imported:
        if obj.parent is None:
            obj.parent = root

    scale = float(registration["scale"])
    root.scale = (scale, scale, scale)
    root.rotation_euler[2] = float(registration["rotation_z_radians"])
    tx, ty = registration["translation_local_xy_m"]
    root.location = (
        float(tx),
        float(ty),
        float(registration["translation_local_z_m"]),
    )
    root["source"] = "Sketchfab VirtualPhoto3D Coimbra photogrammetry"
    root["license"] = "CC Attribution"
    return root, meshes


def cull_near_vertical_photogrammetry_faces(
    meshes,
    max_abs_normal_z: float = 0.15,
) -> dict:
    total_faces = 0
    removed_faces = 0
    affected_meshes = 0

    for obj in meshes:
        mesh = obj.data
        polygon_count = len(mesh.polygons)
        total_faces += polygon_count
        if polygon_count == 0:
            continue

        normals = np.empty(polygon_count * 3, dtype=np.float64)
        mesh.polygons.foreach_get("normal", normals)
        normals = normals.reshape((-1, 3))

        matrix = np.asarray(obj.matrix_world.to_3x3(), dtype=np.float64)
        world_normals = normals @ matrix.T
        lengths = np.linalg.norm(world_normals, axis=1)
        abs_nz = np.abs(
            world_normals[:, 2] / np.maximum(lengths, 1e-12)
        )
        remove_indices = np.flatnonzero(abs_nz < float(max_abs_normal_z))
        if remove_indices.size == 0:
            continue

        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.faces.ensure_lookup_table()
        delete_faces = [bm.faces[int(i)] for i in remove_indices]
        bmesh.ops.delete(bm, geom=delete_faces, context="FACES")
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()

        removed_faces += int(remove_indices.size)
        affected_meshes += 1

    receipt = {
        "max_abs_normal_z": float(max_abs_normal_z),
        "total_faces_before": int(total_faces),
        "removed_faces": int(removed_faces),
        "remaining_faces": int(total_faces - removed_faces),
        "affected_meshes": int(affected_meshes),
        "removed_fraction": (
            float(removed_faces / total_faces) if total_faces else 0.0
        ),
    }
    print("photogrammetry face cull:", json.dumps(receipt, sort_keys=True))
    return receipt


def apply_photogrammetry_surface_mask(
    root,
    meshes,
    inspection: dict,
    fade_m: float,
    slope_fade_start: float = 0.18,
    slope_fade_end: float = 0.62,
) -> None:
    bounds = inspection["bounds"]
    min_x, min_y = float(bounds["min"][0]), float(bounds["min"][1])
    max_x, max_y = float(bounds["max"][0]), float(bounds["max"][1])

    materials = {}
    for mesh in meshes:
        for slot in mesh.material_slots:
            if slot.material is not None:
                materials[slot.material.name_full] = slot.material

    for material in materials.values():
        material.use_nodes = True
        tree = material.node_tree
        output = next(
            (node for node in tree.nodes if node.type == "OUTPUT_MATERIAL" and node.is_active_output),
            None,
        )
        if output is None:
            continue
        surface = output.inputs.get("Surface")
        if surface is None or not surface.is_linked:
            continue

        source_socket = surface.links[0].from_socket
        tree.links.remove(surface.links[0])

        tex = tree.nodes.new("ShaderNodeTexCoord")
        tex.object = root
        separate = tree.nodes.new("ShaderNodeSeparateXYZ")
        tree.links.new(tex.outputs["Object"], separate.inputs["Vector"])

        distances = []
        for axis, bound, operation in (
            ("X", min_x, "SUBTRACT"),
            ("X", max_x, "SUBTRACT"),
            ("Y", min_y, "SUBTRACT"),
            ("Y", max_y, "SUBTRACT"),
        ):
            node = tree.nodes.new("ShaderNodeMath")
            node.operation = operation
            if bound in (min_x, min_y):
                tree.links.new(separate.outputs[axis], node.inputs[0])
                node.inputs[1].default_value = bound
            else:
                node.inputs[0].default_value = bound
                tree.links.new(separate.outputs[axis], node.inputs[1])
            distances.append(node)

        min_a = tree.nodes.new("ShaderNodeMath")
        min_a.operation = "MINIMUM"
        tree.links.new(distances[0].outputs[0], min_a.inputs[0])
        tree.links.new(distances[1].outputs[0], min_a.inputs[1])

        min_b = tree.nodes.new("ShaderNodeMath")
        min_b.operation = "MINIMUM"
        tree.links.new(distances[2].outputs[0], min_b.inputs[0])
        tree.links.new(distances[3].outputs[0], min_b.inputs[1])

        min_all = tree.nodes.new("ShaderNodeMath")
        min_all.operation = "MINIMUM"
        tree.links.new(min_a.outputs[0], min_all.inputs[0])
        tree.links.new(min_b.outputs[0], min_all.inputs[1])

        divide = tree.nodes.new("ShaderNodeMath")
        divide.operation = "DIVIDE"
        divide.inputs[1].default_value = float(fade_m)
        tree.links.new(min_all.outputs[0], divide.inputs[0])

        clamp_low = tree.nodes.new("ShaderNodeMath")
        clamp_low.operation = "MAXIMUM"
        clamp_low.inputs[1].default_value = 0.0
        tree.links.new(divide.outputs[0], clamp_low.inputs[0])

        clamp_high = tree.nodes.new("ShaderNodeMath")
        clamp_high.operation = "MINIMUM"
        clamp_high.inputs[1].default_value = 1.0
        tree.links.new(clamp_low.outputs[0], clamp_high.inputs[0])

        geometry = tree.nodes.new("ShaderNodeNewGeometry")
        normal_split = tree.nodes.new("ShaderNodeSeparateXYZ")
        tree.links.new(geometry.outputs["True Normal"], normal_split.inputs["Vector"])

        normal_abs = tree.nodes.new("ShaderNodeMath")
        normal_abs.operation = "ABSOLUTE"
        tree.links.new(normal_split.outputs["Z"], normal_abs.inputs[0])

        slope_sub = tree.nodes.new("ShaderNodeMath")
        slope_sub.operation = "SUBTRACT"
        slope_sub.inputs[1].default_value = float(slope_fade_start)
        tree.links.new(normal_abs.outputs[0], slope_sub.inputs[0])

        slope_div = tree.nodes.new("ShaderNodeMath")
        slope_div.operation = "DIVIDE"
        slope_div.inputs[1].default_value = float(
            max(1e-6, slope_fade_end - slope_fade_start)
        )
        tree.links.new(slope_sub.outputs[0], slope_div.inputs[0])

        slope_low = tree.nodes.new("ShaderNodeMath")
        slope_low.operation = "MAXIMUM"
        slope_low.inputs[1].default_value = 0.0
        tree.links.new(slope_div.outputs[0], slope_low.inputs[0])

        slope_high = tree.nodes.new("ShaderNodeMath")
        slope_high.operation = "MINIMUM"
        slope_high.inputs[1].default_value = 1.0
        tree.links.new(slope_low.outputs[0], slope_high.inputs[0])

        visibility = tree.nodes.new("ShaderNodeMath")
        visibility.operation = "MULTIPLY"
        tree.links.new(clamp_high.outputs[0], visibility.inputs[0])
        tree.links.new(slope_high.outputs[0], visibility.inputs[1])

        transparent = tree.nodes.new("ShaderNodeBsdfTransparent")
        mix = tree.nodes.new("ShaderNodeMixShader")
        tree.links.new(visibility.outputs[0], mix.inputs[0])
        tree.links.new(transparent.outputs[0], mix.inputs[1])
        tree.links.new(source_socket, mix.inputs[2])
        tree.links.new(mix.outputs[0], surface)


def main() -> None:
    for path in (CONFIG, SOURCE_MANIFEST, REGISTRATION, INSPECTION, ORTHO, TERRAIN):
        if not path.is_file():
            raise SystemExit(f"Missing V2-001 hero input: {path}")

    cfg = json.loads(CONFIG.read_text())
    source = json.loads(SOURCE_MANIFEST.read_text())
    registration = json.loads(REGISTRATION.read_text())
    inspection = json.loads(INSPECTION.read_text())
    model = ROOT / source["scene"]
    if not model.is_file():
        raise SystemExit(f"Missing photogrammetry scene: {model}")

    bpy.ops.wm.read_factory_settings(use_empty=True)

    terrain = np.load(TERRAIN)
    z = terrain["z"]
    xs = terrain["xs"]
    ys = terrain["ys"]
    z0 = float(terrain["z0"])

    terrain_builder.ORTHO = ORTHO
    ground_mat, image = terrain_builder.ortho_material()
    terrain_obj = terrain_builder.build_terrain(xs, ys, z, z0, ground_mat)
    terrain_obj["v2_role"] = "DGT context"

    root, meshes = import_photogrammetry(model, registration)
    face_cull = cull_near_vertical_photogrammetry_faces(
        meshes,
        max_abs_normal_z=0.15,
    )
    edge_fade_m = 100.0
    slope_fade_start = 0.18
    slope_fade_end = 0.62
    apply_photogrammetry_surface_mask(
        root,
        meshes,
        inspection,
        edge_fade_m,
        slope_fade_start=slope_fade_start,
        slope_fade_end=slope_fade_end,
    )

    camera_data = bpy.data.cameras.new("V2_001_Hero_Camera")
    camera = bpy.data.objects.new("V2_001_Hero_Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    base_camera = registration["hero_camera_local"]
    base_target = registration["hero_target_local"]
    camera_z_lift_m = 70.0
    camera.location = (
        float(base_camera[0]),
        float(base_camera[1]),
        float(base_camera[2]) + camera_z_lift_m,
    )
    camera_data.sensor_width = 36.0
    camera_data.dof.use_dof = False

    review_variants = [
        {"name": "a-85mm", "lens_mm": 85.0, "target_z_offset_m": -80.0},
        {"name": "b-105mm", "lens_mm": 105.0, "target_z_offset_m": -110.0},
        {"name": "c-125mm", "lens_mm": 125.0, "target_z_offset_m": -130.0},
    ]
    selected_variant = review_variants[1]

    scene = bpy.context.scene
    scene.camera = camera
    scene.render.resolution_x = int(cfg["hero"]["resolution"][0])
    scene.render.resolution_y = int(cfg["hero"]["resolution"][1])
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(IMAGE)
    scene.render.film_transparent = False
    scene.render.use_motion_blur = False

    scene.cycles.samples = int(cfg["hero"]["cycles_samples"])
    scene.cycles.use_denoising = True
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.08
    scene.cycles.max_bounces = 6
    scene.cycles.diffuse_bounces = 3
    scene.cycles.glossy_bounces = 3
    scene.cycles.transmission_bounces = 2
    metal_devices = configure_metal(scene)

    world = bpy.data.worlds.new("V2_001_World")
    world.use_nodes = True
    scene.world = world
    background = world.node_tree.nodes.get("Background")
    if background:
        background.inputs["Color"].default_value = (0.62, 0.70, 0.82, 1.0)
        background.inputs["Strength"].default_value = 0.45

    sun_data = bpy.data.lights.new("V2_001_Sun", "SUN")
    sun_data.energy = 2.0
    sun_data.angle = math.radians(6.0)
    sun = bpy.data.objects.new("V2_001_Sun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (
        math.radians(38.0),
        math.radians(-18.0),
        math.radians(-35.0),
    )

    OUT.mkdir(parents=True, exist_ok=True)
    variant_receipts = []
    for variant in review_variants:
        camera_data.lens = float(variant["lens_mm"])
        review_target = (
            float(base_target[0]),
            float(base_target[1]),
            float(base_target[2]) + float(variant["target_z_offset_m"]),
        )
        look_at(camera, review_target)
        variant_path = OUT / f"coimbra-v2-001-hero-{variant['name']}.png"
        scene.render.filepath = str(variant_path)
        started = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        variant_elapsed = time.perf_counter() - started
        variant_receipts.append(
            {
                **variant,
                "image": variant_path.relative_to(ROOT).as_posix(),
                "image_sha256": digest(variant_path),
                "render_seconds": variant_elapsed,
            }
        )

    selected_receipt = next(
        item for item in variant_receipts if item["name"] == selected_variant["name"]
    )
    selected_path = ROOT / selected_receipt["image"]
    shutil.copyfile(selected_path, IMAGE)
    elapsed = float(selected_receipt["render_seconds"])
    review_lens_mm = float(selected_receipt["lens_mm"])
    target_z_offset_m = float(selected_receipt["target_z_offset_m"])

    ATTRIBUTION.write_text(
        "Photogrammetry: Coimbra by VirtualPhoto3D (@johnagotinho), Sketchfab, "
        "CC Attribution.\n"
        "Orthophoto 2025 © Direção-Geral do Território (DGT), CC BY 4.0.\n"
        "Terrain/surface: DGT LiDAR 2024–2025.\n"
    )

    payload = {
        "version": "coimbra-v2-001-hero-v1",
        "purpose": "neutral visual-first still; not production-video acceptance",
        "image": IMAGE.relative_to(ROOT).as_posix(),
        "image_sha256": digest(IMAGE),
        "render_seconds": elapsed,
        "resolution": cfg["hero"]["resolution"],
        "lens_mm": review_lens_mm,
        "visual_revision": "geometric-steep-face-cull-v6",
        "review_variants": variant_receipts,
        "selected_variant": selected_variant["name"],
        "camera_z_lift_m": camera_z_lift_m,
        "target_z_offset_m": target_z_offset_m,
        "photogrammetry_edge_fade_m": edge_fade_m,
        "photogrammetry_slope_fade_start_abs_nz": slope_fade_start,
        "photogrammetry_slope_fade_end_abs_nz": slope_fade_end,
        "cycles_samples": cfg["hero"]["cycles_samples"],
        "metal_devices": metal_devices,
        "motion_blur": False,
        "depth_of_field": False,
        "cinematic_grade": False,
        "photogrammetry_meshes": len(meshes),
        "photogrammetry_face_cull": face_cull,
        "photogrammetry_transform": {
            "scale": registration["scale"],
            "rotation_z_degrees": registration["rotation_z_degrees"],
            "translation_local_xy_m": registration["translation_local_xy_m"],
            "translation_local_z_m": registration["translation_local_z_m"],
        },
        "registration_inliers": registration["inliers"],
        "registration_inlier_ratio": registration["inlier_ratio"],
        "attribution": ATTRIBUTION.relative_to(ROOT).as_posix(),
    }
    MANIFEST.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
