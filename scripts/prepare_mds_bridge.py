from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.merge import merge


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "coimbra_bridge.json"
OSM = ROOT / "data" / "osm" / "coimbra-route.json"
RAW = ROOT / "data" / "raw" / "mds_bridge"
PROCESSED = ROOT / "data" / "processed"

OUT_NPZ = PROCESSED / "bridge_terrain_6m.npz"
OUT_META = PROCESSED / "bridge_terrain_6m.json"
OUT_OSM = PROCESSED / "bridge_osm_local_epsg3763.json"

TARGET_RESOLUTION_M = 6.0


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    osm = json.loads(OSM.read_text())
    west, south, east, north = cfg["bbox_wgs84"]

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3763", always_xy=True)
    x1, y1 = transformer.transform(west, south)
    x2, y2 = transformer.transform(east, north)
    minx, maxx = sorted((x1, x2))
    miny, maxy = sorted((y1, y2))
    cx = (minx + maxx) / 2.0
    cy = (miny + maxy) / 2.0

    files = sorted(list(RAW.glob("*.tif")) + list(RAW.glob("*.tiff")))
    if not files:
        raise SystemExit(f"No DGT MDS files in {RAW}")

    srcs = [rasterio.open(path) for path in files]
    try:
        mosaic, transform = merge(srcs, bounds=(minx, miny, maxx, maxy), nodata=-999.0)
    finally:
        for src in srcs:
            src.close()

    z = mosaic[0].astype("float32")
    z[z <= -998] = np.nan
    valid = z[np.isfinite(z)]
    if not valid.size:
        raise RuntimeError("Bridge MDS crop has no valid pixels")
    fill = float(np.nanmedian(valid))
    z = np.nan_to_num(z, nan=fill)

    source_res = abs(float(transform.a))
    stride = max(1, int(round(TARGET_RESOLUTION_M / source_res)))
    z_small = z[::stride, ::stride].astype("float32")

    rows = np.arange(z_small.shape[0], dtype=np.float32) * stride
    cols = np.arange(z_small.shape[1], dtype=np.float32) * stride
    xs_abs = transform.c + (cols + 0.5) * transform.a
    ys_abs = transform.f + (rows + 0.5) * transform.e
    xs = (xs_abs - cx).astype("float32")
    ys = (ys_abs - cy).astype("float32")
    z0 = float(np.min(z_small))

    PROCESSED.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        OUT_NPZ,
        z=z_small,
        xs=xs,
        ys=ys,
        z0=np.float32(z0),
        center_x=np.float32(cx),
        center_y=np.float32(cy),
        source_resolution=np.float32(source_res),
        terrain_resolution=np.float32(source_res * stride),
    )

    local_nodes = {}
    for element in osm.get("elements", []):
        if element.get("type") != "node":
            continue
        x, y = transformer.transform(element["lon"], element["lat"])
        local_nodes[str(element["id"])] = [x - cx, y - cy]

    local_osm = {
        "center_epsg3763": [cx, cy],
        "bbox_epsg3763": [minx, miny, maxx, maxy],
        "nodes": local_nodes,
        "ways": [
            element
            for element in osm.get("elements", [])
            if element.get("type") == "way"
        ],
    }
    OUT_OSM.write_text(json.dumps(local_osm))

    meta = {
        "source": "DGT MDS-2m",
        "source_files": [path.name for path in files],
        "source_resolution_m": source_res,
        "terrain_resolution_m": source_res * stride,
        "shape": list(z_small.shape),
        "z_min": float(z_small.min()),
        "z_max": float(z_small.max()),
        "z0": z0,
        "center_epsg3763": [cx, cy],
        "bbox_epsg3763": [minx, miny, maxx, maxy],
        "terrain_npz": str(OUT_NPZ.relative_to(ROOT)),
        "osm_local": str(OUT_OSM.relative_to(ROOT)),
    }
    OUT_META.write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
