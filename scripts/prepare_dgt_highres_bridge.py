from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.merge import merge


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "coimbra_bridge.json"
RAW_ROOT = ROOT / "data" / "raw" / "dgt_highres"
OUT = ROOT / "bridge_output_008b"

MDT_DIR = RAW_ROOT / "mdt-50cm"
MDS_DIR = RAW_ROOT / "mds-50cm"
MDT_TIF = OUT / "bridge_mdt_50cm.tif"
MDS_TIF = OUT / "bridge_mds_50cm.tif"
TERRAIN_NPZ = OUT / "bridge_terrain_highres_2m.npz"
HAG_NPZ = OUT / "bridge_height_above_ground_1m.npz"
META_JSON = OUT / "highres-geodata-manifest.json"


def source_files(directory: Path):
    files = sorted(list(directory.glob("*.tif")) + list(directory.glob("*.tiff")))
    if not files:
        raise RuntimeError(f"No GeoTIFF files in {directory}")
    return files


def crop_mosaic(files: list[Path], bounds):
    srcs = [rasterio.open(path) for path in files]
    try:
        mosaic, transform = merge(
            srcs,
            bounds=bounds,
            res=(0.5, 0.5),
            nodata=-999.0,
            target_aligned_pixels=False,
        )
        crs = srcs[0].crs
    finally:
        for src in srcs:
            src.close()

    arr = mosaic[0].astype("float32")
    arr[arr <= -998.0] = np.nan
    if not np.isfinite(arr).any():
        raise RuntimeError("High-resolution crop has no valid pixels")
    return arr, transform, crs


def write_tif(path: Path, arr: np.ndarray, transform, crs):
    profile = {
        "driver": "GTiff",
        "height": arr.shape[0],
        "width": arr.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": crs,
        "transform": transform,
        "nodata": -999.0,
        "compress": "deflate",
        "predictor": 3,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.where(np.isfinite(arr), arr, -999.0), 1)


def block_reduce_mean(arr: np.ndarray, factor: int):
    rows = (arr.shape[0] // factor) * factor
    cols = (arr.shape[1] // factor) * factor
    cropped = arr[:rows, :cols]
    return np.nanmean(cropped.reshape(rows // factor, factor, cols // factor, factor), axis=(1, 3))


def block_reduce_max(arr: np.ndarray, factor: int):
    rows = (arr.shape[0] // factor) * factor
    cols = (arr.shape[1] // factor) * factor
    cropped = arr[:rows, :cols]
    return np.nanmax(cropped.reshape(rows // factor, factor, cols // factor, factor), axis=(1, 3))


def grid_coords(transform, shape, factor, cx, cy):
    rows = np.arange(shape[0], dtype=np.float32)
    cols = np.arange(shape[1], dtype=np.float32)
    xs_abs = transform.c + (cols * factor + factor / 2.0) * transform.a
    ys_abs = transform.f + (rows * factor + factor / 2.0) * transform.e
    return (xs_abs - cx).astype("float32"), (ys_abs - cy).astype("float32")


def sha256(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    west, south, east, north = cfg["bbox_wgs84"]
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3763", always_xy=True)
    x1, y1 = transformer.transform(west, south)
    x2, y2 = transformer.transform(east, north)
    minx, maxx = sorted((x1, x2))
    miny, maxy = sorted((y1, y2))
    cx = (minx + maxx) / 2.0
    cy = (miny + maxy) / 2.0
    bounds = (minx, miny, maxx, maxy)

    OUT.mkdir(parents=True, exist_ok=True)

    mdt, mdt_transform, mdt_crs = crop_mosaic(source_files(MDT_DIR), bounds)
    mds, mds_transform, mds_crs = crop_mosaic(source_files(MDS_DIR), bounds)

    if mdt.shape != mds.shape:
        raise RuntimeError(f"MDT/MDS shape mismatch: {mdt.shape} vs {mds.shape}")
    if not np.allclose(tuple(mdt_transform), tuple(mds_transform), atol=1e-7):
        raise RuntimeError("MDT/MDS transforms do not align")

    mdt_fill = float(np.nanmedian(mdt))
    mdt = np.nan_to_num(mdt, nan=mdt_fill)
    mds = np.where(np.isfinite(mds), mds, mdt).astype("float32")

    write_tif(MDT_TIF, mdt, mdt_transform, mdt_crs)
    write_tif(MDS_TIF, mds, mds_transform, mds_crs)

    hag_50cm = np.clip(mds - mdt, 0.0, 80.0).astype("float32")

    terrain_factor = 4  # 0.5m -> 2m
    terrain = block_reduce_mean(mdt, terrain_factor).astype("float32")
    terrain_xs, terrain_ys = grid_coords(
        mdt_transform, terrain.shape, terrain_factor, cx, cy
    )
    terrain_z0 = float(terrain.min())
    np.savez_compressed(
        TERRAIN_NPZ,
        z=terrain,
        xs=terrain_xs,
        ys=terrain_ys,
        z0=np.float32(terrain_z0),
        center_x=np.float32(cx),
        center_y=np.float32(cy),
        source_resolution=np.float32(0.5),
        terrain_resolution=np.float32(2.0),
    )

    hag_factor = 2  # 0.5m -> 1m max-pool
    hag_1m = block_reduce_max(hag_50cm, hag_factor).astype("float32")
    hag_xs, hag_ys = grid_coords(mdt_transform, hag_1m.shape, hag_factor, cx, cy)
    np.savez_compressed(
        HAG_NPZ,
        height=hag_1m,
        xs=hag_xs,
        ys=hag_ys,
        center_x=np.float32(cx),
        center_y=np.float32(cy),
        source_resolution=np.float32(0.5),
        height_resolution=np.float32(1.0),
    )

    metadata = {
        "source": "DGT LiDAR 2024-2025",
        "collections": ["MDT-50cm", "MDS-50cm"],
        "source_resolution_m": 0.5,
        "render_terrain_resolution_m": 2.0,
        "height_above_ground_resolution_m": 1.0,
        "bbox_wgs84": cfg["bbox_wgs84"],
        "bbox_epsg3763": [minx, miny, maxx, maxy],
        "center_epsg3763": [cx, cy],
        "mdt_shape_50cm": list(mdt.shape),
        "mds_shape_50cm": list(mds.shape),
        "terrain_shape_2m": list(terrain.shape),
        "height_shape_1m": list(hag_1m.shape),
        "mdt_range_m": [float(mdt.min()), float(mdt.max())],
        "mds_range_m": [float(mds.min()), float(mds.max())],
        "height_above_ground_range_m": [float(hag_1m.min()), float(hag_1m.max())],
        "height_above_ground_nonzero_fraction": float(np.mean(hag_1m > 0.5)),
        "outputs": {
            "mdt_50cm": MDT_TIF.relative_to(ROOT).as_posix(),
            "mds_50cm": MDS_TIF.relative_to(ROOT).as_posix(),
            "terrain_2m": TERRAIN_NPZ.relative_to(ROOT).as_posix(),
            "height_above_ground_1m": HAG_NPZ.relative_to(ROOT).as_posix(),
        },
    }
    metadata["sha256"] = {
        "mdt_50cm": sha256(MDT_TIF),
        "mds_50cm": sha256(MDS_TIF),
        "terrain_2m": sha256(TERRAIN_NPZ),
        "height_above_ground_1m": sha256(HAG_NPZ),
    }
    META_JSON.write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
