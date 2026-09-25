from __future__ import annotations

import io
import math
import sys
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.transform import from_bounds
import requests

from common import PROCESSED, ensure_dirs, load_config

WMS = "https://cartografia.dgterritorio.gov.pt/wms/ortos2025"
LAYER = "Ortos2025-RGB"
CRS = "EPSG:3763"

# 500 m at 25 cm = 2000 px. This is intentionally conservative for WMS servers.
TILE_METRES = 500.0
RESOLUTION = 0.25

def get_tile(session: requests.Session, bbox: tuple[float, float, float, float]) -> Image.Image:
    minx, miny, maxx, maxy = bbox
    width = int(round((maxx - minx) / RESOLUTION))
    height = int(round((maxy - miny) / RESOLUTION))
    params = {
        "service": "WMS",
        "request": "GetMap",
        "version": "1.3.0",
        "layers": LAYER,
        "styles": "",
        "crs": CRS,
        "bbox": f"{minx},{miny},{maxx},{maxy}",
        "width": str(width),
        "height": str(height),
        "format": "image/png",
        "transparent": "false",
    }
    r = session.get(WMS, params=params, timeout=120)
    r.raise_for_status()
    ctype = r.headers.get("content-type", "")
    if "image" not in ctype:
        raise RuntimeError(f"WMS returned {ctype}: {r.text[:500]}")
    return Image.open(io.BytesIO(r.content)).convert("RGB")

def main() -> None:
    ensure_dirs()
    cfg = load_config()
    minx, miny, maxx, maxy = cfg["bbox_epsg3763"]
    width_m, height_m = maxx - minx, maxy - miny

    nx = math.ceil(width_m / TILE_METRES)
    ny = math.ceil(height_m / TILE_METRES)

    full_w = int(round(width_m / RESOLUTION))
    full_h = int(round(height_m / RESOLUTION))
    canvas = Image.new("RGB", (full_w, full_h))

    s = requests.Session()
    s.headers["User-Agent"] = "coimbra-dgt-prototype/0.1"

    print(f"Downloading DGT 2025 ortho: {full_w} x {full_h}px, {nx} x {ny} WMS tiles")
    for iy in range(ny):
        # Image row 0 is north. Iterate north -> south.
        tile_maxy = maxy - iy * TILE_METRES
        tile_miny = max(miny, tile_maxy - TILE_METRES)
        y0 = int(round((maxy - tile_maxy) / RESOLUTION))

        for ix in range(nx):
            tile_minx = minx + ix * TILE_METRES
            tile_maxx = min(maxx, tile_minx + TILE_METRES)
            x0 = int(round((tile_minx - minx) / RESOLUTION))

            print(f"  tile {ix+1}/{nx}, {iy+1}/{ny}")
            tile = get_tile(s, (tile_minx, tile_miny, tile_maxx, tile_maxy))
            canvas.paste(tile, (x0, y0))

    jpg = PROCESSED / "ortho_2025.jpg"
    canvas.save(jpg, quality=94, subsampling=0)

    arr = np.asarray(canvas)
    tif = PROCESSED / "ortho_2025.tif"
    transform = from_bounds(minx, miny, maxx, maxy, full_w, full_h)
    with rasterio.open(
        tif,
        "w",
        driver="GTiff",
        width=full_w,
        height=full_h,
        count=3,
        dtype="uint8",
        crs=CRS,
        transform=transform,
        tiled=True,
        compress="jpeg",
        photometric="ycbcr",
    ) as dst:
        for b in range(3):
            dst.write(arr[:, :, b], b + 1)

    print(f"Wrote {tif}")
    print(f"Wrote {jpg}")

if __name__ == "__main__":
    main()
