from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.windows import from_bounds

from common import PROCESSED, RAW_MDS, ensure_dirs, load_config

def main() -> None:
    ensure_dirs()
    cfg = load_config()
    bbox = cfg["bbox_epsg3763"]
    files = sorted(list(RAW_MDS.glob("*.tif")) + list(RAW_MDS.glob("*.tiff")))
    if not files:
        raise SystemExit("No MDS GeoTIFF files in data/raw/mds/. Run scripts/fetch_mds.py first.")

    srcs = [rasterio.open(p) for p in files]
    try:
        mosaic, transform = merge(srcs, bounds=tuple(bbox), nodata=-999.0)
    finally:
        for s in srcs:
            s.close()

    arr = mosaic[0].astype("float32")
    arr[arr <= -998] = np.nan

    out = PROCESSED / "mds_50cm.tif"
    profile = {
        "driver": "GTiff",
        "height": arr.shape[0],
        "width": arr.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:3763",
        "transform": transform,
        "nodata": -999.0,
        "compress": "deflate",
        "tiled": True,
    }
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(np.where(np.isnan(arr), -999.0, arr), 1)

    valid = arr[np.isfinite(arr)]
    print(f"Wrote {out}")
    if valid.size:
        print(f"Elevation range: {valid.min():.2f} .. {valid.max():.2f} m")

if __name__ == "__main__":
    main()
