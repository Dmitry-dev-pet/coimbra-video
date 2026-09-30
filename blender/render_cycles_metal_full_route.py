"""028: render the accepted 026 full route with Cycles GPU / Apple Metal.

This is a render-only lane. It opens the exact accepted 026 packed scene, verifies
the accepted scene/camera hashes, changes only the Cycles execution device to
GPU / Metal, renders native frames 1..360, and records per-frame/shard timing
and hashes.
"""
from __future__ import annotations

import argparse
import json
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

FRAMES = 360
SHARD_SIZE = 30


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :]
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--prepare", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    frames_dir = args.out / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    prepare = json.loads(args.prepare.read_text())
    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene = bpy.context.scene

    metal027.verify_frozen_source(scene, args.blend, prepare)
    cpu_settings = metal027.accepted_cpu_settings(scene)

    before_protected = full.protected_digest(scene)
    before_cameras = full.camera_records(scene)
    metal_settings = metal027.configure_metal(scene, cpu_settings)

    frame_receipts: dict[str, dict] = {}
    shard_receipts: list[dict] = []
    started_total = time.perf_counter()

    for shard_start in range(1, FRAMES + 1, SHARD_SIZE):
        shard_end = min(FRAMES, shard_start + SHARD_SIZE - 1)
        shard_started = time.perf_counter()
        shard_frames: dict[str, dict] = {}

        for frame in range(shard_start, shard_end + 1):
            scene.frame_set(frame)
            path = frames_dir / f"frame_{frame:04d}.png"
            started = time.perf_counter()
            backend.render_png(scene, path)
            elapsed = time.perf_counter() - started

            item = {
                "sha256": full.digest_file(path),
                "bytes": path.stat().st_size,
                "seconds": elapsed,
            }
            frame_receipts[str(frame)] = item
            shard_frames[str(frame)] = item
            print(f"metal frame {frame}: {elapsed:.3f}s")

        shard_receipts.append(
            {
                "start": shard_start,
                "end": shard_end,
                "seconds": time.perf_counter() - shard_started,
                "frames": shard_frames,
            }
        )

    total_seconds = time.perf_counter() - started_total

    if full.protected_digest(scene) != before_protected:
        raise RuntimeError("Metal full-route render changed protected scene state")
    if full.camera_records(scene) != before_cameras:
        raise RuntimeError("Metal full-route render changed camera path")

    receipt = {
        "version": "coimbra-028-metal-full-route-v1",
        "source_026_run": metal027.EXPECTED_026_RUN,
        "source_025_commit": metal027.EXPECTED_SOURCE_025,
        "source_code_commit": os.environ.get("COIMBRA_SOURCE_SHA", "local"),
        "blend_sha256": metal027.EXPECTED_BLEND_SHA256,
        "protected_sha256": metal027.EXPECTED_PROTECTED_SHA256,
        "resolution": metal027.EXPECTED_RESOLUTION,
        "frame_count": FRAMES,
        "fps": 30,
        "duration_seconds": 12.0,
        "scene_unchanged": True,
        "camera_unchanged": True,
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
        "frame_count": FRAMES,
        "total_seconds": total_seconds,
        "metal_devices": metal_settings["metal_devices"],
    }, indent=2))


if __name__ == "__main__":
    main()
