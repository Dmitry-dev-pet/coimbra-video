from __future__ import annotations

import json
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "bridge_output_019" / "coimbra-full-route-pitched-roofs.blend"
HAG = ROOT / "bridge_output_008b" / "bridge_height_above_ground_1m.npz"
OUT_IMAGE = ROOT / "data" / "processed" / "bridge_ortho_2025.jpg"
OUT_META = ROOT / "data" / "processed" / "bridge_ortho_2025.json"


def main():
    for required in (SOURCE, HAG):
        if not required.is_file():
            raise SystemExit(f"Missing input: {required}")

    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    terrain = bpy.data.objects.get("City_Terrain")
    if terrain is None or terrain.type != "MESH":
        raise RuntimeError("City_Terrain missing")

    image = None
    for mat in terrain.data.materials:
        if mat is None or not mat.use_nodes or mat.node_tree is None:
            continue
        for node in mat.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image is not None:
                candidate = node.image
                if len(candidate.packed_files) > 0:
                    image = candidate
                    break
        if image is not None:
            break

    if image is None:
        raise RuntimeError("Packed DGT orthophoto image not found")

    raw = bytes(image.packed_files[0].packed_file.data)
    if not raw:
        raise RuntimeError("Packed orthophoto payload is empty")

    hag = np.load(HAG)
    center_x = float(hag["center_x"])
    center_y = float(hag["center_y"])

    corners = [terrain.matrix_world @ Vector(corner) for corner in terrain.bound_box]
    minx_local = min(float(point.x) for point in corners)
    maxx_local = max(float(point.x) for point in corners)
    miny_local = min(float(point.y) for point in corners)
    maxy_local = max(float(point.y) for point in corners)

    width = int(image.size[0])
    height = int(image.size[1])
    if width <= 0 or height <= 0:
        raise RuntimeError(f"Invalid packed image dimensions: {image.size}")

    width_m = maxx_local - minx_local
    height_m = maxy_local - miny_local
    resolution_x = width_m / width
    resolution_y = height_m / height
    resolution = (resolution_x + resolution_y) * 0.5

    OUT_IMAGE.parent.mkdir(parents=True, exist_ok=True)
    OUT_IMAGE.write_bytes(raw)

    meta = {
        "source": "DGT Orthophotos 2025 (packed accepted scene)",
        "license": "CC BY 4.0",
        "resolution_m": resolution,
        "resolution_x_m": resolution_x,
        "resolution_y_m": resolution_y,
        "bbox_epsg3763": [
            center_x + minx_local,
            center_y + miny_local,
            center_x + maxx_local,
            center_y + maxy_local,
        ],
        "bbox_local": [
            minx_local,
            miny_local,
            maxx_local,
            maxy_local,
        ],
        "center_epsg3763": [center_x, center_y],
        "image_size": [width, height],
        "image_name": image.name,
        "output": OUT_IMAGE.relative_to(ROOT).as_posix(),
    }
    OUT_META.write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
