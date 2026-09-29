"""Independent, Blender-free acceptance of 026 delivery and shard receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(prepare, shards, probe):
    require(prepare["version"] == "coimbra-cycles-full-route-prepare-v1", "Unknown prepare schema")
    require(prepare["geometry_matches_025"] is True, "025 geometry not confirmed")
    require(prepare["frame_count"] == 360 and prepare["fps"] == 30, "Native timing changed")
    require(prepare["resolution"] == [1600, 1000], "025 framing/resolution changed")
    require(prepare["source_025_commit"] == "d178382d10eef41ec00da3fe562fcc445438f8da", "Unpinned baseline")
    expected_frames = list(range(1, 361))
    require([c["frame"] for c in prepare["cameras"]] == expected_frames, "Incomplete camera record")
    settings = prepare["cycles"]
    for key, value in {"device": "CPU", "samples": 16, "use_denoising": True,
                       "use_adaptive_sampling": True}.items():
        require(settings.get(key) == value, f"Cycles setting changed: {key}")
    require(len(shards) == 12, "Exactly twelve shards required")
    actual_frames = []
    for shard in sorted(shards, key=lambda s: s["start"]):
        require(shard["end"] - shard["start"] + 1 == 30, "Shard length is not 30")
        actual_frames.extend(range(shard["start"], shard["end"] + 1))
        require(shard["protected_sha256"] == prepare["protected_sha256"], "Protected state changed")
        require(shard["blend_sha256"] == prepare["blend_sha256"], "Different scene artifact")
        require(shard["cycles"] == settings, "Different shard render settings")
        require(shard["camera_unchanged"] is True, "Camera changed")
        require(shard["geometry_material_world_unchanged"] is True, "Scene changed")
        require(sorted(map(int, shard["frames"])) == list(range(shard["start"], shard["end"] + 1)),
                "Missing frame receipts")
        require(all(len(h) == 64 and all(c in "0123456789abcdef" for c in h)
                    for h in shard["frames"].values()), "Invalid frame hash")
    require(actual_frames == expected_frames, "Missing, duplicated, or reordered frame range")
    stream = probe["streams"][0]
    require(stream["codec_name"] == "h264", "Not H.264")
    require(stream["pix_fmt"] == "yuv420p", "Incompatible pixel format")
    require([int(stream["width"]), int(stream["height"])] == prepare["resolution"], "Wrong video resolution")
    require(stream["r_frame_rate"] == "30/1", "Wrong video FPS")
    require(int(stream["nb_read_frames"]) == 360, "Video does not decode to 360 frames")
    require(math.isclose(float(probe["format"]["duration"]), 12.0, abs_tol=0.04), "Wrong video duration")
    return {"verified": True, "frames": 360, "fps": 30, "duration_seconds": 12.0,
            "resolution": prepare["resolution"], "source_025_commit": prepare["source_025_commit"],
            "protected_sha256": prepare["protected_sha256"], "shards": len(shards),
            "sampling": "native integer frames 1..360; no repeats or optical flow inserted"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root
    prepare = json.loads((root / "prepare.json").read_text())
    shards = [json.loads(p.read_text()) for p in (root / "shards").glob("shard-????-????.json")]
    result = validate(prepare, shards, json.loads((root / "ffprobe.json").read_text()))
    video = root / "coimbra-cycles-full-route-12s.mp4"
    result["video_sha256"] = hashlib.sha256(video.read_bytes()).hexdigest()
    result["attribution"] = (root / "attribution.txt").read_text().strip()
    require("OpenStreetMap" in result["attribution"] and "DGT" in result["attribution"], "Missing attribution")
    for frame in (1, 181, 360):
        require((root / "review" / f"frame-{frame:03d}.png").is_file(), "Missing decoded video review frame")
    (root / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
