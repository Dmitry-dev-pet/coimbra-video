from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from pyproj import Transformer

import fetch_dgt_highres_bridge as dgt
from prepare_dgt_highres_bridge import crop_mosaic, source_files, write_tif


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "cova_do_ouro_site.json"
RAW_ROOT = ROOT / "data" / "raw" / "cova_do_ouro_mdt"
OUT = ROOT / "site_output_cova_do_ouro"

MDT_DIR = RAW_ROOT / "mdt-50cm"
MDT_TIF = OUT / "cova_do_ouro_mdt_50cm.tif"
SUMMARY_JSON = OUT / "site_summary.json"
PROFILE_CSV = OUT / "steepest_profile.csv"
MAP_PNG = OUT / "terrain_map.png"
PROFILE_PNG = OUT / "steepest_profile.png"
DOWNLOAD_MANIFEST = OUT / "download-manifest.json"


def make_bbox(center_lon: float, center_lat: float, half_extent_m: float):
    to_pt = Transformer.from_crs("EPSG:4326", "EPSG:3763", always_xy=True)
    to_wgs = Transformer.from_crs("EPSG:3763", "EPSG:4326", always_xy=True)
    cx, cy = to_pt.transform(center_lon, center_lat)
    west, south = to_wgs.transform(cx - half_extent_m, cy - half_extent_m)
    east, north = to_wgs.transform(cx + half_extent_m, cy + half_extent_m)
    return [west, south, east, north], (cx, cy), (cx - half_extent_m, cy - half_extent_m, cx + half_extent_m, cy + half_extent_m)


def bilinear(arr: np.ndarray, transform, x: float, y: float) -> float:
    col_corner, row_corner = (~transform) * (x, y)
    col = col_corner - 0.5
    row = row_corner - 0.5
    c0 = int(math.floor(col))
    r0 = int(math.floor(row))
    dc = col - c0
    dr = row - r0
    if r0 < 0 or c0 < 0 or r0 + 1 >= arr.shape[0] or c0 + 1 >= arr.shape[1]:
        return float("nan")
    q00 = arr[r0, c0]
    q10 = arr[r0, c0 + 1]
    q01 = arr[r0 + 1, c0]
    q11 = arr[r0 + 1, c0 + 1]
    vals = np.array([q00, q10, q01, q11], dtype=float)
    if not np.isfinite(vals).all():
        return float("nan")
    return float(
        q00 * (1 - dc) * (1 - dr)
        + q10 * dc * (1 - dr)
        + q01 * (1 - dc) * dr
        + q11 * dc * dr
    )


