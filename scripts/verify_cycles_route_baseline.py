from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "bridge_output_025"
MANIFEST = OUT / "cycles-route-baseline.json"
METRICS = OUT / "route-backend-metrics.json"

EXPECTED_FRAMES = [1, 181, 360]
EXPECTED_SIZE = (1600, 1000)
SOURCE_024_COMMIT = "d5583af1a837c6a3a0831f42ffdc667abd6b37ab"


def image_metrics(path: Path):
    image = Image.open(path).convert("RGB")
    if image.size != EXPECTED_SIZE:
        raise SystemExit(f"unexpected image size for {path}: {image.size}")
    arr = np.asarray(image, dtype=np.float32) / 255.0
    luma = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
    return {
        "mean_luma": float(luma.mean()),
        "p05_luma": float(np.quantile(luma, 0.05)),
        "near_black_fraction": float((luma < 0.04).mean()),
        "dark_fraction": float((luma < 0.10).mean()),
    }, arr


def main():
    manifest = json.loads(MANIFEST.read_text())
    if manifest.get("version") != "coimbra-cycles-route-baseline-v1":
        raise SystemExit("wrong manifest version")
    if manifest.get("source_024_commit") != SOURCE_024_COMMIT:
        raise SystemExit("wrong 024 source commit")
    if manifest.get("review_frames") != EXPECTED_FRAMES:
        raise SystemExit("wrong review frame set")
    if manifest.get("production_camera_unchanged") is not True:
        raise SystemExit("production camera invariant not recorded")
    if manifest.get("geometry_material_mutations") is not False:
        raise SystemExit("geometry/material mutation invariant not recorded")

    records = manifest.get("renders") or []
    if [int(item["frame"]) for item in records] != EXPECTED_FRAMES:
        raise SystemExit("render records do not match review frames")

    metrics = {
        "version": "coimbra-route-backend-metrics-v1",
        "frames": [],
    }

    for item in records:
        frame = int(item["frame"])
        eevee = ROOT / item["eevee"]["path"]
        cycles = ROOT / item["cycles"]["path"]
        if not eevee.is_file() or not cycles.is_file():
            raise SystemExit(f"missing render pair for frame {frame}")

        settings = item["cycles"].get("settings") or {}
        if int(settings.get("samples", 0)) != 16:
            raise SystemExit(f"frame {frame}: Cycles samples != 16")
        if settings.get("use_denoising") is not True:
            raise SystemExit(f"frame {frame}: denoising disabled")

        eevee_metrics, eevee_arr = image_metrics(eevee)
        cycles_metrics, cycles_arr = image_metrics(cycles)
        mean_abs_difference = float(np.abs(eevee_arr - cycles_arr).mean())
        if mean_abs_difference <= 0.001:
            raise SystemExit(f"frame {frame}: EEVEE/Cycles outputs unexpectedly similar")

        metrics["frames"].append(
            {
                "frame": frame,
                "eevee": eevee_metrics,
                "cycles": cycles_metrics,
                "mean_abs_rgb_difference": mean_abs_difference,
                "near_black_fraction_delta_cycles_minus_eevee": (
                    cycles_metrics["near_black_fraction"]
                    - eevee_metrics["near_black_fraction"]
                ),
            }
        )

    METRICS.write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
