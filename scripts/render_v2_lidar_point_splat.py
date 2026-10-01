from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import laspy
import numpy as np
import requests
from PIL import Image
from pyproj import Transformer
from scipy.ndimage import distance_transform_edt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_dgt_highres_bridge import STAC_SEARCH, authenticate


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "coimbra_v2_001.json"
DGT_ROOT = ROOT / "bridge_output_v2_001" / "dgt"
TERRAIN = DGT_ROOT / "prepared" / "coimbra-v2-001-terrain-2m.npz"
HAG = DGT_ROOT / "prepared" / "coimbra-v2-001-height-above-ground-1m.npz"
OUT = ROOT / "bridge_output_v2_lidar_points"

WIDTH = 1600
HEIGHT = 1000
SENSOR_WIDTH_MM = 36.0
TARGET_WGS84 = (-8.42596, 40.20744)
SEARCH_EPS = 0.00015
CHUNK_SIZE = 600_000
RENDER_CLASSES = {1, 2, 3, 4, 5, 6, 9, 26}
VARIANTS = [
    {"name": "a-85mm", "lens_mm": 85.0, "target_z_offset_m": -80.0},
    {"name": "b-105mm", "lens_mm": 105.0, "target_z_offset_m": -110.0},
    {"name": "c-125mm", "lens_mm": 125.0, "target_z_offset_m": -130.0},
]


def sample_grid(values, xs, ys, x, y):
    dx = float(xs[1] - xs[0])
    dy = float(ys[1] - ys[0])
    col = int(round((float(x) - float(xs[0])) / dx))
    row = int(round((float(y) - float(ys[0])) / dy))
    if not (0 <= row < len(ys) and 0 <= col < len(xs)):
        raise RuntimeError(f"grid sample outside extent: {x},{y}")
    return float(values[row, col])


def normalized(vector):
    vector = np.asarray(vector, dtype=np.float64)
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-12:
        raise RuntimeError("zero-length camera vector")
    return vector / norm


def camera_basis(camera, target):
    forward = normalized(np.asarray(target) - np.asarray(camera))
    world_up = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    right = normalized(np.cross(forward, world_up))
    up = normalized(np.cross(right, forward))
    return right, up, forward


def asset_href(feature):
    for asset in feature.get("assets", {}).values():
        href = asset.get("href")
        ctype = (asset.get("type") or "").lower()
        clean = href.lower().split("?")[0] if href else ""
        if href and (
            "laszip" in ctype
            or clean.endswith(".laz")
            or clean.endswith(".las")
        ):
            return href
    return None


def download_tile():
    user = os.getenv("DGT_USER", "").strip()
    password = os.getenv("DGT_PASSWORD", "")
    if not user or not password:
        raise SystemExit("DGT_USER and DGT_PASSWORD are required")

    bbox = [
        TARGET_WGS84[0] - SEARCH_EPS,
        TARGET_WGS84[1] - SEARCH_EPS,
        TARGET_WGS84[0] + SEARCH_EPS,
        TARGET_WGS84[1] + SEARCH_EPS,
    ]
    session = authenticate(user, password)
    response = session.post(
        STAC_SEARCH,
        json={"bbox": bbox, "limit": 10, "collections": ["LAZ"]},
        timeout=90,
    )
    response.raise_for_status()
    features = response.json().get("features", [])
    if not features:
        raise RuntimeError(f"No DGT LAZ tile intersects {bbox}")

    feature = features[0]
    href = asset_href(feature)
    if not href:
        raise RuntimeError("Selected DGT feature has no LAS/LAZ asset")

    OUT.mkdir(parents=True, exist_ok=True)
    suffix = ".laz" if href.lower().split("?")[0].endswith(".laz") else ".las"
    path = OUT / f"{feature.get('id','historic-core')}{suffix}"
    with session.get(href, stream=True, timeout=300) as download:
        download.raise_for_status()
        with path.open("wb") as handle:
            for chunk in download.iter_content(1024 * 1024):
                if chunk:
                    handle.write(chunk)
    return feature, path


