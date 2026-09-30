"""Blender-free acceptance for the 027 Mac CPU-vs-Metal checkpoint run."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

EXPECTED_FRAMES = [1, 181, 360]
EXPECTED_RESOLUTION = [1600, 1000]
EXPECTED_BLEND_SHA256 = "5eed3da289693015ed6b491eb26f992f0c579a1625540f1f4acc13155860a590"
EXPECTED_PROTECTED_SHA256 = "98ee88d4c6e28dfccb010b7ad9faa89f88466768eed7ec440fb96d99b276450f"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(receipt: dict, comparison: dict) -> dict:
    require(receipt["version"] == "coimbra-027-metal-checkpoints-v1", "Unknown receipt schema")
    require(receipt["source_026_run"] == 36646652931, "Wrong 026 source run")
    require(receipt["blend_sha256"] == EXPECTED_BLEND_SHA256, "Wrong frozen blend")
    require(receipt["protected_sha256"] == EXPECTED_PROTECTED_SHA256, "Wrong protected scene")
    require(receipt["resolution"] == EXPECTED_RESOLUTION, "Resolution changed")
    require(receipt["frames"] == EXPECTED_FRAMES, "Checkpoint set changed")
    require(receipt["scene_unchanged"] is True, "Scene changed")
    require(receipt["camera_unchanged"] is True, "Camera changed")

    cpu = receipt["cpu"]
    metal = receipt["metal"]
    require(cpu["settings"]["device"] == "CPU", "CPU baseline not CPU")
    require(cpu["settings"]["samples"] == 16, "CPU samples changed")
    require(cpu["settings"]["use_denoising"] is True, "CPU denoising changed")
    require(cpu["settings"]["use_adaptive_sampling"] is True, "CPU adaptive sampling changed")

    require(metal["settings"]["device"] == "GPU", "Metal render not GPU")
    require(metal["settings"]["compute_device_type"] == "METAL", "Metal backend not selected")
    require(bool(metal["settings"]["metal_devices"]), "No Metal devices recorded")
    require(metal["settings"]["samples"] == 16, "Metal samples changed")

    for side in (cpu, metal):
        require(side["total_seconds"] > 0, "Non-positive render time")
        require(sorted(map(int, side["timings_seconds"])) == EXPECTED_FRAMES, "Missing timing")
        require(sorted(map(int, side["images"])) == EXPECTED_FRAMES, "Missing image receipt")
        for image in side["images"].values():
            digest = image["sha256"]
            require(len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), "Bad image hash")
            require(image["bytes"] > 0, "Empty image")

    require(
        math.isclose(
            receipt["speedup_cpu_over_metal"],
            cpu["total_seconds"] / metal["total_seconds"],
            rel_tol=1e-6,
        ),
        "Speedup does not match timing totals",
    )

    require(comparison["version"] == "coimbra-027-image-comparison-v1", "Unknown comparison schema")
    require(sorted(map(int, comparison["frames"])) == EXPECTED_FRAMES, "Comparison frames changed")
    for frame, metrics in comparison["frames"].items():
        require(metrics["size"] == EXPECTED_RESOLUTION, f"Frame {frame}: wrong dimensions")
        require(0 <= metrics["mean_abs_normalized"] <= 0.08, f"Frame {frame}: gross mean image drift")
        require(0 <= metrics["rms_normalized"] <= 0.15, f"Frame {frame}: gross RMS image drift")
        require(0 <= metrics["max_abs_normalized"] <= 1.0, f"Frame {frame}: invalid max difference")

    return {
        "verified": True,
        "frames": EXPECTED_FRAMES,
        "resolution": EXPECTED_RESOLUTION,
        "cpu_total_seconds": cpu["total_seconds"],
        "metal_total_seconds": metal["total_seconds"],
        "speedup_cpu_over_metal": receipt["speedup_cpu_over_metal"],
        "metal_devices": metal["settings"]["metal_devices"],
        "comparison": comparison["frames"],
        "blend_sha256": receipt["blend_sha256"],
        "protected_sha256": receipt["protected_sha256"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()

    result = validate(
        json.loads((args.root / "render-receipt.json").read_text()),
        json.loads((args.root / "image-comparison.json").read_text()),
    )
    (args.root / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
