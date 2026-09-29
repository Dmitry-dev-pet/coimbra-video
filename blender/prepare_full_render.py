from __future__ import annotations

import hashlib
import json
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "bridge_output_010" / "coimbra-urban-quality.blend"
OUT = ROOT / "bridge_output_016"
BLEND = OUT / "coimbra-full-render-016.blend"
MANIFEST = OUT / "full-render-prepare-manifest.json"

WIDTH = 1280
HEIGHT = 720
FPS = 30
FRAME_START = 1
FRAME_END = 360


def camera_signature(scene):
    camera = scene.camera
    if camera is None or camera.type != "CAMERA":
        raise RuntimeError("production camera missing")

    original = scene.frame_current
    checkpoints = []
    for frame in (1, 61, 121, 181, 241, 301, 360):
        scene.frame_set(frame)
        checkpoints.append(
            {
                "frame": frame,
                "location": [round(float(v), 6) for v in camera.location],
                "rotation": [round(float(v), 7) for v in camera.rotation_euler],
                "lens": round(float(camera.data.lens), 6),
                "fstop": round(float(camera.data.dof.aperture_fstop), 6),
                "focus_distance": round(float(camera.data.dof.focus_distance), 6),
            }
        )
    scene.frame_set(original)
    payload = json.dumps(checkpoints, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def main():
    if not SOURCE.is_file():
        raise SystemExit(f"Missing 010 source scene: {SOURCE}")

    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    scene = bpy.context.scene

    signature_before = camera_signature(scene)

    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.render.fps = FPS
    scene.render.fps_base = 1.0
    scene.render.resolution_x = WIDTH
    scene.render.resolution_y = HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"

    # Full run is a render-only operation. Do not touch camera animation,
    # geometry, materials or lighting.
    signature_after = camera_signature(scene)
    if signature_after != signature_before:
        raise RuntimeError("production camera changed while preparing full render")

    scene["full_render_version"] = "coimbra-full-render-v1"
    scene["full_render_width"] = WIDTH
    scene["full_render_height"] = HEIGHT
    scene["full_render_fps"] = FPS
    scene["full_render_frames"] = FRAME_END - FRAME_START + 1

    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))

    result = {
        "version": "coimbra-full-render-v1",
        "source_scene": SOURCE.relative_to(ROOT).as_posix(),
        "prepared_scene": BLEND.relative_to(ROOT).as_posix(),
        "resolution": [WIDTH, HEIGHT],
        "fps": FPS,
        "frame_start": FRAME_START,
        "frame_end": FRAME_END,
        "frame_count": FRAME_END - FRAME_START + 1,
        "duration_seconds": (FRAME_END - FRAME_START + 1) / FPS,
        "camera_hash_before": signature_before,
        "camera_hash_after": signature_after,
        "camera_unchanged": signature_before == signature_after,
        "scene_changes": {
            "geometry": False,
            "materials": False,
            "lighting": False,
            "camera_animation": False,
            "render_settings_only": True,
        },
    }
    MANIFEST.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
