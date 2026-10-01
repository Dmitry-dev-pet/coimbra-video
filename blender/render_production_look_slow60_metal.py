"""032: render the accepted Coimbra 030 v2 look at 1440 native Blender subframes / 60 fps."""
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

SOURCE_START = 1.0
SOURCE_END = 360.0
OUTPUT_FRAMES = 1440
OUTPUT_FPS = 60
SHARD_SIZE = 120

EXPECTED_030_RUN = 36720891074
EXPECTED_030_REVISION = "v2-shadow-recovery"
EXPECTED_BLEND_SHA256 = "5fe8ca9e8605c6ea1908d8a814f9ad5209248c606b34ebbbb3dd47607edff881"
EXPECTED_STRUCTURE_SHA256 = "c3e599c7d27547527c6d6b430b7aaed8c8103c297d93c68fc66eef0c194d02da"
EXPECTED_RESOLUTION = [1600, 1000]


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


def verify_source(scene, blend: Path, review: dict, prepare: dict) -> None:
    require(full.digest_file(blend) == EXPECTED_BLEND_SHA256, "Wrong accepted 030 candidate blend")
    require(review.get("version") == "coimbra-030-production-look-review-v1", "Wrong 030 review schema")
    require(review.get("candidate_revision") == EXPECTED_030_REVISION, "Wrong 030 candidate revision")
    require(review.get("candidate_blend", {}).get("sha256") == EXPECTED_BLEND_SHA256, "030 manifest blend SHA mismatch")
    require(review.get("structure_sha256") == EXPECTED_STRUCTURE_SHA256, "030 manifest structure SHA mismatch")
    require(review.get("structure_unchanged") is True, "030 structure was not accepted")
    require(review.get("camera_unchanged") is True, "030 camera was not accepted")
    require(review.get("resolution") == EXPECTED_RESOLUTION, "030 resolution changed")
    require(review.get("source_026_run") == metal027.EXPECTED_026_RUN, "030 is not based on accepted 026")

    require(look030.structure_digest(scene) == EXPECTED_STRUCTURE_SHA256, "Loaded 030 structure differs")
    require(full.camera_records(scene) == prepare.get("cameras"), "Loaded 030 camera path differs from 026")
    require(prepare.get("frame_count") == 360 and prepare.get("fps") == 30, "Native route timing changed")
    require([scene.render.resolution_x, scene.render.resolution_y] == EXPECTED_RESOLUTION, "Scene resolution changed")


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    frames_dir = args.out / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    review = json.loads(args.review.read_text())
    prepare = json.loads(args.prepare.read_text())

    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene = bpy.context.scene
    verify_source(scene, args.blend, review, prepare)

    before_protected = full.protected_digest(scene)
    before_structure = look030.structure_digest(scene)
    before_cameras = full.camera_records(scene)

    cpu_settings = metal027.accepted_cpu_settings(scene)
    metal_settings = metal027.configure_metal(scene, cpu_settings)

    frame_receipts: dict[str, dict] = {}
    shard_receipts: list[dict] = []
    started_total = time.perf_counter()

    for shard_start in range(1, OUTPUT_FRAMES + 1, SHARD_SIZE):
        shard_end = min(OUTPUT_FRAMES, shard_start + SHARD_SIZE - 1)
        shard_started = time.perf_counter()
        shard_frames: dict[str, dict] = {}

        for output_frame in range(shard_start, shard_end + 1):
            source, base, subframe = source_sample(output_frame)
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
                f"slow60 production-look metal output {output_frame}: "
                f"source={source:.6f} ({base}+{subframe:.6f}) {elapsed:.3f}s"
            )

        shard_receipts.append({
            "start": shard_start,
            "end": shard_end,
            "seconds": time.perf_counter() - shard_started,
            "frames": shard_frames,
        })

    total_seconds = time.perf_counter() - started_total

    require(full.protected_digest(scene) == before_protected, "032 rendering changed accepted visual state")
    require(look030.structure_digest(scene) == before_structure, "032 rendering changed scene structure")
    require(full.camera_records(scene) == before_cameras, "032 rendering changed native camera path")

    receipt = {
        "version": "coimbra-032-slow60-production-look-metal-v1",
        "source_030_run": EXPECTED_030_RUN,
        "source_030_revision": EXPECTED_030_REVISION,
        "source_030_blend_sha256": EXPECTED_BLEND_SHA256,
        "source_030_structure_sha256": EXPECTED_STRUCTURE_SHA256,
        "source_030_protected_sha256": before_protected,
        "source_026_run": metal027.EXPECTED_026_RUN,
        "source_code_commit": os.environ.get("COIMBRA_SOURCE_SHA", "local"),
        "resolution": EXPECTED_RESOLUTION,
        "source_frame_start": SOURCE_START,
        "source_frame_end": SOURCE_END,
        "source_frame_count": 360,
        "output_frame_count": OUTPUT_FRAMES,
        "fps": OUTPUT_FPS,
        "duration_seconds": OUTPUT_FRAMES / OUTPUT_FPS,
        "speed_ratio_vs_031": 0.5,
        "source_frame_step": (SOURCE_END - SOURCE_START) / (OUTPUT_FRAMES - 1),
        "sampling": "native Blender fractional-frame evaluation",
        "repeated_frames": False,
        "optical_flow": False,
        "scene_unchanged": True,
        "structure_unchanged": True,
        "native_camera_path_unchanged": True,
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
        "output_frame_count": OUTPUT_FRAMES,
        "fps": OUTPUT_FPS,
        "duration_seconds": receipt["duration_seconds"],
        "source_frame_step": receipt["source_frame_step"],
        "total_seconds": total_seconds,
        "metal_devices": metal_settings["metal_devices"],
        "source_030_blend_sha256": EXPECTED_BLEND_SHA256,
    }, indent=2))


if __name__ == "__main__":
    main()
