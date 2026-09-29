from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "bridge_output_019" / "coimbra-full-route-pitched-roofs.blend"
OUT = ROOT / "bridge_output_023" / "review-bbox.json"
FRAME = 33
HALF_SIZE_M = 360.0


def main():
    if not SOURCE.is_file():
        raise SystemExit(f"Missing source: {SOURCE}")

    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    scene = bpy.context.scene
    camera = scene.camera
    if camera is None:
        raise RuntimeError("production camera missing")

    scene.frame_set(FRAME)
    forward = camera.matrix_world.to_quaternion() @ Vector((0.0, 0.0, -1.0))

    focus_distance = float(camera.data.dof.focus_distance)
    if not (20.0 <= focus_distance <= 900.0):
        focus_distance = 250.0

    target = camera.location + forward * focus_distance
    # Keep the crop useful even if DOF focus is relatively close.
    if (Vector((target.x, target.y, 0.0)) - Vector((camera.location.x, camera.location.y, 0.0))).length < 100.0:
        target = camera.location + forward * 260.0

    bbox = [
        float(target.x - HALF_SIZE_M),
        float(target.y - HALF_SIZE_M),
        float(target.x + HALF_SIZE_M),
        float(target.y + HALF_SIZE_M),
    ]

    result = {
        "version": "coimbra-semantic-object-review-bbox-v1",
        "frame": FRAME,
        "half_size_m": HALF_SIZE_M,
        "bbox_local": bbox,
        "camera_location": [float(v) for v in camera.location],
        "target_local": [float(target.x), float(target.y), float(target.z)],
        "lens_mm": float(camera.data.lens),
        "focus_distance": float(camera.data.dof.focus_distance),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
