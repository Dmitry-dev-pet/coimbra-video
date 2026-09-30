"""027: compare accepted 026 Cycles CPU checkpoints with Apple Metal.

This lane is render-only. It opens the exact accepted 026 packed scene, verifies
its checksum/protected state/camera records, renders the same three checkpoints
on CPU and Metal, and records timing + image hashes. It never rebuilds or edits
scene geometry, materials, lights, world state, or camera animation.
"""
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

FRAMES = (1, 181, 360)
EXPECTED_SOURCE_025 = "d178382d10eef41ec00da3fe562fcc445438f8da"
EXPECTED_026_RUN = 36646652931
EXPECTED_BLEND_SHA256 = "5eed3da289693015ed6b491eb26f992f0c579a1625540f1f4acc13155860a590"
EXPECTED_PROTECTED_SHA256 = "98ee88d4c6e28dfccb010b7ad9faa89f88466768eed7ec440fb96d99b276450f"
EXPECTED_RESOLUTION = [1600, 1000]


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :]
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--prepare", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args(argv)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def verify_frozen_source(scene, blend: Path, prepare: dict) -> None:
    require(full.digest_file(blend) == EXPECTED_BLEND_SHA256, "Unexpected 026 blend SHA-256")
    require(prepare.get("blend_sha256") == EXPECTED_BLEND_SHA256, "026 manifest blend SHA mismatch")
    require(
        prepare.get("protected_sha256") == EXPECTED_PROTECTED_SHA256,
        "026 manifest protected-state SHA mismatch",
    )
    require(
        prepare.get("source_025_commit") == EXPECTED_SOURCE_025,
        "026 manifest does not point at accepted 025 source",
    )
    require(prepare.get("resolution") == EXPECTED_RESOLUTION, "026 resolution changed")
    require(prepare.get("frame_count") == 360 and prepare.get("fps") == 30, "026 timing changed")

    protected = full.protected_digest(scene)
    require(protected == EXPECTED_PROTECTED_SHA256, "Loaded scene protected state differs from 026")
    require(full.camera_records(scene) == prepare.get("cameras"), "Loaded camera path differs from 026")


def accepted_cpu_settings(scene) -> dict:
    settings = full.check_cycles(scene)
    expected = {
        "device": "CPU",
        "samples": 16,
        "use_denoising": True,
        "use_adaptive_sampling": True,
        "adaptive_threshold": 0.08,
        "max_bounces": 6,
        "diffuse_bounces": 3,
        "glossy_bounces": 3,
        "transmission_bounces": 2,
    }
    for key, value in expected.items():
        actual = settings.get(key)
        if isinstance(value, float):
            require(
                isinstance(actual, (int, float)) and math.isclose(float(actual), value, abs_tol=1e-6),
                f"CPU Cycles setting changed: {key}={actual!r}",
            )
        else:
            require(actual == value, f"CPU Cycles setting changed: {key}={actual!r}")
    return settings


def configure_metal(scene, cpu_settings: dict) -> dict:
    addon = bpy.context.preferences.addons.get("cycles")
    require(addon is not None, "Cycles addon unavailable")

    prefs = addon.preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()

    metal_devices = []
    for device in prefs.devices:
        enabled = device.type == "METAL"
        device.use = enabled
        if enabled:
            metal_devices.append(device.name)

    require(metal_devices, "No Cycles METAL device detected")

    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"

    # Keep every accepted 026 sampling/bounce setting unchanged.
    require(scene.cycles.samples == cpu_settings["samples"], "Metal switch changed samples")
    require(scene.cycles.use_denoising == cpu_settings["use_denoising"], "Metal switch changed denoising")
    require(
        scene.cycles.use_adaptive_sampling == cpu_settings["use_adaptive_sampling"],
        "Metal switch changed adaptive sampling",
    )

    return {
        **cpu_settings,
        "device": "GPU",
        "compute_device_type": "METAL",
        "metal_devices": metal_devices,
    }


def render_frames(scene, frames: tuple[int, ...], out_dir: Path, label: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    timings = {}
    images = {}

    for frame in frames:
        scene.frame_set(frame)
        path = out_dir / f"frame-{frame:03d}-{label}.png"
        started = time.perf_counter()
        backend.render_png(scene, path)
        elapsed = time.perf_counter() - started
        timings[str(frame)] = elapsed
        images[str(frame)] = {
            "path": path.name,
            "sha256": full.digest_file(path),
            "bytes": path.stat().st_size,
        }
        print(f"{label} frame {frame}: {elapsed:.3f}s")

    return {
        "timings_seconds": timings,
        "total_seconds": sum(timings.values()),
        "images": images,
    }


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    prepare = json.loads(args.prepare.read_text())
    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene = bpy.context.scene
    verify_frozen_source(scene, args.blend, prepare)

    before_protected = full.protected_digest(scene)
    before_cameras = full.camera_records(scene)

    cpu_settings = accepted_cpu_settings(scene)
    cpu = render_frames(scene, FRAMES, args.out, "cpu")

    require(full.protected_digest(scene) == before_protected, "CPU render changed protected scene")
    require(full.camera_records(scene) == before_cameras, "CPU render changed camera path")

    metal_settings = configure_metal(scene, cpu_settings)
    metal = render_frames(scene, FRAMES, args.out, "metal")

    require(full.protected_digest(scene) == before_protected, "Metal render changed protected scene")
    require(full.camera_records(scene) == before_cameras, "Metal render changed camera path")

    speedup = cpu["total_seconds"] / metal["total_seconds"]
    receipt = {
        "version": "coimbra-027-metal-checkpoints-v1",
        "source_026_run": EXPECTED_026_RUN,
        "source_025_commit": EXPECTED_SOURCE_025,
        "source_code_commit": os.environ.get("COIMBRA_SOURCE_SHA", "local"),
        "blend_sha256": EXPECTED_BLEND_SHA256,
        "protected_sha256": EXPECTED_PROTECTED_SHA256,
        "resolution": EXPECTED_RESOLUTION,
        "frames": list(FRAMES),
        "scene_unchanged": True,
        "camera_unchanged": True,
        "cpu": {"settings": cpu_settings, **cpu},
        "metal": {"settings": metal_settings, **metal},
        "speedup_cpu_over_metal": speedup,
    }
    (args.out / "render-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
