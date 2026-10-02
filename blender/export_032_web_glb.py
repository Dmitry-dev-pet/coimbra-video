"""Export the accepted Coimbra 032/030 production scene plus the exact 032 camera route."""
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


def source_sample(output_frame: int) -> tuple[float, int, float]:
    source = source_time(output_frame)
    base = int(math.floor(source + 1e-10))
    subframe = source - base
    if subframe >= 1.0 - 1e-9:
        base += 1
        subframe = 0.0
    return source, base, subframe


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


def export_camera_route(scene, camera, out: Path) -> dict:
    samples = []
    for output_frame in range(1, OUTPUT_FRAMES + 1):
        source, _base, _subframe = source_sample(output_frame)
        samples.append(camera_state(scene, camera, source, output_frame))

    anchor = camera_state(scene, camera, float(FRAME))
    route = {
        "version": "coimbra-038-web-route-v1",
        "source_lane": "Coimbra 032 via accepted 030 production-look scene",
        "source_blend_sha256": EXPECTED_BLEND_SHA256,
        "coordinate_space": "Blender world; align to imported frame-181 glTF camera via anchor",
        "resolution": RESOLUTION,
        "aspect": RESOLUTION[0] / RESOLUTION[1],
        "source_frame_start": SOURCE_START,
        "source_frame_end": SOURCE_END,
        "source_frame_count": 360,
        "output_frame_count": OUTPUT_FRAMES,
        "fps": OUTPUT_FPS,
        "duration_seconds": OUTPUT_FRAMES / OUTPUT_FPS,
        "source_frame_step": (SOURCE_END - SOURCE_START) / (OUTPUT_FRAMES - 1),
        "sampling": "native Blender fractional-frame evaluation",
        "repeated_frames": False,
        "optical_flow": False,
        "anchor": anchor,
        "samples": samples,
    }
    route_path = out / "coimbra-032-camera-route.json"
    route_path.write_text(
        json.dumps(route, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return {
        "path": route_path.name,
        "bytes": route_path.stat().st_size,
        "sha256": sha256(route_path),
        "output_frame_count": OUTPUT_FRAMES,
        "fps": OUTPUT_FPS,
        "duration_seconds": OUTPUT_FRAMES / OUTPUT_FPS,
        "anchor_source_frame": FRAME,
    }


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    if sha256(args.blend) != EXPECTED_BLEND_SHA256:
        raise RuntimeError("Accepted 030/032 production-look blend checksum mismatch")

    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene = bpy.context.scene
    scene.frame_set(FRAME)
    bpy.context.view_layer.update()

    camera = scene.camera
    if camera is None:
        raise RuntimeError("Production camera missing")

    frame181_camera = {
        "name": camera.name,
        "location": [float(v) for v in camera.matrix_world.translation],
        "matrix_world": matrix_rows(camera.matrix_world),
        "lens_mm": float(camera.data.lens),
        "sensor_width_mm": float(camera.data.sensor_width),
        "fov_y_deg": math.degrees(float(camera.data.angle_y)),
    }

    for obj in scene.objects:
        obj.select_set(False)

    export_objects = []
    counts = {}
    mesh_vertices = 0
    mesh_triangles = 0
    material_names = set()

    allowed_types = {"MESH", "CURVE", "SURFACE", "FONT", "META", "CAMERA", "LIGHT"}
    for obj in scene.objects:
        if obj.hide_render or obj.type not in allowed_types:
            continue
        obj.select_set(True)
        export_objects.append(obj)
        counts[obj.type] = counts.get(obj.type, 0) + 1

        if obj.type == "MESH":
            mesh = obj.data
            mesh_vertices += len(mesh.vertices)
            mesh.calc_loop_triangles()
            mesh_triangles += len(mesh.loop_triangles)
            for slot in obj.material_slots:
                if slot.material:
                    material_names.add(slot.material.name)

    if not export_objects or counts.get("MESH", 0) == 0:
        raise RuntimeError("No render-visible production geometry selected")

    glb = args.out / "coimbra-032-frame181.glb"
    bpy.ops.export_scene.gltf(
        filepath=str(glb),
        export_format="GLB",
        use_selection=True,
        export_cameras=True,
        export_lights=True,
        export_animations=False,
        export_materials="EXPORT",
        export_image_format="WEBP",
        export_image_quality=82,
        export_meshopt_compression_enable=True,
        export_meshopt_extension="EXT_meshopt_compression",
        export_texcoords=True,
        export_normals=True,
        export_yup=True,
    )

    if not glb.is_file() or glb.stat().st_size < 1024 * 1024:
        raise RuntimeError("GLB export is missing or unexpectedly small")

    packed_images = sum(1 for image in bpy.data.images if image.packed_file)
    file_images = sum(
        1 for image in bpy.data.images
        if image.filepath and not image.packed_file
    )

    route_info = export_camera_route(scene, camera, args.out)
    scene.frame_set(FRAME)
    bpy.context.view_layer.update()

    manifest = {
        "version": "coimbra-038-web-route-export-v1",
        "source_lane": "Coimbra 032 via accepted 030 production-look scene",
        "source_run_id": 36720891074,
        "source_blend": args.blend.name,
        "source_blend_sha256": EXPECTED_BLEND_SHA256,
        "frame": FRAME,
        "selected_objects": len(export_objects),
        "object_types": counts,
        "mesh_vertices": mesh_vertices,
        "mesh_triangles": mesh_triangles,
        "materials": len(material_names),
        "packed_images": packed_images,
        "external_file_images": file_images,
        "camera": frame181_camera,
        "route": route_info,
        "web_compression": {
            "mesh": "EXT_meshopt_compression",
            "images": "WebP",
            "image_quality": 82,
            "geometry_simplification": False,
        },
        "glb": {
            "path": glb.name,
            "bytes": glb.stat().st_size,
            "sha256": sha256(glb),
        },
    }
    (args.out / "export-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
