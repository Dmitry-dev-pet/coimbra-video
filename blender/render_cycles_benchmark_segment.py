"""029: benchmark one frozen Coimbra segment across Cycles device modes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))

import render_backend_comparison as backend
import render_cycles_full_route as full
import render_cycles_metal_checkpoints as metal027


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :]
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--prepare", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu", "metal", "metal-cpu"], required=True)
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    return parser.parse_args(argv)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def configure_metal_cpu(scene, cpu_settings: dict) -> dict:
    addon = bpy.context.preferences.addons.get("cycles")
    require(addon is not None, "Cycles addon unavailable")

    prefs = addon.preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()

    enabled = []
    metal_devices = []
    cpu_devices = []
    for device in prefs.devices:
        use = device.type in {"METAL", "CPU"}
        device.use = use
        if use:
            enabled.append({"name": device.name, "type": device.type})
            if device.type == "METAL":
                metal_devices.append(device.name)
            elif device.type == "CPU":
                cpu_devices.append(device.name)

    require(metal_devices, "No METAL device detected")
    require(cpu_devices, "No CPU device exposed to Cycles METAL backend")

    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    require(scene.cycles.samples == cpu_settings["samples"], "Hybrid switch changed samples")
    require(scene.cycles.use_denoising == cpu_settings["use_denoising"], "Hybrid switch changed denoising")
    require(
        scene.cycles.use_adaptive_sampling == cpu_settings["use_adaptive_sampling"],
        "Hybrid switch changed adaptive sampling",
    )

    return {
        **cpu_settings,
        "device": "GPU",
        "compute_device_type": "METAL+CPU",
        "metal_devices": metal_devices,
        "cpu_devices": cpu_devices,
        "enabled_devices": enabled,
    }


def main() -> None:
    args = parse_args()
    require(1 <= args.start <= args.end <= 360, "Invalid benchmark range")
    args.out.mkdir(parents=True, exist_ok=True)
    frames_dir = args.out / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    prepare = json.loads(args.prepare.read_text())
    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene = bpy.context.scene
    metal027.verify_frozen_source(scene, args.blend, prepare)

    before_protected = full.protected_digest(scene)
    before_cameras = full.camera_records(scene)
    cpu_settings = metal027.accepted_cpu_settings(scene)

    if args.device == "cpu":
        settings = dict(cpu_settings)
    elif args.device == "metal":
        settings = metal027.configure_metal(scene, cpu_settings)
    else:
        settings = configure_metal_cpu(scene, cpu_settings)

    timings = {}
    images = {}
    started_total = time.perf_counter()

    for frame in range(args.start, args.end + 1):
        scene.frame_set(frame)
        path = frames_dir / f"frame_{frame:04d}.png"
        started = time.perf_counter()
        backend.render_png(scene, path)
        elapsed = time.perf_counter() - started
        timings[str(frame)] = elapsed
        images[str(frame)] = {
            "sha256": full.digest_file(path),
            "bytes": path.stat().st_size,
        }
        print(f"benchmark {args.device} frame {frame}: {elapsed:.3f}s")

    total_seconds = time.perf_counter() - started_total
    require(full.protected_digest(scene) == before_protected, "Benchmark changed protected scene")
    require(full.camera_records(scene) == before_cameras, "Benchmark changed camera path")

    receipt = {
        "version": "coimbra-029-device-benchmark-v1",
        "device_mode": args.device,
        "start": args.start,
        "end": args.end,
        "frame_count": args.end - args.start + 1,
        "source_026_run": metal027.EXPECTED_026_RUN,
        "blend_sha256": metal027.EXPECTED_BLEND_SHA256,
        "protected_sha256": metal027.EXPECTED_PROTECTED_SHA256,
        "resolution": metal027.EXPECTED_RESOLUTION,
        "settings": settings,
        "total_seconds": total_seconds,
        "timings_seconds": timings,
        "images": images,
        "scene_unchanged": True,
        "camera_unchanged": True,
    }
    (args.out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({
        "device_mode": args.device,
        "frames": [args.start, args.end],
        "total_seconds": total_seconds,
    }, indent=2))


if __name__ == "__main__":
    main()
