from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
GLB = ROOT / "bridge_output_009b" / "osm2world-coimbra.glb"
OUT = ROOT / "bridge_output_009b"
OUT_BLEND = OUT / "osm2world-reference.blend"
PREVIEW = OUT / "osm2world-reference.png"
MANIFEST = OUT / "osm2world-reference-manifest.json"


def look_at(obj, target: Vector):
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def main() -> None:
    if not GLB.is_file():
        raise SystemExit(f"Missing GLB: {GLB}")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(GLB))

    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not mesh_objects:
        raise RuntimeError("OSM2World import produced no mesh objects")

    points = []
    total_vertices = 0
    total_polygons = 0
    for obj in mesh_objects:
        total_vertices += len(obj.data.vertices)
        total_polygons += len(obj.data.polygons)
        for corner in obj.bound_box:
            points.append(obj.matrix_world @ Vector(corner))

    min_v = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    max_v = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    center = (min_v + max_v) * 0.5
    size = max_v - min_v
    span = max(size.x, size.y, max(size.z, 1.0))

    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.03, 0.04, 0.06, 1.0)
        bg.inputs["Strength"].default_value = 0.35

    sun_data = bpy.data.lights.new("OSM2World_Sun", "SUN")
    sun_data.energy = 2.5
    sun_data.angle = math.radians(12)
    sun = bpy.data.objects.new("OSM2World_Sun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(38), math.radians(-20), math.radians(-35))

    area_data = bpy.data.lights.new("OSM2World_Fill", "AREA")
    area_data.energy = 1500
    area_data.shape = "DISK"
    area_data.size = span * 0.6
    area = bpy.data.objects.new("OSM2World_Fill", area_data)
    bpy.context.collection.objects.link(area)
    area.location = center + Vector((-0.45 * span, -0.55 * span, 0.65 * span))
    look_at(area, center)

    camera_data = bpy.data.cameras.new("Camera")
    camera = bpy.data.objects.new("Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    camera.location = center + Vector((-0.75 * span, -0.75 * span, 0.72 * span))
    camera_data.lens = 52
    look_at(camera, center)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 768
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(PREVIEW)

    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))
    bpy.ops.render.render(write_still=True)

    manifest = {
        "upstream": {
            "repository": "tordanik/OSM2World",
            "commit": "8ec26a9ea426444a4f7882cf0cfcab432c876ae5",
            "license": "MIT",
        },
        "input_glb": GLB.relative_to(ROOT).as_posix(),
        "output_blend": OUT_BLEND.relative_to(ROOT).as_posix(),
        "preview": PREVIEW.relative_to(ROOT).as_posix(),
        "mesh_objects": len(mesh_objects),
        "vertices": total_vertices,
        "polygons": total_polygons,
        "bounds": {
            "min": list(min_v),
            "max": list(max_v),
            "size": list(size),
        },
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
