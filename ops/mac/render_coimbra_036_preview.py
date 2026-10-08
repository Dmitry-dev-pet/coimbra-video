"""Coimbra 036 review preview: 640x480 / 60 fps with the validated 033 smooth camera path."""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import bpy

ROOT = Path.cwd()
COIMBRA = ROOT / "coimbra"
sys.path.insert(0, str(COIMBRA / "blender"))

import render_camera_motion_review as lane033
import render_cycles_full_route as full
import render_cycles_metal_checkpoints as metal027
import render_production_look_review as look030
import render_production_look_slow60_metal as lane032
from mathutils import Quaternion, Vector

WIDTH, HEIGHT = 640, 480
SAMPLES = 4
THRESHOLD = 0.15
RENDER_FRAMES = 1440
OUTPUT_FRAMES = 1440
OUTPUT_FPS = 60


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--blend", type=Path, required=True)
    p.add_argument("--review", type=Path, required=True)
    p.add_argument("--prepare", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    return p.parse_args(sys.argv[sys.argv.index("--") + 1 :])


def render_preview_png(scene, path: Path) -> None:
    """Render without the production helper that forces 1600x1000."""
    if scene.render.resolution_x != WIDTH or scene.render.resolution_y != HEIGHT:
        raise RuntimeError(
            f"preview resolution drift before render: "
            f"{scene.render.resolution_x}x{scene.render.resolution_y}"
        )
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    if not path.is_file():
        raise RuntimeError(f"Render missing: {path}")


def main():
    a = parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    frames = a.out / "frames"
    frames.mkdir(parents=True, exist_ok=True)

    review = json.loads(a.review.read_text())
    prepare = json.loads(a.prepare.read_text())

    bpy.ops.wm.open_mainfile(filepath=str(a.blend))
    scene = bpy.context.scene
    lane032.verify_source(scene, a.blend, review, prepare)

    structure_before = look030.structure_digest(scene)
    cameras_before = full.camera_records(scene)

    anchors = [lane033.capture_anchor(scene, frame) for frame in lane033.ANCHOR_SOURCE_FRAMES]
    current_records = [
        lane033.capture_current(scene, lane033.source_time(frame))
        for frame in range(1, lane033.OUTPUT_FRAMES + 1)
    ]
    smooth_records, path_info = lane033.smooth_records(anchors)
    current_metrics = lane033.motion_metrics(current_records)
    smooth_metrics = lane033.motion_metrics(smooth_records)

    cpu = metal027.accepted_cpu_settings(scene)
    metal = metal027.configure_metal(scene, cpu)

    source_camera = scene.camera
    if source_camera is None:
        raise RuntimeError("production camera missing")

    proxy_camera = source_camera.copy()
    proxy_data = source_camera.data.copy()
    proxy_camera.data = proxy_data
    proxy_camera.name = "Coimbra036_SmoothPreviewCamera"
    proxy_data.name = "Coimbra036_SmoothPreviewCameraData"
    proxy_camera.animation_data_clear()
    proxy_data.animation_data_clear()
    for constraint in list(proxy_camera.constraints):
        proxy_camera.constraints.remove(constraint)
    proxy_camera.parent = None
    proxy_camera.scale = (1.0, 1.0, 1.0)
    proxy_camera.rotation_mode = "QUATERNION"
    scene.collection.objects.link(proxy_camera)
    scene.camera = proxy_camera

    old = (
        scene.render.resolution_x,
        scene.render.resolution_y,
        scene.render.resolution_percentage,
        scene.cycles.samples,
        float(scene.cycles.adaptive_threshold),
    )
    scene.render.resolution_x = WIDTH
    scene.render.resolution_y = HEIGHT
    scene.render.resolution_percentage = 100
    scene.cycles.samples = SAMPLES
    scene.cycles.adaptive_threshold = THRESHOLD
    bpy.context.view_layer.update()

    receipts = {}
    t0 = time.perf_counter()
    scene.frame_set(1)
    bpy.context.view_layer.update()
    try:
        for record in smooth_records:
            render_frame = int(record["output_frame"])
            proxy_camera.location = Vector(record["location"])
            proxy_camera.rotation_quaternion = Quaternion(record["quaternion"])
            proxy_camera.data.lens = float(record["lens"])
            proxy_camera.data.dof.focus_distance = float(record["focus_distance"])
            bpy.context.view_layer.update()

            path = frames / f"frame_{render_frame:04d}.png"
            f0 = time.perf_counter()
            render_preview_png(scene, path)
            elapsed = time.perf_counter() - f0

            actual_q = proxy_camera.matrix_world.to_quaternion().normalized()
            receipts[str(render_frame)] = {
                "route_fraction": float(record["route_fraction"]),
                "seconds": elapsed,
                "bytes": path.stat().st_size,
                "sha256": full.digest_file(path),
                "camera_location_after_render": [float(v) for v in proxy_camera.location],
                "camera_quaternion_after_render": [
                    float(actual_q.w), float(actual_q.x), float(actual_q.y), float(actual_q.z)
                ],
                "lens_after_render": float(proxy_camera.data.lens),
                "focus_distance_after_render": float(proxy_camera.data.dof.focus_distance),
            }
            print(f"036-smooth-preview {render_frame}/{RENDER_FRAMES} {elapsed:.3f}s")
    finally:
        scene.camera = source_camera
        bpy.data.objects.remove(proxy_camera, do_unlink=True)
        if proxy_data.users == 0:
            bpy.data.cameras.remove(proxy_data)
        (
            scene.render.resolution_x,
            scene.render.resolution_y,
            scene.render.resolution_percentage,
            scene.cycles.samples,
            scene.cycles.adaptive_threshold,
        ) = old
        bpy.context.view_layer.update()

    assert look030.structure_digest(scene) == structure_before
    assert full.camera_records(scene) == cameras_before

    receipt = {
        "version": "coimbra-036-smooth-camera-preview1440-native60-640x480-v5",
        "preview_only": True,
        "source_035_review_run": 36892916114,
        "quality64_promoted": False,
        "source_030_run": lane032.EXPECTED_030_RUN,
        "source_030_blend_sha256": lane032.EXPECTED_BLEND_SHA256,
        "source_code_commit": os.environ.get("COIMBRA_SOURCE_SHA", "local"),
        "resolution": [WIDTH, HEIGHT],
        "samples": SAMPLES,
        "adaptive_threshold": THRESHOLD,
        "render_frame_count": RENDER_FRAMES,
        "output_frame_count": OUTPUT_FRAMES,
        "fps": OUTPUT_FPS,
        "duration_seconds": OUTPUT_FRAMES / OUTPUT_FPS,
        "speed_ratio_vs_031": 0.5,
        "source_frame_step": (lane032.SOURCE_END - lane032.SOURCE_START) / (RENDER_FRAMES - 1),
        "sampling": "1440 native 60 fps evaluations of the Coimbra 033 smoothed camera candidate",
        "camera_motion_model": "coimbra-033-smooth-camera-motion-review-v2",
        "anchor_source_frames": lane033.ANCHOR_SOURCE_FRAMES,
        "route_model": {
            "position": "centripetal Catmull-Rom through accepted anchor locations",
            "target": "centripetal Catmull-Rom through anchor forward targets",
            "speed": "global arc-length parameterization",
            "rotation": "look-at quaternion derived from smoothed target and position",
            **path_info,
        },
        "motion_metrics": {
            "current_032_sampling": current_metrics,
            "candidate_033_smoothed": smooth_metrics,
        },
        "smooth_records": smooth_records,
        "repeated_frames": False,
        "repeat_factor": 1,
        "metal_devices": metal.get("metal_devices", []),
        "total_seconds": time.perf_counter() - t0,
        "frames": receipts,
    }
    (a.out / "render-receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
