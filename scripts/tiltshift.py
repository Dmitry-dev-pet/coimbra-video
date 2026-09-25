from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

from common import OUTPUT

SRC = OUTPUT / "coimbra_sharp.png"
DST = OUTPUT / "coimbra_tiltshift.png"

def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"Missing {SRC}. Render the sharp frame first.")

    img = Image.open(SRC).convert("RGB")
    w, h = img.size
    base = np.asarray(img, dtype=np.float32)

    # Pyramid of progressively blurred images.
    radii = [0, 2, 5, 10, 18, 28]
    layers = [base]
    for r in radii[1:]:
        layers.append(np.asarray(img.filter(ImageFilter.GaussianBlur(r)), dtype=np.float32))
    stack = np.stack(layers, axis=0)

    yy, xx = np.mgrid[0:h, 0:w]
    xn = (xx - w / 2) / w
    yn = (yy - h / 2) / h

    # Tilted focus band. Negative slope makes the band follow the city hillside better
    # for the default camera.
    band_center = -0.02 - 0.20 * xn
    dist = np.abs(yn - band_center)

    sharp_half_width = 0.055
    blur_span = 0.34
    t = np.clip((dist - sharp_half_width) / blur_span, 0.0, 1.0)
    level = t * (len(radii) - 1)

    lo = np.floor(level).astype(np.int32)
    hi = np.minimum(lo + 1, len(radii) - 1)
    frac = (level - lo)[..., None]

    flat = np.arange(h * w)
    lo_img = stack[lo.ravel(), yy.ravel(), xx.ravel()].reshape(h, w, 3)
    hi_img = stack[hi.ravel(), yy.ravel(), xx.ravel()].reshape(h, w, 3)
    out = lo_img * (1.0 - frac) + hi_img * frac

    # Very small saturation/contrast bump, common in miniature photography.
    mean = out.mean(axis=2, keepdims=True)
    out = mean + (out - mean) * 1.10
    out = (out - 128.0) * 1.04 + 128.0
    out = np.clip(out, 0, 255).astype(np.uint8)

    Image.fromarray(out).save(DST)
    print(f"Wrote {DST}")

if __name__ == "__main__":
    main()
