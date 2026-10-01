"""036: promote the reviewed Coimbra 035 quality64 treatment to the accepted 032 slow60 route."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
import time

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))

import render_backend_comparison as backend
import render_cycles_full_route as full
import render_cycles_metal_checkpoints as metal027
import render_production_look_review as look030
import render_production_look_slow60_metal as lane032

QUALITY_SAMPLES = 64
QUALITY_ADAPTIVE_THRESHOLD = 0.03
EXPECTED_035_REVIEW_RUN = 36892916114
EXPECTED_035_SOURCE_SHA = "5a76e767d8b95578a9e999b4803176812a78b3a6"


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :]
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--prepare", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args(argv)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    frames_dir = args.out / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    review = json.loads(args.review.read_text())
    prepare = json.loads(args.prepare.read_text())

    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene = bpy.context.scene
    lane032.verify_source(scene, args.blend, review, prepare)

    before_protected = full.protected_digest(scene)
    before_structure = look030.structure_digest(scene)
    before_cameras = full.camera_records(scene)

    cpu_settings = metal027.accepted_cpu_settings(scene)
    metal_settings = metal027.configure_metal(scene, cpu_settings)

    require(scene.cycles.samples == 16, "036 source samples are not accepted 032 baseline")
    require(math.isclose(float(scene.cycles.adaptive_threshold), 0.08, abs_tol=1e-6), "036 source adaptive threshold changed")
    require(scene.cycles.use_denoising is True, "036 requires accepted denoising")
    require(scene.cycles.use_adaptive_sampling is True, "036 requires accepted adaptive sampling")

    baseline_samples = int(scene.cycles.samples)
    baseline_threshold = float(scene.cycles.adaptive_threshold)
    scene.cycles.samples = QUALITY_SAMPLES
    scene.cycles.adaptive_threshold = QUALITY_ADAPTIVE_THRESHOLD
    bpy.context.view_layer.update()

    metal_settings = {
        **metal_settings,
        "samples": int(scene.cycles.samples),
        "adaptive_threshold": float(scene.cycles.adaptive_threshold),
    }

    require(metal_settings["samples"] == QUALITY_SAMPLES, "036 quality64 samples not applied")
    require(
        math.isclose(metal_settings["adaptive_threshold"], QUALITY_ADAPTIVE_THRESHOLD, abs_tol=1e-6),
        "036 quality64 adaptive threshold not applied",
    )

    frame_receipts: dict[str, dict] = {}
    shard_receipts: list[dict] = []
    started_total = time.perf_counter()

    try:
        for shard_start in range(1, lane032.OUTPUT_FRAMES + 1, lane032.SHARD_SIZE):
            shard_end = min(lane032.OUTPUT_FRAMES, shard_start + lane032.SHARD_SIZE - 1)
            shard_started = time.perf_counter()
            shard_frames: dict[str, dict] = {}

            for output_frame in range(shard_start, shard_end + 1):
                source, base, subframe = lane032.source_sample(output_frame)
                scene.frame_set(base, subframe=subframe)
                path = frames_dir / f"frame_{output_frame:04d}.png"
                started = time.perf_counter()
                backend.render_png(scene, path)
                elapsed = time.perf_counter() - started

                item = {
                    "source_frame": source,
                    "base_frame": base,
                    "subframe": subframe,
                    "sha256": full.digest_file(path),
                    "bytes": path.stat().st_size,
                    "seconds": elapsed,
                }
                frame_receipts[str(output_frame)] = item
                shard_frames[str(output_frame)] = item
                print(
                    f"036 quality64 output {output_frame}: "
                    f"source={source:.6f} ({base}+{subframe:.6f}) {elapsed:.3f}s"
                )

            shard_receipts.append({
                "start": shard_start,
                "end": shard_end,
                "seconds": time.perf_counter() - shard_started,
                "frames": shard_frames,
            })
    finally:
        scene.cycles.samples = baseline_samples
        scene.cycles.adaptive_threshold = baseline_threshold
        bpy.context.view_layer.update()

    total_seconds = time.perf_counter() - started_total

    require(full.protected_digest(scene) == before_protected, "036 rendering changed accepted visual state")
    require(look030.structure_digest(scene) == before_structure, "036 rendering changed scene structure")
    require(full.camera_records(scene) == before_cameras, "036 rendering changed native camera path")
    require(scene.cycles.samples == 16, "036 failed to restore accepted samples")
    require(math.isclose(float(scene.cycles.adaptive_threshold), 0.08, abs_tol=1e-6), "036 failed to restore accepted threshold")

    receipt = {
        "version": "coimbra-036-quality64-slow60-metal-v1",
        "source_035_review_run": EXPECTED_035_REVIEW_RUN,
        "source_035_review_commit": EXPECTED_035_SOURCE_SHA,
        "quality64_review_verified": True,
        "quality64_samples": QUALITY_SAMPLES,
        "quality64_adaptive_threshold": QUALITY_ADAPTIVE_THRESHOLD,
        "source_030_run": lane032.EXPECTED_030_RUN,
        "source_030_revision": lane032.EXPECTED_030_REVISION,
        "source_030_blend_sha256": lane032.EXPECTED_BLEND_SHA256,
        "source_030_structure_sha256": lane032.EXPECTED_STRUCTURE_SHA256,
        "source_030_protected_sha256": before_protected,
        "source_026_run": metal027.EXPECTED_026_RUN,
        "source_code_commit": os.environ.get("COIMBRA_SOURCE_SHA", "local"),
        "resolution": lane032.EXPECTED_RESOLUTION,
        "source_frame_start": lane032.SOURCE_START,
        "source_frame_end": lane032.SOURCE_END,
        "source_frame_count": 360,
        "output_frame_count": lane032.OUTPUT_FRAMES,
        "fps": lane032.OUTPUT_FPS,
        "duration_seconds": lane032.OUTPUT_FRAMES / lane032.OUTPUT_FPS,
        "speed_ratio_vs_031": 0.5,
        "source_frame_step": (lane032.SOURCE_END - lane032.SOURCE_START) / (lane032.OUTPUT_FRAMES - 1),
        "sampling": "native Blender fractional-frame evaluation",
        "repeated_frames": False,
        "optical_flow": False,
        "motion_blur": False,
        "atmosphere_light": False,
        "scene_unchanged": True,
        "structure_unchanged": True,
        "native_camera_path_unchanged": True,
        "sampling_restored": True,
        "metal": {
            "settings": metal_settings,
            "total_seconds": total_seconds,
            "frames": frame_receipts,
            "shards": shard_receipts,
        },
    }
    (args.out / "render-receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output_frame_count": lane032.OUTPUT_FRAMES,
        "fps": lane032.OUTPUT_FPS,
        "duration_seconds": receipt["duration_seconds"],
        "samples": QUALITY_SAMPLES,
        "adaptive_threshold": QUALITY_ADAPTIVE_THRESHOLD,
        "total_seconds": total_seconds,
        "metal_devices": metal_settings["metal_devices"],
        "source_035_review_run": EXPECTED_035_REVIEW_RUN,
    }, indent=2))


if __name__ == "__main__":
    main()