def hero_camera_absolute():
    cfg = json.loads(CONFIG.read_text())
    terrain_file = np.load(TERRAIN)
    hag_file = np.load(HAG)

    center_x = float(terrain_file["center_x"])
    center_y = float(terrain_file["center_y"])
    terrain_z = terrain_file["z"].astype(np.float64)
    terrain_xs = terrain_file["xs"].astype(np.float64)
    terrain_ys = terrain_file["ys"].astype(np.float64)
    hag = hag_file["height"].astype(np.float64)
    hag_xs = hag_file["xs"].astype(np.float64)
    hag_ys = hag_file["ys"].astype(np.float64)

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3763", always_xy=True)
    camera_cfg = cfg["hero"]["camera_anchor"]
    target_cfg = cfg["hero"]["target"]

    camera_x, camera_y = transformer.transform(
        camera_cfg["lon"], camera_cfg["lat"]
    )
    target_x, target_y = transformer.transform(
        target_cfg["lon"], target_cfg["lat"]
    )

    camera_local_x = camera_x - center_x
    camera_local_y = camera_y - center_y
    target_local_x = target_x - center_x
    target_local_y = target_y - center_y

    camera_ground = sample_grid(
        terrain_z, terrain_xs, terrain_ys, camera_local_x, camera_local_y
    )
    target_ground = sample_grid(
        terrain_z, terrain_xs, terrain_ys, target_local_x, target_local_y
    )
    target_hag = max(
        0.0,
        sample_grid(hag, hag_xs, hag_ys, target_local_x, target_local_y),
    )

    base_camera = np.array(
        [
            camera_x,
            camera_y,
            camera_ground + float(cfg["hero"]["camera_height_agl_m"]),
        ],
        dtype=np.float64,
    )
    base_target = np.array(
        [
            target_x,
            target_y,
            target_ground
            + target_hag
            + float(cfg["hero"]["target_height_above_surface_m"]),
        ],
        dtype=np.float64,
    )
    return base_camera, base_target


def rgb8(points):
    red = np.asarray(points.red, dtype=np.uint16)
    green = np.asarray(points.green, dtype=np.uint16)
    blue = np.asarray(points.blue, dtype=np.uint16)
    rgb = np.column_stack([red, green, blue]).astype(np.float32)
    if float(np.percentile(rgb, 99.9)) > 255.0:
        rgb *= 255.0 / 65535.0
    return np.clip(rgb, 0, 255).astype(np.uint8)


def update_zbuffer(depth_buffer, color_buffer, pixel, depth, color):
    if pixel.size == 0:
        return 0

    order = np.lexsort((depth, pixel))
    pix_sorted = pixel[order]
    first = np.empty(pix_sorted.shape, dtype=bool)
    first[0] = True
    first[1:] = pix_sorted[1:] != pix_sorted[:-1]
    chosen = order[first]

    p = pixel[chosen]
    z = depth[chosen]
    c = color[chosen]
    better = z < depth_buffer[p]
    if np.any(better):
        p = p[better]
        depth_buffer[p] = z[better]
        color_buffer[p] = c[better]
        return int(p.size)
    return 0


def fill_small_holes(rgb, occupied, radius_px=2.2):
    empty = ~occupied
    if not np.any(empty):
        return rgb, occupied
    distance, indices = distance_transform_edt(
        empty, return_distances=True, return_indices=True
    )
    fill = empty & (distance <= float(radius_px))
    if np.any(fill):
        yy = indices[0][fill]
        xx = indices[1][fill]
        rgb[fill] = rgb[yy, xx]
        occupied = occupied | fill
    return rgb, occupied


