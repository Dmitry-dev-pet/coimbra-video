from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from common import OUTPUT, PROCESSED, ensure_dirs

SRC = PROCESSED / "ortho_2025.jpg"
FRAMES = OUTPUT / "ortho_frames"
DST = OUTPUT / "coimbra_ortho_preview.mp4"

FPS = 18
SECONDS = 6
OUT_W = 1280
OUT_H = 720


def miniature_frame(img: Image.Image, t: float) -> Image.Image:
    w, h = img.size

    # Slow cinematic move over the University/Baixa/Mondego crop.
    zoom = 1.05 + 0.13 * t
    crop_w = min(w, int(w / zoom))
    crop_h = min(h, int(crop_w * OUT_H / OUT_W))
    if crop_h > h:
        crop_h = h
        crop_w = int(crop_h * OUT_W / OUT_H)

    travel_x = int((w - crop_w) * (0.28 + 0.38 * t))
    travel_y = int((h - crop_h) * (0.30 + 0.10 * math.sin(t * math.pi)))
    x0 = max(0, min(w - crop_w, travel_x))
    y0 = max(0, min(h - crop_h, travel_y))

    frame = img.crop((x0, y0, x0 + crop_w, y0 + crop_h)).resize(
        (OUT_W, OUT_H), Image.Resampling.LANCZOS
    )

    base = np.asarray(frame, dtype=np.float32)
    radii = [0, 2, 5, 9, 15]
    layers = [base]
    for r in radii[1:]:
        layers.append(
            np.asarray(frame.filter(ImageFilter.GaussianBlur(r)), dtype=np.float32)
        )
    stack = np.stack(layers, axis=0)

    yy, xx = np.mgrid[0:OUT_H, 0:OUT_W]
    xn = (xx - OUT_W / 2) / OUT_W
    yn = (yy - OUT_H / 2) / OUT_H
    center = -0.02 - 0.18 * xn + 0.018 * math.sin(t * math.tau)
    dist = np.abs(yn - center)

    level = np.clip((dist - 0.06) / 0.32, 0.0, 1.0) * (len(radii) - 1)
    lo = np.floor(level).astype(np.int32)
    hi = np.minimum(lo + 1, len(radii) - 1)
    frac = (level - lo)[..., None]

    lo_img = stack[lo.ravel(), yy.ravel(), xx.ravel()].reshape(OUT_H, OUT_W, 3)
    hi_img = stack[hi.ravel(), yy.ravel(), xx.ravel()].reshape(OUT_H, OUT_W, 3)
    out = lo_img * (1.0 - frac) + hi_img * frac

    mean = out.mean(axis=2, keepdims=True)
    out = mean + (out - mean) * 1.08
    out = np.clip((out - 128.0) * 1.03 + 128.0, 0, 255).astype(np.uint8)
    return Image.fromarray(out)


def main() -> None:
    ensure_dirs()
    if not SRC.exists():
        raise SystemExit(f"Missing {SRC}. Run fetch_ortho.py first.")
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is required")

    if FRAMES.exists():
        shutil.rmtree(FRAMES)
    FRAMES.mkdir(parents=True)

    img = Image.open(SRC).convert("RGB")
    total = FPS * SECONDS
    for i in range(total):
        t = i / max(1, total - 1)
        frame = miniature_frame(img, t)
        frame.save(FRAMES / f"frame_{i:04d}.jpg", quality=91)

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-framerate", str(FPS),
            "-i", str(FRAMES / "frame_%04d.jpg"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "20",
            "-movflags", "+faststart",
            str(DST),
        ],
        check=True,
    )
    print(f"Wrote {DST}")


if __name__ == "__main__":
    main()
