"""Blender-free verifier for Coimbra 035 visual-polish review."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

EXPECTED_030_RUN = 36720891074
EXPECTED_026_RUN = 36646652931
EXPECTED_BLEND_SHA256 = "5fe8ca9e8605c6ea1908d8a814f9ad5209248c606b34ebbbb3dd47607edff881"
EXPECTED_STRUCTURE_SHA256 = "c3e599c7d27547527c6d6b430b7aaed8c8103c297d93c68fc66eef0c194d02da"
EXPECTED_CHECKPOINTS = [121, 421, 721, 1021, 1321]
EXPECTED_VARIANTS = ["baseline", "motion_blur", "atmosphere_light", "quality64"]
EXPECTED_RESOLUTION = [1600, 1000]
EXPECTED_SOURCE_STEP = 359 / 1439
EXPECTED_SHUTTER = EXPECTED_SOURCE_STEP * 0.5


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(a, b, tol=1e-9):
    return math.isclose(float(a), float(b), abs_tol=tol)


def expected_source(output_frame: int) -> float:
    return 1.0 + (output_frame - 1) * 359.0 / 1439.0


def validate_camera(expected: dict, actual: dict, label: str) -> None:
    require(expected == actual, f"{label}: camera state differs from accepted 032 checkpoint")


def validate(receipt: dict) -> dict:
    require(receipt["version"] == "coimbra-035-visual-polish-review-v1", "Wrong 035 schema")
    require(receipt["source_030_run"] == EXPECTED_030_RUN, "Wrong 030 source run")
    require(receipt["source_026_run"] == EXPECTED_026_RUN, "Wrong 026 source run")
    require(receipt["source_030_blend_sha256"] == EXPECTED_BLEND_SHA256, "Wrong 030 blend")
    require(receipt["source_030_structure_sha256"] == EXPECTED_STRUCTURE_SHA256, "Wrong 030 structure")
    require(receipt["accepted_lane"] == "Coimbra 032", "035 is not based on accepted 032")
    require("unchanged accepted 032" in receipt["camera_timing_policy"], "035 camera/timing policy changed")
    require(receipt["output_fps_reference"] == 60, "Wrong 032 fps reference")
    require(close(receipt["output_duration_reference_seconds"], 24.0), "Wrong 032 duration reference")
    require(receipt["checkpoint_output_frames"] == EXPECTED_CHECKPOINTS, "Wrong 035 checkpoints")
    require(receipt["resolution"] == EXPECTED_RESOLUTION, "Wrong 035 resolution")

    require(receipt["scene_restored"] is True, "035 did not restore scene state")
    require(receipt["structure_unchanged"] is True, "035 changed structure")
    require(receipt["camera_unchanged"] is True, "035 changed accepted camera")
    require(receipt["promotion"] == "human-review-required", "035 must remain review-only")

    baseline_cycles = receipt["baseline_cycles"]
    require(baseline_cycles["samples"] == 16, "Accepted baseline samples changed")
    require(baseline_cycles["use_denoising"] is True, "Accepted denoising changed")
    require(baseline_cycles["use_adaptive_sampling"] is True, "Accepted adaptive sampling changed")
    require(close(baseline_cycles["adaptive_threshold"], 0.08), "Accepted threshold changed")

    mapping = receipt["motion_blur_mapping"]
    require(close(mapping["source_frame_step"], EXPECTED_SOURCE_STEP), "Wrong 032 source-frame step")
    require(close(mapping["shutter_source_frames"], EXPECTED_SHUTTER), "Wrong 180-degree shutter mapping")
    require(close(mapping["shutter_output_frames"], 0.5), "Wrong output shutter fraction")
    require(close(mapping["shutter_angle_degrees"], 180.0), "Wrong shutter angle")

    checkpoints = receipt["checkpoint_evidence"]
    require(set(checkpoints) == {str(x) for x in EXPECTED_CHECKPOINTS}, "Checkpoint evidence incomplete")
    for output_frame in EXPECTED_CHECKPOINTS:
        item = checkpoints[str(output_frame)]
        require(item["output_frame"] == output_frame, f"Checkpoint {output_frame}: wrong output frame")
        require(close(item["source_frame"], expected_source(output_frame), 1e-8), f"Checkpoint {output_frame}: wrong source frame")
        require(len(item["camera"]["location"]) == 3, f"Checkpoint {output_frame}: bad camera location")
        require(len(item["camera"]["quaternion"]) == 4, f"Checkpoint {output_frame}: bad camera quaternion")

    variants = receipt["variants"]
    require(list(variants) == EXPECTED_VARIANTS, "Wrong 035 variant order/set")

    baseline_settings = receipt["baseline_settings"]
    require(baseline_settings["samples"] == 16, "Baseline snapshot samples changed")
    require(close(baseline_settings["adaptive_threshold"], 0.08), "Baseline snapshot threshold changed")
    require(baseline_settings["render_use_motion_blur"] is False, "Baseline unexpectedly uses motion blur")

    for variant in EXPECTED_VARIANTS:
        payload = variants[variant]
        require(payload["total_seconds"] > 0, f"{variant}: invalid render time")
        images = payload["images"]
        require(set(images) == {str(x) for x in EXPECTED_CHECKPOINTS}, f"{variant}: incomplete images")
        for output_frame in EXPECTED_CHECKPOINTS:
            item = images[str(output_frame)]
            require(item["output_frame"] == output_frame, f"{variant}/{output_frame}: wrong output frame")
            require(close(item["source_frame"], expected_source(output_frame), 1e-8), f"{variant}/{output_frame}: wrong source sample")
            require(len(item["sha256"]) == 64, f"{variant}/{output_frame}: invalid image hash")
            require(int(item["bytes"]) > 0, f"{variant}/{output_frame}: empty image")
            require(float(item["seconds"]) > 0, f"{variant}/{output_frame}: invalid timing")
            validate_camera(
                checkpoints[str(output_frame)]["camera"],
                item["camera"],
                f"{variant}/{output_frame}",
            )

    base = variants["baseline"]["settings"]
    require(base["name"] == "baseline", "Wrong baseline label")
    require(base["samples"] == 16, "Baseline review samples changed")
    require(close(base["adaptive_threshold"], 0.08), "Baseline review threshold changed")
    require(base["motion_blur"] is False, "Baseline review motion blur changed")
    require(close(base["atmosphere_density"], 0.0), "Baseline review atmosphere changed")

    blur = variants["motion_blur"]["settings"]
    require(blur["motion_blur"] is True, "Motion-blur variant disabled")
    require(blur["motion_blur_position"] == "CENTER", "Motion-blur position changed")
    require(close(blur["motion_blur_shutter_source_frames"], EXPECTED_SHUTTER), "Motion-blur shutter changed")
    require(close(blur["motion_blur_shutter_output_frames"], 0.5), "Motion-blur output mapping changed")
    require(close(blur["motion_blur_angle_degrees"], 180.0), "Motion-blur angle changed")
    require(blur["samples"] == 16, "Motion-blur variant changed sampling")
    require(close(blur["atmosphere_density"], 0.0), "Motion-blur variant added atmosphere")

    atmosphere = variants["atmosphere_light"]["settings"]
    require(atmosphere["samples"] == 16, "Atmosphere variant changed sampling")
    require(atmosphere["motion_blur"] is False, "Atmosphere variant added motion blur")
    require(close(atmosphere["atmosphere_density"], 0.00015), "Atmosphere density changed")
    require(close(atmosphere["atmosphere_anisotropy"], 0.18), "Atmosphere anisotropy changed")
    require(close(atmosphere["background_strength"], 0.68), "Atmosphere background changed")
    require(close(atmosphere["sun_energy"], 1.65), "Atmosphere sun energy changed")
    require(close(atmosphere["sun_angle_deg"], 10.0), "Atmosphere sun angle changed")
    require(close(atmosphere["fill_energy"], 900.0), "Atmosphere fill changed")

    quality = variants["quality64"]["settings"]
    require(quality["samples"] == 64, "Quality variant samples changed")
    require(close(quality["adaptive_threshold"], 0.03), "Quality variant threshold changed")
    require(quality["motion_blur"] is False, "Quality variant added motion blur")
    require(close(quality["atmosphere_density"], 0.0), "Quality variant added atmosphere")

    baseline_images = variants["baseline"]["images"]
    changed_counts = {}
    for variant in ("motion_blur", "atmosphere_light", "quality64"):
        count = sum(
            variants[variant]["images"][key]["sha256"] != baseline_images[key]["sha256"]
            for key in baseline_images
        )
        require(count >= 4, f"{variant}: too few images differ from baseline ({count}/5)")
        changed_counts[variant] = count

    return {
        "verified": True,
        "production_acceptance": False,
        "human_review_required": True,
        "accepted_lane": "Coimbra 032",
        "checkpoints": EXPECTED_CHECKPOINTS,
        "variants": EXPECTED_VARIANTS,
        "changed_counts": changed_counts,
        "motion_blur_shutter_source_frames": EXPECTED_SHUTTER,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("review", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    receipt = json.loads(args.review.read_text())
    result = validate(receipt)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
