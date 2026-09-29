from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.merge import merge
from rasterio.warp import Resampling, reproject


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "coimbra_bridge.json"
PDAL_TILES = ROOT / "bridge_output_009c" / "tiles"
REFERENCE = ROOT / "bridge_output_008b" / "bridge_height_above_ground_1m.npz"
HIGHRES_META = ROOT / "bridge_output_008b" / "highres-geodata-manifest.json"
OUT = ROOT / "bridge_output_009c"
MOSAIC = OUT / "pdal-height-above-ground-1m.tif"
REPORT = OUT / "pdal-vs-raster-hag.json"


def main() -> None:
    files = sorted(PDAL_TILES.glob("*.tif"))
    if not files:
        raise SystemExit("No PDAL HAG tile rasters found")

    cfg = json.loads(CONFIG.read_text())
    meta = json.loads(HIGHRES_META.read_text())
    ref = np.load(REFERENCE)
    ref_h = ref["height"].astype(np.float32)
    xs = ref["xs"].astype(np.float64)
    ys = ref["ys"].astype(np.float64)
    cx, cy = map(float, meta["center_epsg3763"])

    srcs = [rasterio.open(path) for path in files]
    try:
        mosaic, transform = merge(srcs, nodata=-9999.0, method="max")
        crs = srcs[0].crs
    finally:
        for src in srcs:
            src.close()

    arr = mosaic[0].astype(np.float32)
    arr[arr <= -9998] = np.nan
    OUT.mkdir(parents=True, exist_ok=True)

    profile = {
        "driver": "GTiff",
        "height": arr.shape[0],
        "width": arr.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": crs,
        "transform": transform,
        "nodata": -9999.0,
        "compress": "deflate",
        "tiled": True,
    }
    with rasterio.open(MOSAIC, "w", **profile) as dst:
        dst.write(np.where(np.isfinite(arr), arr, -9999.0), 1)

    # Reproject PDAL HAG into the exact 1 m reference grid derived from MDS-MDT.
    x_abs0 = cx + float(xs[0])
    y_abs0 = cy + float(ys[0])
    dx = float(np.median(np.diff(xs)))
    dy = abs(float(np.median(np.diff(ys))))
    dst_transform = Affine.translation(x_abs0 - dx / 2.0, y_abs0 + dy / 2.0) * Affine.scale(dx, -dy)

    aligned = np.full(ref_h.shape, np.nan, dtype=np.float32)
    reproject(
        source=np.where(np.isfinite(arr), arr, -9999.0),
        destination=aligned,
        src_transform=transform,
        src_crs=crs,
        src_nodata=-9999.0,
        dst_transform=dst_transform,
        dst_crs="EPSG:3763",
        dst_nodata=np.nan,
        resampling=Resampling.bilinear,
    )

    valid = np.isfinite(aligned) & np.isfinite(ref_h)
    signal = valid & ((aligned > 0.5) | (ref_h > 0.5))
    delta = aligned[signal] - ref_h[signal]

    report = {
        "pdal": {
            "tile_count": len(files),
            "mosaic_shape": list(arr.shape),
            "range_m": [
                float(np.nanmin(arr)),
                float(np.nanmax(arr)),
            ],
            "nonzero_fraction": float(np.nanmean(arr > 0.5)),
        },
        "reference": {
            "source": "DGT MDS-50cm - MDT-50cm, max-pooled to 1m",
            "shape": list(ref_h.shape),
            "range_m": [float(np.nanmin(ref_h)), float(np.nanmax(ref_h))],
        },
        "comparison": {
            "valid_cells": int(np.count_nonzero(valid)),
            "signal_cells": int(np.count_nonzero(signal)),
            "mae_m": float(np.mean(np.abs(delta))) if delta.size else None,
            "rmse_m": float(np.sqrt(np.mean(delta ** 2))) if delta.size else None,
            "median_delta_m": float(np.median(delta)) if delta.size else None,
            "p90_abs_delta_m": float(np.percentile(np.abs(delta), 90)) if delta.size else None,
            "correlation": float(np.corrcoef(aligned[signal], ref_h[signal])[0, 1]) if delta.size > 2 else None,
        },
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
