"""Export the accepted Coimbra 032/030 scene and a baked 032 browser camera route."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy


EXPECTED_BLEND_SHA256 = "5fe8ca9e8605c6ea1908d8a814f9ad5209248c606b34ebbbb3dd47607edff881"
FRAME = 181
SOURCE_START = 1.0
SOURCE_END = 360.0
OUTPUT_FRAMES = 1440
OUTPUT_FPS = 60
RESOLUTION = [1600, 1000]
WEB_CAMERA_NAME = "Coimbra038_WebCamera"


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :]
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args(argv)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def matrix_rows(matrix):
    return [[float(v) for v in row] for row in matrix]


def matrix_flat_rows(matrix):
    return [float(v) for row in matrix for v in row]


def source_time(output_frame: int) -> float:
    if not 1 <= output_frame <= OUTPUT_FRAMES:
        raise ValueError(output_frame)
    t = (output_frame - 1) / (OUTPUT_FRAMES - 1)
    return SOURCE_START + t * (SOURCE_END - SOURCE_START)


def set_source_frame(scene, source: float) -> tuple[int, float]:
    base = int(math.floor(source + 1e-10))
    subframe = source - base
    if subframe >= 1.0 - 1e-9:
        base += 1
        subframe = 0.0
    scene.frame_set(base, subframe=subframe)
    bpy.context.view_layer.update()
    return base, subframe


def camera_state(scene, camera, source: float, output_frame: int | None = None) -> dict:
    base, subframe = set_source_frame(scene, source)
    state = {
        "source_frame": float(source),
        "base_frame": int(base),
        "subframe": float(subframe),
        "matrix_world": matrix_flat_rows(camera.matrix_world),
        "lens_mm": float(camera.data.lens),
        "sensor_width_mm": float(camera.data.sensor_width),
        "fov_y_deg": math.degrees(float(camera.data.angle_y)),
    }
    if output_frame is not None:
        state["output_frame"] = int(output_frame)
    return state


def selected_export_objects(scene, production_camera, web_camera=None):
    allowed_types = {"MESH", "CURVE", "SURFACE", "FONT", "META", "CAMERA", "LIGHT"}
    result = []
    for obj in scene.objects:
        obj.select_set(False)
    for obj in scene.objects:
        if obj.hide_render or obj.type not in allowed_types:
            continue
        if web_camera is not None and obj == production_camera:
            continue
        if web_camera is None and obj.name == WEB_CAMERA_NAME:
            continue
        obj.select_set(True)
        result.append(obj)
    if web_camera is not None:
        web_camera.select_set(True)
        if web_camera not in result:
            result.append(web_camera)
    return result


def export_glb(path: Path, *, animations: bool) -> None:
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_cameras=True,
        export_lights=True,
        export_animations=animations,
        export_materials="EXPORT",
        export_image_format="WEBP",
        export_image_quality=82,
        export_meshopt_compression_enable=True,
        export_meshopt_extension="EXT_meshopt_compression",
        export_texcoords=True,
        export_normals=True,
        export_yup=True,
    )
    if not path.is_file() or path.stat().st_size < 1024 * 1024:
        raise RuntimeError(f"GLB export missing or unexpectedly small: {path}")


def bake_web_camera(scene, production_camera) -> tuple[object, dict]:
    old = bpy.data.objects.get(WEB_CAMERA_NAME)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)

    web_camera = bpy.data.objects.new(WEB_CAMERA_NAME, production_camera.data.copy())
    bpy.context.collection.objects.link(web_camera)
    web_camera.rotation_mode = "QUATERNION"

    samples = []
    lens_values = []
    for output_frame in range(1, OUTPUT_FRAMES + 1):
        source = source_time(output_frame)
        state = camera_state(scene, production_camera, source, output_frame)
        samples.append(state)
        lens_values.append(state["lens_mm"])

        loc, rot, scale = production_camera.matrix_world.decompose()
        web_camera.location = loc
        web_camera.rotation_quaternion = rot
        web_camera.scale = scale
        web_camera.data.lens = state["lens_mm"]

        web_camera.keyframe_insert(data_path="location", frame=output_frame)
        web_camera.keyframe_insert(data_path="rotation_quaternion", frame=output_frame)
        web_camera.keyframe_insert(data_path="scale", frame=output_frame)

    if web_camera.animation_data is None or web_camera.animation_data.action is None:
        raise RuntimeError("Baked web camera action was not created")

    anchor = camera_state(scene, production_camera, float(FRAME))
    route = {
        "version": "coimbra-038-web-route-v2",
        "source_lane": "Coimbra 032 via accepted 030 production-look scene",
        "source_blend_sha256": EXPECTED_BLEND_SHA256,
        "camera_node": WEB_CAMERA_NAME,
        "coordinate_space": "glTF exporter-baked camera animation; browser does not remap Blender matrices",
        "resolution": RESOLUTION,
        "aspect": RESOLUTION[0] / RESOLUTION[1],
        "source_frame_start": SOURCE_START,
        "source_frame_end": SOURCE_END,
        "source_frame_count": 360,
        "output_frame_count": OUTPUT_FRAMES,
        "fps": OUTPUT_FPS,
        "duration_seconds": OUTPUT_FRAMES / OUTPUT_FPS,
        "animation_sample_duration_seconds": (OUTPUT_FRAMES - 1) / OUTPUT_FPS,
        "source_frame_step": (SOURCE_END - SOURCE_START) / (OUTPUT_FRAMES - 1),
        "sampling": "native Blender fractional-frame evaluation baked to 1440 camera transform keys",
        "repeated_frames": False,
        "optical_flow": False,
        "lens_constant": max(lens_values) - min(lens_values) < 1e-9,
        "anchor": anchor,
        "samples": samples,
    }
    return web_camera, route


def scene_stats(scene) -> dict:
    counts = {}
    mesh_vertices = 0
    mesh_triangles = 0
    material_names = set()
    for obj in scene.objects:
        if obj.hide_render:
            continue
        counts[obj.type] = counts.get(obj.type, 0) + 1
        if obj.type != "MESH":
            continue
        mesh = obj.data
        mesh_vertices += len(mesh.vertices)
        mesh.calc_loop_triangles()
        mesh_triangles += len(mesh.loop_triangles)
        for slot in obj.material_slots:
            if slot.material:
                material_names.add(slot.material.name)
    return {
        "object_types": counts,
        "mesh_vertices": mesh_vertices,
        "mesh_triangles": mesh_triangles,
        "materials": len(material_names),
    }


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    if sha256(args.blend) != EXPECTED_BLEND_SHA256:
        raise RuntimeError("Accepted 030/032 production-look blend checksum mismatch")

    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene = bpy.context.scene
    production_camera = scene.camera
    if production_camera is None:
        raise RuntimeError("Production camera missing")

    scene.frame_set(FRAME)
    bpy.context.view_layer.update()
    frame181_camera = {
        "name": production_camera.name,
        "location": [float(v) for v in production_camera.matrix_world.translation],
        "matrix_world": matrix_rows(production_camera.matrix_world),
        "lens_mm": float(production_camera.data.lens),
        "sensor_width_mm": float(production_camera.data.sensor_width),
        "fov_y_deg": math.degrees(float(production_camera.data.angle_y)),
    }

    stats = scene_stats(scene)
    if stats["object_types"].get("MESH", 0) == 0:
        raise RuntimeError("No render-visible production geometry found")

    selected_export_objects(scene, production_camera)
    static_glb = args.out / "coimbra-032-frame181.glb"
    export_glb(static_glb, animations=False)

    web_camera, route = bake_web_camera(scene, production_camera)
    route_path = args.out / "coimbra-032-camera-route.json"
    route_path.write_text(json.dumps(route, separators=(",", ":")) + "\n", encoding="utf-8")

    scene.frame_start = 1
    scene.frame_end = OUTPUT_FRAMES
    scene.render.fps = OUTPUT_FPS
    scene.frame_set(1)
    bpy.context.view_layer.update()

    selected_export_objects(scene, production_camera, web_camera)
    route_glb = args.out / "coimbra-032-route.glb"
    export_glb(route_glb, animations=True)

    packed_images = sum(1 for image in bpy.data.images if image.packed_file)
    file_images = sum(
        1 for image in bpy.data.images
        if image.filepath and not image.packed_file
    )

    manifest = {
        "version": "coimbra-038-web-route-export-v2",
        "source_lane": "Coimbra 032 via accepted 030 production-look scene",
        "source_run_id": 36720891074,
        "source_blend": args.blend.name,
        "source_blend_sha256": EXPECTED_BLEND_SHA256,
        "frame": FRAME,
        **stats,
        "packed_images": packed_images,
        "external_file_images": file_images,
        "camera": frame181_camera,
        "route": {
            "path": route_path.name,
            "bytes": route_path.stat().st_size,
            "sha256": sha256(route_path),
            "camera_node": WEB_CAMERA_NAME,
            "output_frame_count": OUTPUT_FRAMES,
            "fps": OUTPUT_FPS,
            "duration_seconds": OUTPUT_FRAMES / OUTPUT_FPS,
            "lens_constant": route["lens_constant"],
        },
        "web_compression": {
            "mesh": "EXT_meshopt_compression",
            "images": "WebP",
            "image_quality": 82,
            "geometry_simplification": False,
        },
        "static_glb": {
            "path": static_glb.name,
            "bytes": static_glb.stat().st_size,
            "sha256": sha256(static_glb),
        },
        "route_glb": {
            "path": route_glb.name,
            "bytes": route_glb.stat().st_size,
            "sha256": sha256(route_glb),
        },
    }
    # Compatibility for the existing 037 staging/verifier.
    manifest["glb"] = manifest["static_glb"]

    (args.out / "export-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
