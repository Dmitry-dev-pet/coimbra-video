from __future__ import annotations

import json
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST = ROOT / "bridge_output_v2_001" / "photogrammetry" / "source-manifest.json"
OUT = ROOT / "bridge_output_v2_001" / "registration"
TOPDOWN = OUT / "photogrammetry-topdown.png"
VERTICES = OUT / "photogrammetry-vertices.npz"
MANIFEST = OUT / "photogrammetry-inspection.json"
MAX_VERTEX_SAMPLES = 250_000
TOPDOWN_SIZE = 2048


def find_mesh_bounds(objects):
    points = []
    total_vertices = 0
    total_polygons = 0
    for obj in objects:
        total_vertices += len(obj.data.vertices)
        total_polygons += len(obj.data.polygons)
        for corner in obj.bound_box:
            points.append(obj.matrix_world @ Vector(corner))
    if not points:
        raise RuntimeError("Photogrammetry import has no mesh bounds")
    min_v = Vector(
        (min(p.x for p in points), min(p.y for p in points), min(p.z for p in points))
    )
    max_v = Vector(
        (max(p.x for p in points), max(p.y for p in points), max(p.z for p in points))
    )
    return min_v, max_v, total_vertices, total_polygons


def sample_vertices(objects, total_vertices: int) -> np.ndarray:
    stride = max(1, total_vertices // MAX_VERTEX_SAMPLES)
    samples = []
    for obj in objects:
        matrix = obj.matrix_world
        for index, vertex in enumerate(obj.data.vertices):
            if index % stride:
                continue
            p = matrix @ vertex.co
            samples.append((float(p.x), float(p.y), float(p.z)))
    if not samples:
        raise RuntimeError("No photogrammetry vertex samples collected")
    if len(samples) > MAX_VERTEX_SAMPLES:
        samples = samples[:: max(1, len(samples) // MAX_VERTEX_SAMPLES)]
        samples = samples[:MAX_VERTEX_SAMPLES]
    return np.asarray(samples, dtype=np.float32)


def set_fast_render_engine(scene) -> str:
    for name in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = name
            return name
        except TypeError:
            continue
    raise RuntimeError("No EEVEE render engine available")


def main() -> None:
    if not SOURCE_MANIFEST.is_file():
        raise SystemExit(f"Missing photogrammetry source manifest: {SOURCE_MANIFEST}")

    source = json.loads(SOURCE_MANIFEST.read_text())
    model = ROOT / source["scene"]
    if not model.is_file():
        raise SystemExit(f"Missing photogrammetry scene: {model}")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(model))

    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("Sketchfab import produced no mesh objects")

    min_v, max_v, total_vertices, total_polygons = find_mesh_bounds(meshes)
    size = max_v - min_v
    center = (min_v + max_v) * 0.5
    xy_span = max(float(size.x), float(size.y), 1.0)

    OUT.mkdir(parents=True, exist_ok=True)
    samples = sample_vertices(meshes, total_vertices)
    np.savez_compressed(VERTICES, xyz=samples)

    camera_data = bpy.data.cameras.new("V2_001_Topdown_Camera")
    camera = bpy.data.objects.new("V2_001_Topdown_Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    camera.location = (center.x, center.y, max_v.z + xy_span)
    camera.rotation_euler = (0.0, 0.0, 0.0)
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = xy_span * 1.04

    world = bpy.data.worlds.new("V2_001_World")
    world.use_nodes = True
    bpy.context.scene.world = world
    background = world.node_tree.nodes.get("Background")
    if background:
        background.inputs["Color"].default_value = (0.82, 0.82, 0.82, 1.0)
        background.inputs["Strength"].default_value = 0.9

    sun_data = bpy.data.lights.new("V2_001_Topdown_Sun", "SUN")
    sun_data.energy = 0.8
    sun_data.angle = 0.3
    sun = bpy.data.objects.new("V2_001_Topdown_Sun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (0.0, 0.0, 0.0)

    scene = bpy.context.scene
    engine = set_fast_render_engine(scene)
    scene.render.resolution_x = TOPDOWN_SIZE
    scene.render.resolution_y = TOPDOWN_SIZE
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.filepath = str(TOPDOWN)
    bpy.ops.render.render(write_still=True)

    # Orthographic camera has square coverage. Record the exact model-space image
    # footprint so image feature matches can be converted back to model XY.
    half = camera_data.ortho_scale * 0.5
    image_bounds = {
        "min_x": float(center.x - half),
        "max_x": float(center.x + half),
        "min_y": float(center.y - half),
        "max_y": float(center.y + half),
    }

    payload = {
        "version": "coimbra-v2-001-photogrammetry-inspection-v1",
        "source": source,
        "render_engine": engine,
        "mesh_objects": len(meshes),
        "vertices": total_vertices,
        "polygons": total_polygons,
        "sampled_vertices": int(samples.shape[0]),
        "bounds": {
            "min": [float(v) for v in min_v],
            "max": [float(v) for v in max_v],
            "size": [float(v) for v in size],
        },
        "topdown": TOPDOWN.relative_to(ROOT).as_posix(),
        "topdown_size": [TOPDOWN_SIZE, TOPDOWN_SIZE],
        "topdown_model_xy": image_bounds,
        "vertex_sample": VERTICES.relative_to(ROOT).as_posix(),
    }
    MANIFEST.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
