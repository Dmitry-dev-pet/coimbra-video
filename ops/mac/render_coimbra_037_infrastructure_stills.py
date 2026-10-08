"""Coimbra 037: two before/after infrastructure stills on the accepted 032/033 scene."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

import bpy
from mathutils import Quaternion, Vector

ROOT = Path.cwd()
COIMBRA = ROOT / "coimbra"
sys.path.insert(0, str(COIMBRA / "blender"))

import render_camera_motion_review as lane033
import render_cycles_full_route as full
import render_cycles_metal_checkpoints as metal027
import render_production_look_review as look030
import render_production_look_slow60_metal as lane032

WIDTH, HEIGHT = 960, 600
SAMPLES = 16
THRESHOLD = 0.08
BRIDGE_CENTER_XY = (-692.18, 331.73)
CLEARANCE_M = 6.5
DECK_LENGTH_M = 110.0
DECK_WIDTH_M = 11.0
DECK_THICKNESS_M = 1.1
VIEW_OFFSET_FRAMES = 36


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1 :]
    p = argparse.ArgumentParser()
    p.add_argument("--blend", type=Path, required=True)
    p.add_argument("--review", type=Path, required=True)
    p.add_argument("--prepare", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    return p.parse_args(argv)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_material(name, color, roughness=0.65, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
    return mat


def add_box(name, center, dimensions, angle, material):
    bpy.ops.mesh.primitive_cube_add(location=center)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler[2] = angle
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    return obj


def terrain_height(x: float, y: float) -> float:
    terrain = bpy.data.objects.get("City_Terrain")
    require(terrain is not None and terrain.type == "MESH", "City_Terrain mesh missing")
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = terrain.evaluated_get(depsgraph)
    inv = evaluated.matrix_world.inverted()
    origin_world = Vector((x, y, 1000.0))
    direction_world = Vector((0.0, 0.0, -1.0))
    origin_local = inv @ origin_world
    direction_local = (inv.to_3x3() @ direction_world).normalized()
    hit, location, _normal, _index = evaluated.ray_cast(
        origin_local, direction_local, distance=2000.0
    )
    require(hit, f"terrain ray miss at {x:.2f},{y:.2f}")
    return float((evaluated.matrix_world @ location).z)


def bridge_orientation(records, nearest_index: int) -> tuple[Vector, Vector]:
    lo = max(0, nearest_index - 20)
    hi = min(len(records) - 1, nearest_index + 20)
    a = Vector(records[lo]["target"])
    b = Vector(records[hi]["target"])
    tangent = b - a
    tangent.z = 0.0
    require(tangent.length > 1e-6, "bridge tangent is degenerate")
    tangent.normalize()
    normal = Vector((-tangent.y, tangent.x, 0.0))
    return tangent, normal


def build_viaduct(records, nearest_index: int):
    cx, cy = BRIDGE_CENTER_XY
    tangent, normal = bridge_orientation(records, nearest_index)
    angle = math.atan2(tangent.y, tangent.x)
    ground = terrain_height(cx, cy)
    deck_top = ground + CLEARANCE_M
    deck_center_z = deck_top - DECK_THICKNESS_M * 0.5

    concrete = make_material(
        "Infra037_Concrete",
        (0.34, 0.36, 0.37, 1.0),
        roughness=0.82,
    )
    asphalt = make_material(
        "Infra037_Asphalt",
        (0.035, 0.04, 0.045, 1.0),
        roughness=0.9,
    )
    metal = make_material(
        "Infra037_Guardrail",
        (0.25, 0.27, 0.29, 1.0),
        roughness=0.4,
        metallic=0.55,
    )

    created = []
    created.append(
        add_box(
            "Infra037_Deck",
            (cx, cy, deck_center_z),
            (DECK_LENGTH_M, DECK_WIDTH_M, DECK_THICKNESS_M),
            angle,
            concrete,
        )
    )
    created.append(
        add_box(
            "Infra037_AsphaltTop",
            (cx, cy, deck_top + 0.08),
            (DECK_LENGTH_M, DECK_WIDTH_M - 0.7, 0.16),
            angle,
            asphalt,
        )
    )

    for side in (-1.0, 1.0):
        p = Vector((cx, cy, deck_top + 0.46)) + normal * (
            side * (DECK_WIDTH_M * 0.5 - 0.18)
        )
        created.append(
            add_box(
                f"Infra037_Barrier_{'L' if side < 0 else 'R'}",
                tuple(p),
                (DECK_LENGTH_M, 0.28, 0.92),
                angle,
                concrete,
            )
        )
        rail = Vector((cx, cy, deck_top + 1.08)) + normal * (
            side * (DECK_WIDTH_M * 0.5 - 0.28)
        )
        created.append(
            add_box(
                f"Infra037_Rail_{'L' if side < 0 else 'R'}",
                tuple(rail),
                (DECK_LENGTH_M, 0.12, 0.12),
                angle,
                metal,
            )
        )

    for index, along in enumerate((-33.0, 0.0, 33.0), start=1):
        pxy = Vector((cx, cy, 0.0)) + tangent * along
        pier_ground = terrain_height(float(pxy.x), float(pxy.y))
        pier_top = deck_center_z - DECK_THICKNESS_M * 0.5
        height = max(1.5, pier_top - pier_ground)
        created.append(
            add_box(
                f"Infra037_Pier_{index}",
                (float(pxy.x), float(pxy.y), pier_ground + height * 0.5),
                (2.0, 5.6, height),
                angle,
                concrete,
            )
        )
        created.append(
            add_box(
                f"Infra037_PierCap_{index}",
                (float(pxy.x), float(pxy.y), pier_top - 0.25),
                (3.0, 8.0, 0.5),
                angle,
                concrete,
            )
        )

    for suffix, along in (("A", -DECK_LENGTH_M * 0.5 + 3.0), ("B", DECK_LENGTH_M * 0.5 - 3.0)):
        pxy = Vector((cx, cy, 0.0)) + tangent * along
        abut_ground = terrain_height(float(pxy.x), float(pxy.y))
        abut_top = deck_center_z - DECK_THICKNESS_M * 0.5
        height = max(1.5, abut_top - abut_ground)
        created.append(
            add_box(
                f"Infra037_Abutment_{suffix}",
                (float(pxy.x), float(pxy.y), abut_ground + height * 0.5),
                (4.0, DECK_WIDTH_M + 2.0, height),
                angle,
                concrete,
            )
        )

    return created, [concrete, asphalt, metal], {
        "center_xy": [cx, cy],
        "terrain_z": ground,
        "deck_top_z": deck_top,
        "clearance_m": CLEARANCE_M,
        "length_m": DECK_LENGTH_M,
        "width_m": DECK_WIDTH_M,
        "orientation_degrees": math.degrees(angle),
        "prototype": "grade-separated deck visual study at accepted route anchor; final OSM way geometry not yet promoted",
    }


def remove_temporary(objects, materials):
    for obj in list(objects):
        if obj and obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    for mat in list(materials):
        if mat and mat.users == 0 and mat.name in bpy.data.materials:
            bpy.data.materials.remove(mat)


def make_proxy_camera(scene):
    source = scene.camera
    require(source is not None, "production camera missing")
    camera = source.copy()
    data = source.data.copy()
    camera.data = data
    camera.name = "Coimbra037_ProxyCamera"
    data.name = "Coimbra037_ProxyCameraData"
    camera.animation_data_clear()
    data.animation_data_clear()
    for constraint in list(camera.constraints):
        camera.constraints.remove(constraint)
    camera.parent = None
    camera.scale = (1.0, 1.0, 1.0)
    camera.rotation_mode = "QUATERNION"
    scene.collection.objects.link(camera)
    scene.camera = camera
    return source, camera, data


def apply_camera_record(camera, record):
    camera.location = Vector(record["location"])
    camera.rotation_quaternion = Quaternion(record["quaternion"])
    camera.data.lens = float(record["lens"])
    camera.data.dof.focus_distance = float(record["focus_distance"])
    bpy.context.view_layer.update()


def render_still(scene, camera, record, path: Path):
    apply_camera_record(camera, record)
    scene.render.filepath = str(path)
    started = time.perf_counter()
    bpy.ops.render.render(write_still=True)
    elapsed = time.perf_counter() - started
    require(path.is_file() and path.stat().st_size > 0, f"missing render {path}")
    return {
        "path": path.name,
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "seconds": elapsed,
        "output_frame": int(record["output_frame"]),
        "camera_location": [float(v) for v in record["location"]],
        "camera_target": [float(v) for v in record["target"]],
        "lens": float(record["lens"]),
    }


def main():
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    review = json.loads(args.review.read_text())
    prepare = json.loads(args.prepare.read_text())

    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene = bpy.context.scene
    lane032.verify_source(scene, args.blend, review, prepare)

    before_structure = look030.structure_digest(scene)
    before_cameras = full.camera_records(scene)

    anchors = [lane033.capture_anchor(scene, frame) for frame in lane033.ANCHOR_SOURCE_FRAMES]
    smooth, path_info = lane033.smooth_records(anchors)

    cx, cy = BRIDGE_CENTER_XY
    nearest_index = min(
        range(len(smooth)),
        key=lambda i: (smooth[i]["target"][0] - cx) ** 2
        + (smooth[i]["target"][1] - cy) ** 2,
    )
    view_indices = [
        max(0, nearest_index - VIEW_OFFSET_FRAMES),
        min(len(smooth) - 1, nearest_index + VIEW_OFFSET_FRAMES),
    ]
    require(view_indices[0] != view_indices[1], "two distinct review views are required")
    views = [smooth[i] for i in view_indices]

    cpu = metal027.accepted_cpu_settings(scene)
    metal_info = metal027.configure_metal(scene, cpu)
    scene.render.resolution_x = WIDTH
    scene.render.resolution_y = HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.cycles.samples = SAMPLES
    scene.cycles.adaptive_threshold = THRESHOLD
    if hasattr(scene.render, "use_motion_blur"):
        scene.render.use_motion_blur = False
    bpy.context.view_layer.update()

    source_camera, proxy_camera, proxy_data = make_proxy_camera(scene)
    baseline = []
    overlay = []
    created = []
    materials = []
    bridge = None
    started_total = time.perf_counter()

    try:
        for label, record in zip(("a", "b"), views):
            baseline.append(
                render_still(
                    scene,
                    proxy_camera,
                    record,
                    args.out / f"baseline-{label}.png",
                )
            )

        created, materials, bridge = build_viaduct(smooth, nearest_index)
        bpy.context.view_layer.update()

        for label, record in zip(("a", "b"), views):
            overlay.append(
                render_still(
                    scene,
                    proxy_camera,
                    record,
                    args.out / f"infrastructure-{label}.png",
                )
            )
    finally:
        remove_temporary(created, materials)
        scene.camera = source_camera
        bpy.data.objects.remove(proxy_camera, do_unlink=True)
        if proxy_data.users == 0:
            bpy.data.cameras.remove(proxy_data)
        scene.frame_set(1)
        bpy.context.view_layer.update()

    require(look030.structure_digest(scene) == before_structure, "037 changed accepted scene structure")
    require(full.camera_records(scene) == before_cameras, "037 changed native camera animation")

    receipt = {
        "version": "coimbra-037-infrastructure-stills-v1",
        "verified": True,
        "review_only": True,
        "source_code_commit": os.environ.get("COIMBRA_SOURCE_SHA", "local"),
        "source_030_run": lane032.EXPECTED_030_RUN,
        "source_030_blend_sha256": lane032.EXPECTED_BLEND_SHA256,
        "scene_structure_unchanged": True,
        "native_camera_animation_unchanged": True,
        "camera_motion": "accepted Coimbra 033 smooth path",
        "nearest_route_output_frame": int(smooth[nearest_index]["output_frame"]),
        "review_output_frames": [int(v["output_frame"]) for v in views],
        "resolution": [WIDTH, HEIGHT],
        "cycles_samples": SAMPLES,
        "adaptive_threshold": THRESHOLD,
        "metal_devices": metal_info.get("metal_devices", []),
        "bridge": bridge,
        "baseline": baseline,
        "infrastructure": overlay,
        "path_length": path_info["path_length"],
        "total_seconds": time.perf_counter() - started_total,
        "note": "Visual proof only. The accepted Coimbra 032 scene and 033 camera motion are not modified or saved.",
    }
    (args.out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
