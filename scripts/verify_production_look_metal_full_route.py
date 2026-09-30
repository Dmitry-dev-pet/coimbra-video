"""Blender-free acceptance of Coimbra 031 production-look Metal delivery."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

EXPECTED_030_RUN = 36720891074
EXPECTED_030_REVISION = "v2-shadow-recovery"
EXPECTED_BLEND_SHA256 = "5fe8ca9e8605c6ea1908d8a814f9ad5209248c606b34ebbbb3dd47607edff881"
EXPECTED_STRUCTURE_SHA256 = "c3e599c7d27547527c6d6b430b7aaed8c8103c297d93c68fc66eef0c194d02da"
EXPECTED_026_RUN = 36646652931
EXPECTED_FRAMES = list(range(1, 361))
EXPECTED_RESOLUTION = [1600, 1000]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(receipt: dict, probe: dict) -> dict:
    require(receipt["version"] == "coimbra-031-production-look-metal-full-route-v1", "Unknown receipt schema")
    require(receipt["source_030_run"] == EXPECTED_030_RUN, "Wrong 030 source run")
    require(receipt["source_030_revision"] == EXPECTED_030_REVISION, "Wrong 030 revision")
    require(receipt["source_030_blend_sha256"] == EXPECTED_BLEND_SHA256, "Wrong accepted 030 blend")
    require(receipt["source_030_structure_sha256"] == EXPECTED_STRUCTURE_SHA256, "Wrong accepted structure")
    require(receipt["source_026_run"] == EXPECTED_026_RUN, "Wrong underlying 026 run")
    require(receipt["resolution"] == EXPECTED_RESOLUTION, "Resolution changed")
    require(receipt["frame_count"] == 360 and receipt["fps"] == 30, "Native timing changed")
    require(math.isclose(receipt["duration_seconds"], 12.0, abs_tol=1e-9), "Duration changed")
    require(receipt["scene_unchanged"] is True, "Visual state changed during render")
    require(receipt["structure_unchanged"] is True, "Structure changed during render")
    require(receipt["camera_unchanged"] is True, "Camera changed during render")

    protected = receipt.get("source_030_protected_sha256")
    require(
        isinstance(protected, str)
        and len(protected) == 64
        and all(c in "0123456789abcdef" for c in protected),
        "Invalid accepted 030 protected-state SHA",
    )

    metal = receipt["metal"]
    settings = metal["settings"]
    require(settings["device"] == "GPU", "031 is not a GPU render")
    require(settings["compute_device_type"] == "METAL", "Metal backend not selected")
    require(bool(settings["metal_devices"]), "No Metal device recorded")
    require(settings["samples"] == 16, "Samples changed")
    require(settings["use_denoising"] is True, "Denoising changed")
    require(settings["use_adaptive_sampling"] is True, "Adaptive sampling changed")
    require(metal["total_seconds"] > 0, "Non-positive render time")

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
    require(len(shards) == 12, "Exactly 12 logical shards required")
    covered = []
    for index, shard in enumerate(shards):
        expected_start = index * 30 + 1
        expected_end = expected_start + 29
        require(
            shard["start"] == expected_start and shard["end"] == expected_end,
            f"Shard {index + 1}: wrong bounds",
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
    require([int(stream["width"]), int(stream["height"])] == EXPECTED_RESOLUTION, "Delivery resolution changed")
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
        "source_030_blend_sha256": receipt["source_030_blend_sha256"],
        "source_030_structure_sha256": receipt["source_030_structure_sha256"],
        "source_030_protected_sha256": protected,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root

    receipt = json.loads((root / "render-receipt.json").read_text())
    probe = json.loads((root / "ffprobe.json").read_text())
    result = validate(receipt, probe)

    video = root / "coimbra-production-look-metal-12s.mp4"
    require(video.is_file() and video.stat().st_size > 0, "Missing final video")
    result["video_sha256"] = hashlib.sha256(video.read_bytes()).hexdigest()

    attribution = (root / "attribution.txt").read_text().strip()
    require("OpenStreetMap" in attribution and "DGT" in attribution, "Missing attribution")
    result["attribution"] = attribution

    for frame in (1, 181, 360):
        require((root / "review" / f"frame-{frame:03d}.png").is_file(), f"Missing review frame {frame}")

    (root / "verification.json").write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
