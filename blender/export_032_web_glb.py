"""Export the accepted Coimbra 032/030 production scene to a static GLB."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy


EXPECTED_BLEND_SHA256 = "5fe8ca9e8605c6ea1908d8a814f9ad5209248c606b34ebbbb3dd47607edff881"
FRAME = 181


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

    manifest = {
        "version": "coimbra-037-web-parity-export-v1",
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
        "camera": {
            "name": camera.name,
            "location": [float(v) for v in camera.matrix_world.translation],
            "matrix_world": matrix_rows(camera.matrix_world),
            "lens_mm": float(camera.data.lens),
            "sensor_width_mm": float(camera.data.sensor_width),
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
