"""Compare 027 CPU/Metal checkpoint PNGs using Pillow."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageEnhance, ImageStat

FRAMES = (1, 181, 360)


def compare_pair(cpu_path: Path, metal_path: Path, diff_path: Path) -> dict:
    cpu = Image.open(cpu_path).convert("RGB")
    metal = Image.open(metal_path).convert("RGB")
    if cpu.size != metal.size:
        raise ValueError(f"Image size mismatch: {cpu.size} != {metal.size}")

    diff = ImageChops.difference(cpu, metal)
    stat = ImageStat.Stat(diff)
    mean_abs = sum(stat.mean) / (3.0 * 255.0)
    rms = math.sqrt(sum(value * value for value in stat.rms) / 3.0) / 255.0
    max_abs = max(high for _low, high in diff.getextrema()) / 255.0

    ImageEnhance.Brightness(diff).enhance(4.0).save(diff_path)
    return {
        "size": list(cpu.size),
        "mean_abs_normalized": mean_abs,
        "rms_normalized": rms,
        "max_abs_normalized": max_abs,
        "diff_path": diff_path.name,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()

    frames = {}
    for frame in FRAMES:
        frames[str(frame)] = compare_pair(
            args.root / f"frame-{frame:03d}-cpu.png",
            args.root / f"frame-{frame:03d}-metal.png",
            args.root / f"frame-{frame:03d}-diff-x4.png",
        )

    result = {"version": "coimbra-027-image-comparison-v1", "frames": frames}
    (args.root / "image-comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
