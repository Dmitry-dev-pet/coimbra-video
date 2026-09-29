from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
BLENDER_DIR = ROOT / "blender"
if str(BLENDER_DIR) not in sys.path:
    sys.path.insert(0, str(BLENDER_DIR))

import render_backend_comparison as backend  # type: ignore

OUT = ROOT / "bridge_output_025"
MANIFEST = OUT / "cycles-route-baseline.json"

REVIEW_FRAMES = [1, 181, 360]
SOURCE_024_COMMIT = "d5583af1a837c6a3a0831f42ffdc667abd6b37ab"


def configure_cycles(scene):
    engine = backend.set_engine(scene, ["CYCLES", "BLENDER_CYCLES"])
    cycles = getattr(scene, "cycles", None)
    settings = {}
    for key, value in (
        ("device", "CPU"),
        ("samples", 16),
        ("use_denoising", True),
        ("use_adaptive_sampling", True),
        ("adaptive_threshold", 0.08),
        ("max_bounces", 6),
        ("diffuse_bounces", 3),
        ("glossy_bounces", 3),
        ("transmission_bounces", 2),
    ):
        try:
            applied = backend.set_if_attr(cycles, key, value)
        except (TypeError, ValueError):
            applied = None
        if applied is not None:
            settings[key] = applied
    return engine, settings


def camera_record(camera, frame):
    return {
        "frame": frame,
        "location": [float(v) for v in camera.location],
        "rotation_euler": [float(v) for v in camera.rotation_euler],
        "lens": float(camera.data.lens),
        "focus_distance": float(camera.data.dof.focus_distance),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    scene, geometry = backend.build_scene()
    camera = scene.camera
    if camera is None:
        raise RuntimeError("production camera missing")

    result = {
        "version": "coimbra-cycles-route-baseline-v1",
        "source_024_commit": SOURCE_024_COMMIT,
        "source_branch": "feature/coimbra-024-render-backend-ab",
        "review_frames": REVIEW_FRAMES,
        "resolution": [backend.WIDTH, backend.HEIGHT],
        "geometry": geometry,
        "production_camera": camera.name,
        "production_camera_unchanged": True,
        "geometry_material_mutations": False,
        "renders": [],
    }

    for frame in REVIEW_FRAMES:
        scene.frame_set(frame)
        camera_state = camera_record(camera, frame)

        eevee_engine = backend.set_engine(scene, ["BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"])
        eevee_path = OUT / f"frame-{frame:03d}-eevee-current.png"
        backend.render_png(scene, eevee_path)

        cycles_engine, cycles_settings = configure_cycles(scene)
        cycles_path = OUT / f"frame-{frame:03d}-cycles-16spp-denoised.png"
        backend.render_png(scene, cycles_path)

        result["renders"].append(
            {
                "frame": frame,
                "camera": camera_state,
                "eevee": {
                    "label": "EEVEE current 023",
                    "engine": eevee_engine,
                    "path": eevee_path.relative_to(ROOT).as_posix(),
                },
                "cycles": {
                    "label": "Cycles 16 spp + denoise",
                    "engine": cycles_engine,
                    "settings": cycles_settings,
                    "path": cycles_path.relative_to(ROOT).as_posix(),
                },
            }
        )

    MANIFEST.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
