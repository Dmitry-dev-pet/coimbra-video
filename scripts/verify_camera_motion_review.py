"""Blender-free verifier for Coimbra 033 camera-motion proxy review."""
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
EXPECTED_ANCHORS = [1, 61, 121, 181, 241, 301, 360]
EXPECTED_FRAMES = 1440
EXPECTED_FPS = 60
EXPECTED_DURATION = 24.0
EXPECTED_RESOLUTION = [960, 600]
EXPECTED_032_VIDEO_SHA256 = "7c34fd28a75d0cbb2aad76871238a0f9871439206fb43ead9f1e4e61574e05b7"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def vec_distance(a, b):
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def validate(receipt: dict, proxy_probe: dict, comparison_probe: dict | None = None) -> dict:
    require(receipt["version"] == "coimbra-033-smooth-camera-motion-review-v2", "Unknown 033 receipt schema")
    require(receipt["source_030_run"] == EXPECTED_030_RUN, "Wrong 030 source run")
    require(receipt["source_030_revision"] == EXPECTED_030_REVISION, "Wrong 030 revision")
    require(receipt["source_030_blend_sha256"] == EXPECTED_BLEND_SHA256, "Wrong 030 blend")
    require(receipt["source_030_structure_sha256"] == EXPECTED_STRUCTURE_SHA256, "Wrong 030 structure")
    require(receipt["source_026_run"] == EXPECTED_026_RUN, "Wrong 026 source")
    require(receipt["anchor_source_frames"] == EXPECTED_ANCHORS, "Anchor frames changed")
    require(receipt["scene_structure_unchanged"] is True, "033 changed accepted scene structure")
    require(receipt["native_camera_animation_unchanged"] is True, "033 changed native camera animation")

    anchors = receipt["anchors"]
    require(len(anchors) == len(EXPECTED_ANCHORS), "Wrong anchor count")
    for expected_frame, anchor in zip(EXPECTED_ANCHORS, anchors):
        require(anchor["source_frame"] == expected_frame, f"Anchor frame mismatch: {expected_frame}")
        require(len(anchor["location"]) == 3 and len(anchor["target"]) == 3, "Invalid anchor geometry")
        require(len(anchor["quaternion"]) == 4, "Invalid anchor quaternion")

    route = receipt["route_model"]
    require(route["position"].startswith("centripetal Catmull-Rom"), "Wrong position smoothing model")
    require(route["target"].startswith("centripetal Catmull-Rom"), "Wrong target smoothing model")
    require(route["speed"] == "global arc-length parameterization", "Wrong speed model")
    require(route["rotation"].startswith("look-at quaternion"), "Wrong rotation model")
    require(route["path_length"] > 0, "Invalid route length")
    require(len(route["segment_lengths"]) == 6, "Wrong segment count")
    require(len(route["segment_time_seconds"]) == 6, "Wrong segment timing count")
    segment_time_sum = sum(route["segment_time_seconds"])
    require(
        math.isclose(segment_time_sum, EXPECTED_DURATION, abs_tol=0.02),
        f"Segment timing diagnostic differs from 24 seconds: {segment_time_sum}",
    )

    delivery = receipt["delivery"]
    require(delivery["frame_count"] == EXPECTED_FRAMES, "Wrong 033 frame count")
    require(delivery["fps"] == EXPECTED_FPS, "Wrong 033 fps")
    require(math.isclose(delivery["duration_seconds"], EXPECTED_DURATION, abs_tol=1e-9), "Wrong 033 duration")
    require(delivery["resolution"] == EXPECTED_RESOLUTION, "Wrong proxy resolution")
    require(delivery["motion_blur"] is False, "033 review must isolate path smoothing before motion blur")
    require("motion-only proxy review" in delivery["purpose"], "033 incorrectly claims production acceptance")

    records = receipt["smooth_records"]
    require(len(records) == EXPECTED_FRAMES, "Wrong smooth record count")
    require(records[0]["output_frame"] == 1 and records[-1]["output_frame"] == EXPECTED_FRAMES, "Wrong record range")
    require(vec_distance(records[0]["location"], anchors[0]["location"]) < 1e-6, "Start location changed")
    require(vec_distance(records[-1]["location"], anchors[-1]["location"]) < 1e-6, "End location changed")

    fractions = [float(item["route_fraction"]) for item in records]
    require(math.isclose(fractions[0], 0.0, abs_tol=1e-12), "Wrong route start fraction")
    require(math.isclose(fractions[-1], 1.0, abs_tol=1e-12), "Wrong route end fraction")
    require(all(b > a for a, b in zip(fractions, fractions[1:])), "Route fractions are not strictly increasing")

    # The continuous spline must pass every original anchor. Output frames need only
    # sample close to each one because global arc-length timing intentionally retimes anchors.
    closest_anchor_distances = []
    for anchor in anchors:
        closest = min(vec_distance(item["location"], anchor["location"]) for item in records)
        closest_anchor_distances.append(closest)
        require(closest < 3.0, f"Smoothed output does not pass close enough to anchor {anchor['source_frame']}: {closest:.3f} m")

    metrics = receipt["motion_metrics"]
    current = metrics["current_032_sampling"]
    smooth = metrics["candidate_033_smoothed"]
    for family in ("linear_step", "angular_step_radians", "linear_step_change", "angular_step_change_radians"):
        for label, payload in (("current", current[family]), ("smooth", smooth[family])):
            for key in ("mean", "std", "cv", "p50", "p95", "max"):
                value = float(payload[key])
                require(math.isfinite(value) and value >= 0.0, f"Invalid {label} {family} {key}")

    # Arc-length reparameterization is a deterministic contract property, so its
    # translational frame-step variation should be nearly zero. Angular quality remains
    # evidence for human review rather than an automatic quality verdict.
    require(
        smooth["linear_step"]["cv"] < 0.01,
        f"033 translation is not close to constant speed: CV={smooth['linear_step']['cv']}",
    )
    require(
        smooth["linear_step"]["cv"] < current["linear_step"]["cv"],
        "033 did not reduce translational step variation",
    )

    proxy = receipt["proxy"]
    require(proxy["resolution"] == EXPECTED_RESOLUTION, "Proxy receipt resolution mismatch")
    require(proxy["fps"] == EXPECTED_FPS, "Proxy receipt fps mismatch")
    require(proxy["frame_count"] == EXPECTED_FRAMES, "Proxy receipt frame count mismatch")
    require(proxy["total_seconds"] > 0, "Proxy render time invalid")
    require(proxy.get("temporary_camera") is True, "033 proxy did not use a detached camera")
    require(len(proxy["frames"]) == EXPECTED_FRAMES, "Proxy frame receipt coverage incomplete")

    unique_hashes = {item["sha256"] for item in proxy["frames"].values()}
    require(
        len(unique_hashes) >= int(EXPECTED_FRAMES * 0.95),
        f"Proxy has too many duplicate rendered frames: {len(unique_hashes)} unique",
    )

    for record in records:
        frame = str(record["output_frame"])
        actual = proxy["frames"][frame]
        require(
            vec_distance(actual["camera_location_after_render"], record["location"]) < 1e-6,
            f"Frame {frame}: rendered proxy camera location drifted",
        )
        qa = actual["camera_quaternion_after_render"]
        qb = record["quaternion"]
        dot = abs(sum(float(a) * float(b) for a, b in zip(qa, qb)))
        dot = max(-1.0, min(1.0, dot))
        angular_error = 2.0 * math.acos(dot)
        require(
            angular_error < 1e-5,
            f"Frame {frame}: rendered proxy camera orientation drifted by {angular_error} rad",
        )
        require(
            math.isclose(float(actual["lens_after_render"]), float(record["lens"]), abs_tol=1e-6),
            f"Frame {frame}: rendered proxy lens drifted",
        )
        require(
            math.isclose(
                float(actual["focus_distance_after_render"]),
                float(record["focus_distance"]),
                abs_tol=1e-5,
            ),
            f"Frame {frame}: rendered proxy focus distance drifted",
        )

    stream = proxy_probe["streams"][0]
    require(stream["codec_name"] == "h264", "Proxy is not H.264")
    require(stream["pix_fmt"] == "yuv420p", "Proxy pixel format changed")
    require([int(stream["width"]), int(stream["height"])] == EXPECTED_RESOLUTION, "Encoded proxy resolution changed")
    require(stream["r_frame_rate"] == "60/1", "Encoded proxy fps changed")
    require(int(stream["nb_read_frames"]) == EXPECTED_FRAMES, "Encoded proxy frame count changed")
    require(math.isclose(float(proxy_probe["format"]["duration"]), EXPECTED_DURATION, abs_tol=0.04), "Encoded proxy duration changed")

    if comparison_probe is not None:
        comparison_stream = comparison_probe["streams"][0]
        require(comparison_stream["codec_name"] == "h264", "Comparison is not H.264")
        require(comparison_stream["r_frame_rate"] == "60/1", "Comparison fps changed")
        require(int(comparison_stream["nb_read_frames"]) == EXPECTED_FRAMES, "Comparison frame count changed")
        require(math.isclose(float(comparison_probe["format"]["duration"]), EXPECTED_DURATION, abs_tol=0.04), "Comparison duration changed")

    return {
        "verified": True,
        "frame_count": EXPECTED_FRAMES,
        "fps": EXPECTED_FPS,
        "duration_seconds": EXPECTED_DURATION,
        "proxy_resolution": EXPECTED_RESOLUTION,
        "anchor_closest_distance_m": closest_anchor_distances,
        "current_linear_cv": current["linear_step"]["cv"],
        "smooth_linear_cv": smooth["linear_step"]["cv"],
        "current_angular_change_p95": current["angular_step_change_radians"]["p95"],
        "smooth_angular_change_p95": smooth["angular_step_change_radians"]["p95"],
        "current_angular_step_p95": current["angular_step_radians"]["p95"],
        "smooth_angular_step_p95": smooth["angular_step_radians"]["p95"],
        "source_030_blend_sha256": receipt["source_030_blend_sha256"],
        "baseline_032_video_sha256": EXPECTED_032_VIDEO_SHA256,
        "review_required": True,
        "production_acceptance": False,
    }


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root

    receipt = json.loads((root / "camera-motion-review.json").read_text())
    proxy_probe = json.loads((root / "proxy-ffprobe.json").read_text())
    comparison_probe_path = root / "comparison-ffprobe.json"
    comparison_probe = json.loads(comparison_probe_path.read_text()) if comparison_probe_path.is_file() else None
    result = validate(receipt, proxy_probe, comparison_probe)

    proxy = root / "coimbra-033-smooth-camera-proxy-24s.mp4"
    require(proxy.is_file() and proxy.stat().st_size > 0, "Missing 033 proxy video")
    result["proxy_sha256"] = digest_file(proxy)

    comparison = root / "coimbra-033-vs-032-side-by-side.mp4"
    if comparison_probe is not None:
        require(comparison.is_file() and comparison.stat().st_size > 0, "Missing side-by-side comparison")
        result["comparison_sha256"] = digest_file(comparison)

    attribution = (root / "attribution.txt").read_text().strip()
    require("OpenStreetMap" in attribution and "DGT" in attribution, "Missing attribution")
    result["attribution"] = attribution

    (root / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
