"""Blender-free acceptance of Coimbra 032 slow60 production-look Metal delivery."""
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
EXPECTED_OUTPUT_FRAMES = list(range(1, 1441))
EXPECTED_RESOLUTION = [1600, 1000]
EXPECTED_SOURCE_STEP = 359 / 1439


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(receipt: dict, probe: dict) -> dict:
    require(receipt["version"] == "coimbra-032-slow60-production-look-metal-v1", "Unknown receipt schema")
    require(receipt["source_030_run"] == EXPECTED_030_RUN, "Wrong 030 source run")
    require(receipt["source_030_revision"] == EXPECTED_030_REVISION, "Wrong 030 revision")
    require(receipt["source_030_blend_sha256"] == EXPECTED_BLEND_SHA256, "Wrong accepted 030 blend")
    require(receipt["source_030_structure_sha256"] == EXPECTED_STRUCTURE_SHA256, "Wrong accepted structure")
    require(receipt["source_026_run"] == EXPECTED_026_RUN, "Wrong underlying 026 run")
    require(receipt["resolution"] == EXPECTED_RESOLUTION, "Resolution changed")
    require(receipt["source_frame_count"] == 360, "Source route frame count changed")
    require(receipt["output_frame_count"] == 1440 and receipt["fps"] == 60, "032 timing changed")
    require(math.isclose(receipt["duration_seconds"], 24.0, abs_tol=1e-9), "Duration changed")
    require(math.isclose(receipt["speed_ratio_vs_031"], 0.5, abs_tol=1e-9), "Speed ratio changed")
    require(math.isclose(receipt["source_frame_start"], 1.0, abs_tol=1e-9), "Wrong source start")
    require(math.isclose(receipt["source_frame_end"], 360.0, abs_tol=1e-9), "Wrong source end")
    require(math.isclose(receipt["source_frame_step"], EXPECTED_SOURCE_STEP, abs_tol=1e-12), "Wrong source step")
    require(receipt["sampling"] == "native Blender fractional-frame evaluation", "Wrong sampling method")
    require(receipt["repeated_frames"] is False, "Repeated frames are forbidden")
    require(receipt["optical_flow"] is False, "Optical flow is forbidden")
    require(receipt["scene_unchanged"] is True, "Visual state changed during render")
    require(receipt["structure_unchanged"] is True, "Structure changed during render")
    require(receipt["native_camera_path_unchanged"] is True, "Native camera path changed")

    protected = receipt.get("source_030_protected_sha256")
    require(
        isinstance(protected, str)
        and len(protected) == 64
        and all(c in "0123456789abcdef" for c in protected),
        "Invalid accepted 030 protected-state SHA",
    )

    metal = receipt["metal"]
    settings = metal["settings"]
    require(settings["device"] == "GPU", "032 is not a GPU render")
    require(settings["compute_device_type"] == "METAL", "Metal backend not selected")
    require(bool(settings["metal_devices"]), "No Metal device recorded")
    require(settings["samples"] == 16, "Samples changed")
    require(settings["use_denoising"] is True, "Denoising changed")
    require(settings["use_adaptive_sampling"] is True, "Adaptive sampling changed")
    require(metal["total_seconds"] > 0, "Non-positive render time")

    frames = metal["frames"]
    require(sorted(map(int, frames)) == EXPECTED_OUTPUT_FRAMES, "Missing or extra output frame receipts")
    previous_source = None
    for output_frame in EXPECTED_OUTPUT_FRAMES:
        item = frames[str(output_frame)]
        expected_source = 1.0 + (output_frame - 1) * EXPECTED_SOURCE_STEP
        require(math.isclose(item["source_frame"], expected_source, abs_tol=1e-9), f"Frame {output_frame}: wrong source sample")
        require(item["seconds"] > 0, f"Frame {output_frame}: non-positive render time")
        require(item["bytes"] > 0, f"Frame {output_frame}: empty image")
        digest = item["sha256"]
        require(
            len(digest) == 64 and all(c in "0123456789abcdef" for c in digest),
            f"Frame {output_frame}: invalid SHA-256",
        )
        if previous_source is not None:
            require(item["source_frame"] > previous_source, f"Frame {output_frame}: non-monotonic route sample")
        previous_source = item["source_frame"]

    require(math.isclose(frames["1"]["source_frame"], 1.0, abs_tol=1e-9), "First sample changed")
    require(math.isclose(frames["1440"]["source_frame"], 360.0, abs_tol=1e-9), "Last sample changed")

    shards = metal["shards"]
    require(len(shards) == 12, "Exactly 12 logical shards required")
    covered = []
    for index, shard in enumerate(shards):
        expected_start = index * 120 + 1
        expected_end = expected_start + 119
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
    require(covered == EXPECTED_OUTPUT_FRAMES, "Shard coverage is not exactly 1..1440")

    stream = probe["streams"][0]
    require(stream["codec_name"] == "h264", "Delivery is not H.264")
    require(stream["pix_fmt"] == "yuv420p", "Delivery pixel format changed")
    require([int(stream["width"]), int(stream["height"])] == EXPECTED_RESOLUTION, "Delivery resolution changed")
    require(stream["r_frame_rate"] == "60/1", "Delivery FPS changed")
    require(int(stream["nb_read_frames"]) == 1440, "Delivery does not decode to 1440 frames")
    require(
        math.isclose(float(probe["format"]["duration"]), 24.0, abs_tol=0.04),
        "Delivery duration is not 24 seconds",
    )

    return {
        "verified": True,
        "frame_count": 1440,
        "fps": 60,
        "duration_seconds": 24.0,
        "speed_ratio_vs_031": 0.5,
        "source_frame_step": EXPECTED_SOURCE_STEP,
        "sampling": receipt["sampling"],
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

    video = root / "coimbra-production-look-slow60-metal-24s.mp4"
    require(video.is_file() and video.stat().st_size > 0, "Missing final video")
    result["video_sha256"] = hashlib.sha256(video.read_bytes()).hexdigest()

    attribution = (root / "attribution.txt").read_text().strip()
    require("OpenStreetMap" in attribution and "DGT" in attribution, "Missing attribution")
    result["attribution"] = attribution

    for frame in (1, 361, 721, 1081, 1440):
        require((root / "review" / f"frame-{frame:04d}.png").is_file(), f"Missing review frame {frame}")

    (root / "verification.json").write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
