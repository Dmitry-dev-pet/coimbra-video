from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

EXPECTED_FRAMES = [1, 181, 360]
EXPECTED_RESOLUTION = [1600, 1000]


def compare_images(a: Path, b: Path) -> dict:
    image_a = Image.open(a).convert("RGB")
    image_b = Image.open(b).convert("RGB")
    if image_a.size != tuple(EXPECTED_RESOLUTION) or image_b.size != tuple(EXPECTED_RESOLUTION):
        raise ValueError("Unexpected review resolution")
    diff = ImageChops.difference(image_a, image_b)
    stat = ImageStat.Stat(diff)
    mean_abs = sum(stat.mean) / (3.0 * 255.0)
    extrema = diff.getextrema()
    max_abs = max(channel[1] for channel in extrema) / 255.0
    return {"mean_abs_normalized": mean_abs, "max_abs_normalized": max_abs}


def verify(root: Path) -> dict:
    manifest = json.loads((root / "production-look-review.json").read_text())
    if manifest.get("version") != "coimbra-030-production-look-review-v1":
        raise ValueError("Wrong 030 manifest version")
    if manifest.get("review_frames") != EXPECTED_FRAMES:
        raise ValueError("Wrong review frame set")
    if manifest.get("resolution") != EXPECTED_RESOLUTION:
        raise ValueError("Wrong review resolution")
    if not manifest.get("structure_unchanged"):
        raise ValueError("Non-light structure changed")
    if not manifest.get("camera_unchanged"):
        raise ValueError("Production camera changed")
    if manifest.get("promotion") != "review-required":
        raise ValueError("030 must remain review-gated")
    if not manifest.get("changes", {}).get("materials"):
        raise ValueError("No material changes recorded")
    if len(manifest.get("changes", {}).get("lights") or []) < 2:
        raise ValueError("No bounded lighting changes recorded")

    metrics = {}
    for frame in EXPECTED_FRAMES:
        key = str(frame)
        baseline = root / manifest["baseline"][key]["path"]
        candidate = root / manifest["candidate"][key]["path"]
        if not baseline.is_file() or not candidate.is_file():
            raise ValueError(f"Missing review pair for frame {frame}")
        result = compare_images(baseline, candidate)
        if result["mean_abs_normalized"] < 0.002:
            raise ValueError(f"030 visual delta too small at frame {frame}")
        if result["mean_abs_normalized"] > 0.45:
            raise ValueError(f"030 visual delta too large at frame {frame}")
        metrics[key] = result

    candidate_blend = root / manifest["candidate_blend"]["path"]
    if not candidate_blend.is_file() or candidate_blend.stat().st_size < 1024 * 1024:
        raise ValueError("Missing candidate Blender scene")

    result = {
        "verified": True,
        "review_required": True,
        "frames": EXPECTED_FRAMES,
        "metrics": metrics,
        "candidate_blend_sha256": manifest["candidate_blend"]["sha256"],
    }
    (root / "production-look-verification.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.root), indent=2))


if __name__ == "__main__":
    main()