def render_variant(reader, camera, target, lens_mm):
    right, up, forward = camera_basis(camera, target)
    focal_px = float(lens_mm) / SENSOR_WIDTH_MM * WIDTH
    cx = WIDTH * 0.5
    cy = HEIGHT * 0.5

    depth_buffer = np.full(WIDTH * HEIGHT, np.inf, dtype=np.float32)
    color_buffer = np.zeros((WIDTH * HEIGHT, 3), dtype=np.uint8)

    accepted_points = 0
    projected_points = 0
    zbuffer_writes = 0
    rgb_nonzero = 0

    for points in reader.chunk_iterator(CHUNK_SIZE):
        cls = np.asarray(points.classification, dtype=np.uint8)
        keep = np.isin(cls, list(RENDER_CLASSES))
        if not np.any(keep):
            continue

        x = np.asarray(points.x[keep], dtype=np.float64)
        y = np.asarray(points.y[keep], dtype=np.float64)
        z = np.asarray(points.z[keep], dtype=np.float64)
        color = rgb8(points)[keep]
        accepted_points += int(x.size)
        rgb_nonzero += int(np.count_nonzero(np.any(color > 0, axis=1)))

        dx = x - camera[0]
        dy = y - camera[1]
        dz = z - camera[2]

        cam_x = dx * right[0] + dy * right[1] + dz * right[2]
        cam_y = dx * up[0] + dy * up[1] + dz * up[2]
        cam_z = dx * forward[0] + dy * forward[1] + dz * forward[2]

        visible = cam_z > 1.0
        if not np.any(visible):
            continue

        cam_x = cam_x[visible]
        cam_y = cam_y[visible]
        cam_z = cam_z[visible]
        color = color[visible]

        u = np.rint(cx + focal_px * cam_x / cam_z).astype(np.int32)
        v = np.rint(cy - focal_px * cam_y / cam_z).astype(np.int32)
        inside = (u >= 0) & (u < WIDTH) & (v >= 0) & (v < HEIGHT)
        if not np.any(inside):
            continue

        u = u[inside]
        v = v[inside]
        depth = cam_z[inside].astype(np.float32)
        color = color[inside]
        projected_points += int(u.size)

        pixel = v.astype(np.int64) * WIDTH + u.astype(np.int64)
        zbuffer_writes += update_zbuffer(
            depth_buffer, color_buffer, pixel, depth, color
        )

    occupied = np.isfinite(depth_buffer).reshape((HEIGHT, WIDTH))
    image = color_buffer.reshape((HEIGHT, WIDTH, 3)).copy()
    occupied_before = int(np.count_nonzero(occupied))

    image, occupied_after_mask = fill_small_holes(image, occupied, radius_px=2.2)
    occupied_after = int(np.count_nonzero(occupied_after_mask))

    sky = np.array([158, 178, 207], dtype=np.uint8)
    image[~occupied_after_mask] = sky

    return image, {
        "accepted_points": accepted_points,
        "projected_points": projected_points,
        "zbuffer_writes": zbuffer_writes,
        "rgb_nonzero_points": rgb_nonzero,
        "occupied_pixels_before_splat": occupied_before,
        "occupied_pixels_after_splat": occupied_after,
        "occupied_fraction_before_splat": occupied_before / (WIDTH * HEIGHT),
        "occupied_fraction_after_splat": occupied_after / (WIDTH * HEIGHT),
    }


def main():
    for required in (CONFIG, TERRAIN, HAG):
        if not required.is_file():
            raise SystemExit(f"Missing input: {required}")

    feature, point_path = download_tile()
    base_camera, base_target = hero_camera_absolute()
    camera = base_camera.copy()
    camera[2] += 70.0

    receipts = []
    with laspy.open(point_path) as reader:
        dimensions = list(reader.header.point_format.dimension_names)
        if not all(name in dimensions for name in ("red", "green", "blue")):
            raise RuntimeError(
                f"LAS point format lacks RGB dimensions: {dimensions}"
            )
        total_points = int(reader.header.point_count)
        las_bounds = {
            "min": [float(v) for v in reader.header.mins],
            "max": [float(v) for v in reader.header.maxs],
        }
        point_format = str(reader.header.point_format)
        las_version = str(reader.header.version)

    for variant in VARIANTS:
        target = base_target.copy()
        target[2] += float(variant["target_z_offset_m"])
        with laspy.open(point_path) as reader:
            image, stats = render_variant(
                reader,
                camera,
                target,
                float(variant["lens_mm"]),
            )
        image_path = OUT / f"coimbra-v2-lidar-{variant['name']}.png"
        Image.fromarray(image, mode="RGB").save(image_path)
        receipts.append(
            {
                **variant,
                **stats,
                "image": image_path.relative_to(ROOT).as_posix(),
            }
        )

    manifest = {
        "version": "coimbra-v2-lidar-point-splat-v1",
        "source": "DGT raw classified LiDAR",
        "feature_id": feature.get("id"),
        "las_version": las_version,
        "point_format": point_format,
        "dimensions": dimensions,
        "download_bytes": point_path.stat().st_size,
        "total_points": total_points,
        "bounds_epsg3763": las_bounds,
        "render_classes": sorted(RENDER_CLASSES),
        "resolution": [WIDTH, HEIGHT],
        "sensor_width_mm": SENSOR_WIDTH_MM,
        "camera_absolute_epsg3763": camera.tolist(),
        "base_target_absolute_epsg3763": base_target.tolist(),
        "variants": receipts,
        "note": (
            "Direct XYZ+RGB LiDAR point-splat review. No OSM geometry, no "
            "photogrammetry mesh, no MDS/HAG geometry reconstruction."
        ),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))

    point_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