def plane_fit(arr: np.ndarray, transform, cx: float, cy: float, radius_m: float):
    rows, cols = np.indices(arr.shape)
    xs = transform.c + (cols + 0.5) * transform.a
    ys = transform.f + (rows + 0.5) * transform.e
    dx = xs - cx
    dy = ys - cy
    mask = np.isfinite(arr) & ((dx * dx + dy * dy) <= radius_m * radius_m)
    if int(mask.sum()) < 20:
        raise RuntimeError("Not enough valid MDT pixels for local plane fit")
    A = np.column_stack([dx[mask], dy[mask], np.ones(int(mask.sum()))])
    z = arr[mask].astype(float)
    a, b, c = np.linalg.lstsq(A, z, rcond=None)[0]
    slope = float(math.hypot(a, b))
    if slope <= 1e-9:
        downhill = (0.0, -1.0)
    else:
        downhill = (-float(a) / slope, -float(b) / slope)
    azimuth = (math.degrees(math.atan2(downhill[0], downhill[1])) + 360.0) % 360.0
    return {
        "dz_dx": float(a),
        "dz_dy": float(b),
        "intercept_center_m": float(c),
        "slope_ratio": slope,
        "slope_percent": slope * 100.0,
        "slope_degrees": math.degrees(math.atan(slope)),
        "downhill_unit_xy": [downhill[0], downhill[1]],
        "downhill_azimuth_deg_from_north": azimuth,
        "sample_count": int(mask.sum()),
    }


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    lon, lat = cfg["center_wgs84"]
    half_extent = float(cfg["half_extent_m"])
    bbox_wgs84, (cx, cy), bounds = make_bbox(lon, lat, half_extent)

    OUT.mkdir(parents=True, exist_ok=True)
    RAW_ROOT.mkdir(parents=True, exist_ok=True)

    dgt.RAW_ROOT = RAW_ROOT
    session = dgt.anonymous_session_if_available(bbox_wgs84)
    access_mode = "anonymous"
    if session is None:
        access_mode = "authenticated"
        user = os.getenv("DGT_USER", "").strip()
        password = os.getenv("DGT_PASSWORD", "")
        if not user or not password:
            raise SystemExit("DGT_USER and DGT_PASSWORD are required when anonymous CDD access is unavailable")
        session = dgt.authenticate(user, password)

    evidence = dgt.download_collection(session, "MDT-50cm", bbox_wgs84)
    DOWNLOAD_MANIFEST.write_text(
        json.dumps(
            {
                "source": "DGT LiDAR 2024-2025",
                "collection": "MDT-50cm",
                "bbox_wgs84": bbox_wgs84,
                "access_mode": access_mode,
                "tiles": evidence,
            },
            indent=2,
        )
        + "\n"
    )

    mdt, transform, crs = crop_mosaic(source_files(MDT_DIR), bounds)
    if not np.isfinite(mdt).any():
        raise RuntimeError("Cropped MDT contains no valid terrain")
    write_tif(MDT_TIF, mdt, transform, crs)

    plane = plane_fit(
        mdt,
        transform,
        cx,
        cy,
        float(cfg["local_plane_radius_m"]),
    )
    ux, uy = plane["downhill_unit_xy"]

    center_elevation = bilinear(mdt, transform, cx, cy)
    half_profile = float(cfg["profile_half_length_m"])
    distances = np.arange(-half_profile, half_profile + 0.001, 0.5)
    elevations = np.array(
        [bilinear(mdt, transform, cx + ux * s, cy + uy * s) for s in distances],
        dtype=float,
    )

    with PROFILE_CSV.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["distance_m_positive_downhill", "elevation_m"])
        for d, z in zip(distances, elevations):
            writer.writerow([f"{d:.2f}", "" if not np.isfinite(z) else f"{z:.3f}"])

    drops = {}
    for length in cfg["building_lengths_m"]:
        length = float(length)
        z_up = bilinear(mdt, transform, cx - ux * length / 2.0, cy - uy * length / 2.0)
        z_down = bilinear(mdt, transform, cx + ux * length / 2.0, cy + uy * length / 2.0)
        drops[f"{length:g}m"] = {
            "upslope_elevation_m": z_up,
            "downslope_elevation_m": z_down,
            "drop_m": z_up - z_down,
            "grade_percent_actual": ((z_up - z_down) / length) * 100.0,
        }

    rows, cols = np.indices(mdt.shape)
    xs = transform.c + (cols + 0.5) * transform.a
    ys = transform.f + (rows + 0.5) * transform.e
    finite = np.isfinite(mdt)

    fig, ax = plt.subplots(figsize=(8, 7))
    extent = [
        float(xs[finite].min()),
        float(xs[finite].max()),
        float(ys[finite].min()),
        float(ys[finite].max()),
    ]
    im = ax.imshow(mdt, extent=extent, origin="upper")
    zmin = float(np.nanmin(mdt))
    zmax = float(np.nanmax(mdt))
    levels = np.arange(math.floor(zmin * 4) / 4, math.ceil(zmax * 4) / 4 + 0.25, 0.25)
    ax.contour(xs, ys, mdt, levels=levels, linewidths=0.45)
    ax.scatter([cx], [cy], s=35, marker="x")
    ax.plot(
        [cx - ux * half_profile, cx + ux * half_profile],
        [cy - uy * half_profile, cy + uy * half_profile],
        linewidth=1.5,
    )
    ax.arrow(cx, cy, ux * 20.0, uy * 20.0, width=0.25, head_width=2.0, length_includes_head=True)
    ax.set_aspect("equal")
    ax.set_title("Cova do Ouro — DGT MDT 50 cm")
    ax.set_xlabel("PT-TM06 X (m)")
    ax.set_ylabel("PT-TM06 Y (m)")
    fig.colorbar(im, ax=ax, label="Elevation (m)")
    fig.tight_layout()
    fig.savefig(MAP_PNG, dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(distances, elevations)
    ax.axvline(0.0, linewidth=0.8)
    ax.set_title("Terrain profile through mapped property point — positive distance is downhill")
    ax.set_xlabel("Distance from mapped point (m)")
    ax.set_ylabel("Elevation (m)")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(PROFILE_PNG, dpi=180)
    plt.close(fig)

    summary = {
        "source": "DGT LiDAR 2024-2025 MDT-50cm",
        "source_resolution_m": 0.5,
        "center_wgs84": [lon, lat],
        "center_epsg3763": [cx, cy],
        "bbox_wgs84": bbox_wgs84,
        "bbox_epsg3763": list(bounds),
        "center_elevation_m": center_elevation,
        "crop_elevation_range_m": [float(np.nanmin(mdt)), float(np.nanmax(mdt))],
        "local_plane_radius_m": float(cfg["local_plane_radius_m"]),
        "local_plane": plane,
        "actual_centered_drops_along_downhill": drops,
        "profile_span_m": [float(distances.min()), float(distances.max())],
        "outputs": {
            "mdt_50cm": MDT_TIF.relative_to(ROOT).as_posix(),
            "terrain_map_png": MAP_PNG.relative_to(ROOT).as_posix(),
            "steepest_profile_csv": PROFILE_CSV.relative_to(ROOT).as_posix(),
            "steepest_profile_png": PROFILE_PNG.relative_to(ROOT).as_posix(),
        },
        "note": "The mapped listing/agency point can be offset from the legal parcel. Use this as terrain evidence around the point, not as a cadastral boundary survey.",
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
