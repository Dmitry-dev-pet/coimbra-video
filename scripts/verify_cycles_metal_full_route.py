"""Blender-free acceptance of Coimbra 028 full-route Metal delivery."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

EXPECTED_BLEND_SHA256 = "5eed3da289693015ed6b491eb26f992f0c579a1625540f1f4acc13155860a590"
EXPECTED_PROTECTED_SHA256 = "98ee88d4c6e28dfccb010b7ad9faa89f88466768eed7ec440fb96d99b276450f"
EXPECTED_SOURCE_025 = "d178382d10eef41ec00da3fe562fcc445438f8da"
EXPECTED_026_RUN = 36646652931
EXPECTED_FRAMES = list(range(1, 361))
EXPECTED_RESOLUTION = [1600, 1000]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(receipt: dict, probe: dict) -> dict:
    require(receipt["version"] == "coimbra-028-metal-full-route-v1", "Unknown receipt schema")
    require(receipt["source_026_run"] == EXPECTED_026_RUN, "Wrong 026 source run")
    require(receipt["source_025_commit"] == EXPECTED_SOURCE_025, "Wrong 025 source commit")
    require(receipt["blend_sha256"] == EXPECTED_BLEND_SHA256, "Wrong frozen blend")
    require(receipt["protected_sha256"] == EXPECTED_PROTECTED_SHA256, "Wrong protected scene")
    require(receipt["resolution"] == EXPECTED_RESOLUTION, "Resolution changed")
    require(receipt["frame_count"] == 360 and receipt["fps"] == 30, "Native timing changed")
    require(math.isclose(receipt["duration_seconds"], 12.0, abs_tol=1e-9), "Duration contract changed")
    require(receipt["scene_unchanged"] is True, "Scene changed")
    require(receipt["camera_unchanged"] is True, "Camera changed")

    metal = receipt["metal"]
    settings = metal["settings"]
    require(settings["device"] == "GPU", "Metal render is not GPU")
    require(settings["compute_device_type"] == "METAL", "Metal backend not selected")
    require(bool(settings["metal_devices"]), "No Metal device recorded")
    require(settings["samples"] == 16, "Samples changed")
    require(settings["use_denoising"] is True, "Denoising changed")
    require(settings["use_adaptive_sampling"] is True, "Adaptive sampling changed")
    require(metal["total_seconds"] > 0, "Non-positive total render time")

    frames = metal["frames"]
    require(sorted(map(int, frames)) == EXPECTED_FRAMES, "Missing or extra frame receipts")
    for frame, item in frames.items():
        require(item["seconds"] > 0, f"Frame {frame}: non-positive render time")
        require(item["bytes"] > 0, f"Frame {frame}: empty image")
        digest = item["sha256"]
        require(
            len(digest) == 64 and all(c in "0123456789abcdef" for c in digest),
            f"Frame {frame}: invalid SHA-256",
        )

    shards = metal["shards"]
    require(len(shards) == 12, "Exactly 12 render shards required")
    covered: list[int] = []
    for index, shard in enumerate(shards):
        expected_start = index * 30 + 1
        expected_end = expected_start + 29
        require(
            shard["start"] == expected_start and shard["end"] == expected_end,
            f"Shard {index + 1}: wrong frame bounds",
        )
        require(shard["seconds"] > 0, f"Shard {index + 1}: non-positive time")
        shard_frames = sorted(map(int, shard["frames"]))
        require(
            shard_frames == list(range(expected_start, expected_end + 1)),
            f"Shard {index + 1}: incomplete frame set",
        )
        covered.extend(shard_frames)
    require(covered == EXPECTED_FRAMES, "Shard coverage is not exactly 1..360")

    stream = probe["streams"][0]
    require(stream["codec_name"] == "h264", "Delivery is not H.264")
    require(stream["pix_fmt"] == "yuv420p", "Delivery pixel format changed")
    require(
        [int(stream["width"]), int(stream["height"])] == EXPECTED_RESOLUTION,
        "Delivery resolution changed",
    )
    require(stream["r_frame_rate"] == "30/1", "Delivery FPS changed")
    require(int(stream["nb_read_frames"]) == 360, "Delivery does not decode to 360 frames")
    require(
        math.isclose(float(probe["format"]["duration"]), 12.0, abs_tol=0.04),
        "Delivery duration is not 12 seconds",
    )

    return {
        "verified": True,
        "frame_count": 360,
        "fps": 30,
        "duration_seconds": 12.0,
        "resolution": EXPECTED_RESOLUTION,
        "metal_total_seconds": metal["total_seconds"],
        "metal_devices": settings["metal_devices"],
        "blend_sha256": receipt["blend_sha256"],
        "protected_sha256": receipt["protected_sha256"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()

    root = args.root
    receipt = json.loads((root / "render-receipt.json").read_text())
    probe = json.loads((root / "ffprobe.json").read_text())
    result = validate(receipt, probe)

    video = root / "coimbra-metal-full-route-12s.mp4"
    require(video.is_file() and video.stat().st_size > 0, "Missing final video")
    result["video_sha256"] = hashlib.sha256(video.read_bytes()).hexdigest()

    attribution = (root / "attribution.txt").read_text().strip()
    require("OpenStreetMap" in attribution and "DGT" in attribution, "Missing attribution")
    result["attribution"] = attribution

    for frame in (1, 181, 360):
        require(
            (root / "review" / f"frame-{frame:03d}.png").is_file(),
            f"Missing decoded review frame {frame}",
        )

    (root / "verification.json").write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
