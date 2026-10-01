"""Blender-free acceptance of Coimbra 036 quality64 slow60 Metal delivery."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import verify_production_look_slow60_metal as base032

EXPECTED_035_REVIEW_RUN = 36892916114
EXPECTED_035_SOURCE_SHA = "5a76e767d8b95578a9e999b4803176812a78b3a6"
EXPECTED_SAMPLES = 64
EXPECTED_ADAPTIVE_THRESHOLD = 0.03


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(receipt: dict, probe: dict) -> dict:
    require(receipt["version"] == "coimbra-036-quality64-slow60-metal-v1", "Unknown 036 receipt schema")
    require(receipt["source_035_review_run"] == EXPECTED_035_REVIEW_RUN, "Wrong 035 review run")
    require(receipt["source_035_review_commit"] == EXPECTED_035_SOURCE_SHA, "Wrong 035 reviewed source")
    require(receipt["quality64_review_verified"] is True, "035 quality64 review not recorded as verified")
    require(receipt["quality64_samples"] == EXPECTED_SAMPLES, "Wrong promoted sample count")
    require(
        math.isclose(receipt["quality64_adaptive_threshold"], EXPECTED_ADAPTIVE_THRESHOLD, abs_tol=1e-9),
        "Wrong promoted adaptive threshold",
    )
    require(receipt["motion_blur"] is False, "036 must not promote motion blur")
    require(receipt["atmosphere_light"] is False, "036 must not promote atmosphere/light variant")
    require(receipt["sampling_restored"] is True, "036 did not restore accepted sampling state")

    settings = receipt["metal"]["settings"]
    require(settings["samples"] == EXPECTED_SAMPLES, "036 render is not 64 samples")
    require(
        math.isclose(float(settings["adaptive_threshold"]), EXPECTED_ADAPTIVE_THRESHOLD, abs_tol=1e-6),
        "036 render adaptive threshold is not 0.03",
    )
    require(settings["use_denoising"] is True, "036 denoising changed")
    require(settings["use_adaptive_sampling"] is True, "036 adaptive sampling changed")

    normalized = deepcopy(receipt)
    normalized["version"] = "coimbra-032-slow60-production-look-metal-v1"
    normalized["metal"]["settings"]["samples"] = 16
    normalized["metal"]["settings"]["adaptive_threshold"] = 0.08
    base = base032.validate(normalized, probe)

    base.update({
        "version": receipt["version"],
        "source_035_review_run": EXPECTED_035_REVIEW_RUN,
        "source_035_review_commit": EXPECTED_035_SOURCE_SHA,
        "samples": EXPECTED_SAMPLES,
        "adaptive_threshold": EXPECTED_ADAPTIVE_THRESHOLD,
        "motion_blur": False,
        "atmosphere_light": False,
        "quality64_promoted": True,
    })
    return base


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root

    receipt = json.loads((root / "render-receipt.json").read_text())
    probe = json.loads((root / "ffprobe.json").read_text())
    result = validate(receipt, probe)

    video = root / "coimbra-production-look-slow60-quality64-metal-24s.mp4"
    require(video.is_file() and video.stat().st_size > 0, "Missing final 036 video")
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
