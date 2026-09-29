from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "bridge_output_015"
MASTER = OUT / "final-look-master-3200x2000.png"
NEUTRAL = OUT / "final-look-neutral.png"
WARM = OUT / "final-look-warm.png"
CINEMATIC = OUT / "final-look-soft-cinematic.png"
MANIFEST = OUT / "final-look-grade-manifest.json"
TARGET_SIZE = (1600, 1000)


def srgb_to_linear(x):
    return np.where(
        x <= 0.04045,
        x / 12.92,
        ((x + 0.055) / 1.055) ** 2.4,
    )


def linear_to_srgb(x):
    return np.where(
        x <= 0.0031308,
        x * 12.92,
        1.055 * np.maximum(x, 0.0) ** (1.0 / 2.4) - 0.055,
    )


def saturation(rgb, amount):
    luminance = (
        rgb[..., 0:1] * 0.2126
        + rgb[..., 1:2] * 0.7152
        + rgb[..., 2:3] * 0.0722
    )
    return luminance + (rgb - luminance) * amount


def contrast(rgb, amount, pivot=0.18):
    return (rgb - pivot) * amount + pivot


def lift_shadows(rgb, amount):
    luma = (
        rgb[..., 0:1] * 0.2126
        + rgb[..., 1:2] * 0.7152
        + rgb[..., 2:3] * 0.0722
    )
    weight = np.clip((0.45 - luma) / 0.45, 0.0, 1.0)
    return rgb + weight * amount


def compress_highlights(rgb, strength):
    return rgb / (1.0 + np.maximum(rgb - 0.65, 0.0) * strength)


def split_tone(rgb, shadow_rgb, highlight_rgb, strength):
    luma = (
        rgb[..., 0:1] * 0.2126
        + rgb[..., 1:2] * 0.7152
        + rgb[..., 2:3] * 0.0722
    )
    shadow_weight = np.clip((0.45 - luma) / 0.45, 0.0, 1.0)
    highlight_weight = np.clip((luma - 0.50) / 0.50, 0.0, 1.0)
    result = rgb.copy()
    result *= 1.0 + shadow_weight * (np.array(shadow_rgb) - 1.0) * strength
    result *= 1.0 + highlight_weight * (np.array(highlight_rgb) - 1.0) * strength
    return result


def vignette(rgb, strength):
    h, w = rgb.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    nx = (xx - (w - 1) * 0.5) / (w * 0.5)
    ny = (yy - (h - 1) * 0.5) / (h * 0.5)
    radius = np.sqrt(nx * nx + ny * ny)
    mask = np.clip((radius - 0.42) / 0.72, 0.0, 1.0) ** 1.7
    return rgb * (1.0 - mask[..., None] * strength)


def grade(profile, srgb):
    rgb = srgb_to_linear(np.clip(srgb, 0.0, 1.0))

    if profile == "neutral":
        rgb *= 1.018
        rgb = lift_shadows(rgb, 0.010)
        rgb = compress_highlights(rgb, 0.22)
        rgb = contrast(rgb, 0.985)
        rgb = saturation(rgb, 0.965)

    elif profile == "warm":
        rgb *= 1.020
        rgb = lift_shadows(rgb, 0.012)
        rgb = compress_highlights(rgb, 0.24)
        rgb = contrast(rgb, 0.990)
        rgb = saturation(rgb, 0.985)
        rgb = split_tone(
            rgb,
            shadow_rgb=(0.985, 1.000, 1.018),
            highlight_rgb=(1.035, 1.014, 0.970),
            strength=0.62,
        )
        rgb = vignette(rgb, 0.025)

    elif profile == "soft-cinematic":
        rgb *= 1.012
        rgb = lift_shadows(rgb, 0.020)
        rgb = compress_highlights(rgb, 0.34)
        rgb = contrast(rgb, 0.965)
        rgb = saturation(rgb, 0.945)
        rgb = split_tone(
            rgb,
            shadow_rgb=(0.965, 0.992, 1.035),
            highlight_rgb=(1.045, 1.018, 0.955),
            strength=0.72,
        )
        rgb = vignette(rgb, 0.045)

    else:
        raise ValueError(profile)

    return np.clip(linear_to_srgb(np.clip(rgb, 0.0, None)), 0.0, 1.0)


def save_profile(source, profile, path):
    graded = grade(profile, source)
    out = Image.fromarray(np.round(graded * 255.0).astype(np.uint8), mode="RGB")
    out.save(path, format="PNG", optimize=True)


def main():
    if not MASTER.is_file():
        raise SystemExit(f"Missing master render: {MASTER}")

    image = Image.open(MASTER).convert("RGB")
    if image.size != (3200, 2000):
        raise SystemExit(f"Unexpected master size: {image.size}")

    # The geometry is rendered at exactly 2x the delivery resolution. LANCZOS
    # downsampling is the anti-aliasing/fine-detail cleanup pass.
    image = image.resize(TARGET_SIZE, Image.Resampling.LANCZOS)
    source = np.asarray(image, dtype=np.float32) / 255.0

    profiles = {
        "neutral": NEUTRAL,
        "warm": WARM,
        "soft-cinematic": CINEMATIC,
    }
    for profile, path in profiles.items():
        save_profile(source, profile, path)

    result = {
        "version": "coimbra-final-look-grade-v1",
        "source": MASTER.relative_to(ROOT).as_posix(),
        "source_resolution": [3200, 2000],
        "output_resolution": list(TARGET_SIZE),
        "downsample": "Pillow LANCZOS 2x",
        "profiles": {
            name: path.relative_to(ROOT).as_posix()
            for name, path in profiles.items()
        },
        "rules": {
            "no_geometry_changes": True,
            "no_scene_material_changes": True,
            "same_camera_for_all_grades": True,
            "grade_only_after_render": True,
        },
    }
    MANIFEST.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
