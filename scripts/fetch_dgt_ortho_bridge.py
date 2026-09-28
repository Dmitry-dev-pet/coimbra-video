from __future__ import annotations

import io
import json
import math
import time
from pathlib import Path

import requests
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "coimbra_bridge.json"
OUT = ROOT / "data" / "processed" / "bridge_ortho_2025.jpg"

WMS = "https://cartografia.dgterritorio.gov.pt/wms/ortos2025"
LAYER = "Ortos2025-RGB"
CRS = "EPSG:3763"
TILE_METRES = 500.0
RESOLUTION = 0.25


def lonlat_to_epsg3763(lon: float, lat: float) -> tuple[float, float]:
    from pyproj import Transformer

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3763", always_xy=True)
    return transformer.transform(lon, lat)


def get_tile(
    session: requests.Session,
    bbox: tuple[float, float, float, float],
    attempt_limit: int = 4,
) -> Image.Image:
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
        "format": "image/jpeg",
        "transparent": "false",
    }

    last_error = None
    for attempt in range(1, attempt_limit + 1):
        try:
            response = session.get(WMS, params=params, timeout=120)
            response.raise_for_status()
            ctype = response.headers.get("content-type", "").lower()
            if "image" not in ctype:
                raise RuntimeError(
                    f"DGT WMS returned {ctype}: {response.text[:300]}"
                )
            return Image.open(io.BytesIO(response.content)).convert("RGB")
        except Exception as exc:
            last_error = exc
            time.sleep(attempt * 2)

    raise RuntimeError(f"Failed DGT WMS tile {bbox}: {last_error!r}")


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    west, south, east, north = cfg["bbox_wgs84"]

    minx, miny = lonlat_to_epsg3763(west, south)
    maxx, maxy = lonlat_to_epsg3763(east, north)
    minx, maxx = sorted((minx, maxx))
    miny, maxy = sorted((miny, maxy))

    width_m = maxx - minx
    height_m = maxy - miny
    nx = math.ceil(width_m / TILE_METRES)
    ny = math.ceil(height_m / TILE_METRES)
    full_w = int(round(width_m / RESOLUTION))
    full_h = int(round(height_m / RESOLUTION))

    print(
        f"DGT ortho bridge bbox: {width_m:.0f} x {height_m:.0f} m, "
        f"{full_w} x {full_h}px, {nx} x {ny} tiles"
    )

    canvas = Image.new("RGB", (full_w, full_h))
    session = requests.Session()
    session.headers["User-Agent"] = (
        "apatch-blender-coimbra-demo/0.2 "
        "(+https://github.com/Dmitry-dev-pet/coimbra-video)"
    )

    for iy in range(ny):
        tile_maxy = maxy - iy * TILE_METRES
        tile_miny = max(miny, tile_maxy - TILE_METRES)
        y0 = int(round((maxy - tile_maxy) / RESOLUTION))

        for ix in range(nx):
            tile_minx = minx + ix * TILE_METRES
            tile_maxx = min(maxx, tile_minx + TILE_METRES)
            x0 = int(round((tile_minx - minx) / RESOLUTION))

            print(f"tile {ix + 1}/{nx}, {iy + 1}/{ny}")
            tile = get_tile(
                session,
                (tile_minx, tile_miny, tile_maxx, tile_maxy),
            )
            canvas.paste(tile, (x0, y0))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUT, quality=91, subsampling=1, optimize=True)

    metadata = {
        "source": "DGT Orthophotos 2025",
        "layer": LAYER,
        "wms": WMS,
        "license": "CC BY 4.0",
        "resolution_m": RESOLUTION,
        "bbox_epsg3763": [minx, miny, maxx, maxy],
        "image_size": [full_w, full_h],
        "output": str(OUT.relative_to(ROOT)),
    }
    (OUT.parent / "bridge_ortho_2025.json").write_text(
        json.dumps(metadata, indent=2) + "\n"
    )
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
