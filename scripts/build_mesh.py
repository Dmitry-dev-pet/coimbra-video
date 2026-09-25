from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling

from common import PROCESSED, ensure_dirs

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh-resolution", type=float, default=2.0)
    args = ap.parse_args()

    ensure_dirs()
    mds_path = PROCESSED / "mds_50cm.tif"
    ortho_path = PROCESSED / "ortho_2025.jpg"
    if not mds_path.exists():
        raise SystemExit("Missing data/processed/mds_50cm.tif")
    if not ortho_path.exists():
        raise SystemExit("Missing data/processed/ortho_2025.jpg")

    with rasterio.open(mds_path) as src:
        src_res = abs(src.transform.a)
        scale = src_res / args.mesh_resolution
        out_h = max(2, int(round(src.height * scale)))
        out_w = max(2, int(round(src.width * scale)))
        z = src.read(
            1,
            out_shape=(out_h, out_w),
            resampling=Resampling.bilinear,
        ).astype("float32")
        bounds = src.bounds

    z[z <= -998] = np.nan
    if np.isnan(z).any():
        fill = float(np.nanmedian(z))
        z = np.nan_to_num(z, nan=fill)

    minx, miny, maxx, maxy = bounds
    xs = np.linspace(minx, maxx, out_w, dtype=np.float32)
    ys = np.linspace(maxy, miny, out_h, dtype=np.float32)  # raster north -> south

    cx = (minx + maxx) / 2.0
    cy = (miny + maxy) / 2.0
    z0 = float(np.nanmin(z))

    obj = PROCESSED / "coimbra.obj"
    mtl = PROCESSED / "coimbra.mtl"

    with obj.open("w", encoding="utf-8") as f:
        f.write("mtllib coimbra.mtl\n")
        f.write("o Coimbra_DGT_MDS\n")

        # Vertices. Use local coordinates for numerical stability in Blender.
        for r in range(out_h):
            yy = ys[r] - cy
            for c in range(out_w):
                xx = xs[c] - cx
                zz = float(z[r, c] - z0)
                f.write(f"v {xx:.3f} {yy:.3f} {zz:.3f}\n")

        # UVs: image origin is top-left; OBJ texture origin is bottom-left.
        for r in range(out_h):
            v = 1.0 - r / (out_h - 1)
            for c in range(out_w):
                u = c / (out_w - 1)
                f.write(f"vt {u:.7f} {v:.7f}\n")

        f.write("usemtl ortho\n")
        for r in range(out_h - 1):
            base = r * out_w
            nxt = (r + 1) * out_w
            for c in range(out_w - 1):
                a = base + c + 1
                b = base + c + 2
                d = nxt + c + 1
                e = nxt + c + 2
                f.write(f"f {a}/{a} {d}/{d} {b}/{b}\n")
                f.write(f"f {b}/{b} {d}/{d} {e}/{e}\n")

    mtl.write_text(
        "newmtl ortho\n"
        "Ka 1.000 1.000 1.000\n"
        "Kd 1.000 1.000 1.000\n"
        "Ks 0.000 0.000 0.000\n"
        "illum 1\n"
        "map_Kd ortho_2025.jpg\n",
        encoding="utf-8",
    )

    verts = out_h * out_w
    tris = (out_h - 1) * (out_w - 1) * 2
    print(f"Wrote {obj}")
    print(f"Mesh: {out_w} x {out_h} = {verts:,} vertices, {tris:,} triangles")
    print(f"Local elevation offset: {z0:.2f} m")

if __name__ == "__main__":
    main()
