from __future__ import annotations

import argparse
import math
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def natural_key(path: Path):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", path.name)]


def collect_frames(source: Path, work: Path) -> list[Path]:
    if source.is_dir():
        frames = sorted(
            [p for p in source.rglob("*") if p.suffix.lower() in IMAGE_EXTS],
            key=natural_key,
        )
        if not frames:
            raise SystemExit(f"No image frames found in {source}")
        return frames

    if source.suffix.lower() == ".zip":
        extracted = work / "earth_studio_zip"
        extracted.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source) as zf:
            zf.extractall(extracted)
        frames = sorted(
            [p for p in extracted.rglob("*") if p.suffix.lower() in IMAGE_EXTS],
            key=natural_key,
        )
        if not frames:
            raise SystemExit("The ZIP contains no image sequence.")
        return frames

    if source.suffix.lower() in {".mp4", ".mov", ".m4v", ".webm"}:
        extracted = work / "decoded"
        extracted.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source),
                "-vsync",
                "0",
                str(extracted / "frame_%06d.png"),
            ],
            check=True,
        )
        return sorted(extracted.glob("frame_*.png"), key=natural_key)

    raise SystemExit("Input must be an Earth Studio ZIP, a frame directory, or a video file.")


def blur_radii(max_radius: float) -> list[float]:
    return [0.0, max_radius * 0.12, max_radius * 0.28, max_radius * 0.52, max_radius * 0.76, max_radius]


def apply_tilt_shift(
    img: Image.Image,
    focus_y: float,
    tilt: float,
    sharp_width: float,
    blur_span: float,
    max_radius: float,
    attribution_protect: float,
    saturation: float,
    contrast: float,
) -> Image.Image:
    img = img.convert("RGB")
    w, h = img.size

    base = np.asarray(img, dtype=np.float32)
    radii = blur_radii(max_radius)
    layers = [base]
    for radius in radii[1:]:
        layers.append(
            np.asarray(
                img.filter(ImageFilter.GaussianBlur(radius)),
                dtype=np.float32,
            )
        )
    stack = np.stack(layers, axis=0)

    yy, xx = np.mgrid[0:h, 0:w]
    xn = (xx / max(1, w - 1)) - 0.5
    yn = yy / max(1, h - 1)

    focus_line = focus_y + tilt * xn
    distance = np.abs(yn - focus_line)

    level = np.clip((distance - sharp_width) / max(1e-6, blur_span), 0.0, 1.0)
    level *= len(radii) - 1

    lo = np.floor(level).astype(np.int32)
    hi = np.minimum(lo + 1, len(radii) - 1)
    frac = (level - lo)[..., None]

    lo_img = stack[lo.ravel(), yy.ravel(), xx.ravel()].reshape(h, w, 3)
    hi_img = stack[hi.ravel(), yy.ravel(), xx.ravel()].reshape(h, w, 3)
    out = lo_img * (1.0 - frac) + hi_img * frac

    # Google Earth Studio attribution must stay visible. Never crop it and restore
    # the bottom strip from the original image so blur cannot make the credits unreadable.
    if attribution_protect > 0:
        start = max(0, int(h * (1.0 - attribution_protect)))
        feather = max(1, int(h * 0.025))
        full_start = min(h, start + feather)
        alpha = np.zeros((h, 1, 1), dtype=np.float32)
        if full_start > start:
            alpha[start:full_start, 0, 0] = np.linspace(0.0, 1.0, full_start - start)
        alpha[full_start:, 0, 0] = 1.0
        out = out * (1.0 - alpha) + base * alpha

    result = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
    if saturation != 1.0:
        result = ImageEnhance.Color(result).enhance(saturation)
    if contrast != 1.0:
        result = ImageEnhance.Contrast(result).enhance(contrast)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="Tilt-shift post-process for Google Earth Studio renders.")
    ap.add_argument("--input", required=True, help="Earth Studio ZIP, frame directory, or video file.")
    ap.add_argument("--output", default="output/coimbra_earthstudio_tiltshift.mp4")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--focus-y", type=float, default=0.48, help="Focus-line vertical position, 0=top, 1=bottom.")
    ap.add_argument("--tilt", type=float, default=-0.14, help="Focus-line slope across the frame.")
    ap.add_argument("--sharp-width", type=float, default=0.055)
    ap.add_argument("--blur-span", type=float, default=0.30)
    ap.add_argument("--max-radius", type=float, default=22.0)
    ap.add_argument(
        "--attribution-protect",
        type=float,
        default=0.12,
        help="Fraction of bottom image protected from blur so Earth Studio attribution stays readable.",
    )
    ap.add_argument("--saturation", type=float, default=1.10)
    ap.add_argument("--contrast", type=float, default=1.04)
    ap.add_argument("--crf", type=int, default=18)
    args = ap.parse_args()

    source = Path(args.input).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is required.")

    with tempfile.TemporaryDirectory(prefix="earthstudio-") as tmp:
        work = Path(tmp)
        frames = collect_frames(source, work)
        rendered = work / "processed"
        rendered.mkdir(parents=True)

        print(f"Processing {len(frames)} Earth Studio frame(s)")
        for idx, frame_path in enumerate(frames):
            with Image.open(frame_path) as frame:
                result = apply_tilt_shift(
                    frame,
                    focus_y=args.focus_y,
                    tilt=args.tilt,
                    sharp_width=args.sharp_width,
                    blur_span=args.blur_span,
                    max_radius=args.max_radius,
                    attribution_protect=args.attribution_protect,
                    saturation=args.saturation,
                    contrast=args.contrast,
                )
                result.save(rendered / f"frame_{idx:06d}.jpg", quality=95, subsampling=0)

            if idx == 0 or (idx + 1) % 50 == 0 or idx + 1 == len(frames):
                print(f"  {idx + 1}/{len(frames)}")

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-framerate",
                str(args.fps),
                "-i",
                str(rendered / "frame_%06d.jpg"),
                "-c:v",
                "libx264",
                "-preset",
                "slow",
                "-crf",
                str(args.crf),
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output),
            ],
            check=True,
        )

    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
