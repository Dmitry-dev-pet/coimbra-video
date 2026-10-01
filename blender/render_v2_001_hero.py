from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys
import time

import bpy
import numpy as np
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))

import build_dgt_terrain_scene as terrain_builder

CONFIG = ROOT / "config" / "coimbra_v2_001.json"
SOURCE_MANIFEST = ROOT / "bridge_output_v2_001" / "photogrammetry" / "source-manifest.json"
REGISTRATION = ROOT / "bridge_output_v2_001" / "registration" / "registration.json"
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


def main() -> None:
    for path in (CONFIG, SOURCE_MANIFEST, REGISTRATION, ORTHO, TERRAIN):
        if not path.is_file():
            raise SystemExit(f"Missing V2-001 hero input: {path}")

    cfg = json.loads(CONFIG.read_text())
    source = json.loads(SOURCE_MANIFEST.read_text())
    registration = json.loads(REGISTRATION.read_text())
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

    camera_data = bpy.data.cameras.new("V2_001_Hero_Camera")
    camera = bpy.data.objects.new("V2_001_Hero_Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = tuple(registration["hero_camera_local"])
    camera_data.lens = float(cfg["hero"]["lens_mm"])
    camera_data.sensor_width = 36.0
    camera_data.dof.use_dof = False
    look_at(camera, registration["hero_target_local"])

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
    started = time.perf_counter()
    bpy.ops.render.render(write_still=True)
    elapsed = time.perf_counter() - started

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
        "lens_mm": cfg["hero"]["lens_mm"],
        "cycles_samples": cfg["hero"]["cycles_samples"],
        "metal_devices": metal_devices,
        "motion_blur": False,
        "depth_of_field": False,
        "cinematic_grade": False,
        "photogrammetry_meshes": len(meshes),
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
