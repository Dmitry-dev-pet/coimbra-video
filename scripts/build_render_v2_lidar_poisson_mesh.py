from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import laspy
import numpy as np
import open3d as o3d
from PIL import Image
from pyproj import Transformer
from scipy.ndimage import distance_transform_edt
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_dgt_highres_bridge import STAC_SEARCH, authenticate


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "coimbra_v2_001.json"
DGT_ROOT = ROOT / "bridge_output_v2_001" / "dgt"
TERRAIN = DGT_ROOT / "prepared" / "coimbra-v2-001-terrain-2m.npz"
HAG = DGT_ROOT / "prepared" / "coimbra-v2-001-height-above-ground-1m.npz"
OUT = ROOT / "bridge_output_v2_lidar_mesh"

WIDTH = 1600
HEIGHT = 1000
SENSOR_WIDTH_MM = 36.0
TARGET_WGS84 = (-8.42596, 40.20744)
SEARCH_EPS = 0.00015
CROP_HALF_M = 150.0
HARD_CLASSES = {2, 6}
VOXEL_M = 0.40
POISSON_DEPTH = 9
DENSITY_QUANTILE = 0.03
SURFACE_SAMPLES = 4_000_000
SAMPLE_CHUNK = 400_000
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


def load_crop(point_path, center_abs):
    xyz_parts = []
    color_parts = []
    class_counts = {}
    raw_crop_points = 0

    min_x = float(center_abs[0] - CROP_HALF_M)
    max_x = float(center_abs[0] + CROP_HALF_M)
    min_y = float(center_abs[1] - CROP_HALF_M)
    max_y = float(center_abs[1] + CROP_HALF_M)

    with laspy.open(point_path) as reader:
        dimensions = list(reader.header.point_format.dimension_names)
        if not all(name in dimensions for name in ("red", "green", "blue")):
            raise RuntimeError(f"LAS has no RGB dimensions: {dimensions}")

        for points in reader.chunk_iterator(750_000):
            x = np.asarray(points.x, dtype=np.float64)
            y = np.asarray(points.y, dtype=np.float64)
            cls = np.asarray(points.classification, dtype=np.uint8)

            spatial = (
                (x >= min_x)
                & (x <= max_x)
                & (y >= min_y)
                & (y <= max_y)
            )
            if not np.any(spatial):
                continue

            crop_classes = cls[spatial]
            values, counts = np.unique(crop_classes, return_counts=True)
            for value, count in zip(values, counts):
                key = str(int(value))
                class_counts[key] = class_counts.get(key, 0) + int(count)

            keep = spatial & np.isin(cls, list(HARD_CLASSES))
            if not np.any(keep):
                continue

            z = np.asarray(points.z[keep], dtype=np.float64)
            xyz = np.column_stack(
                [
                    x[keep] - center_abs[0],
                    y[keep] - center_abs[1],
                    z - center_abs[2],
                ]
            )
            colors = rgb8(points)[keep]
            xyz_parts.append(xyz)
            color_parts.append(colors)
            raw_crop_points += int(xyz.shape[0])

    if not xyz_parts:
        raise RuntimeError("No hard-surface LiDAR points in the 300m crop")

    xyz = np.concatenate(xyz_parts, axis=0)
    colors = np.concatenate(color_parts, axis=0)
    return xyz, colors, class_counts, raw_crop_points


def reconstruct_mesh(xyz, colors):
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(xyz)
    pcd.colors = o3d.utility.Vector3dVector(colors.astype(np.float64) / 255.0)

    down = pcd.voxel_down_sample(VOXEL_M)
    if len(down.points) < 50_000:
        raise RuntimeError(f"Unexpectedly sparse downsampled crop: {len(down.points)}")

    down.estimate_normals(
        search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=1.8, max_nn=48)
    )
    down.orient_normals_consistent_tangent_plane(30, 10.0, 0.5)

    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        down,
        depth=POISSON_DEPTH,
        scale=1.05,
        linear_fit=False,
        n_threads=-1,
    )

    density = np.asarray(densities, dtype=np.float64)
    threshold = float(np.quantile(density, DENSITY_QUANTILE))
    remove = density < threshold
    removed_low_density = int(np.count_nonzero(remove))
    mesh.remove_vertices_by_mask(remove)

    crop_box = o3d.geometry.AxisAlignedBoundingBox(
        min_bound=np.array([-CROP_HALF_M, -CROP_HALF_M, -120.0]),
        max_bound=np.array([CROP_HALF_M, CROP_HALF_M, 180.0]),
    )
    mesh = mesh.crop(crop_box)
    mesh.remove_duplicated_vertices()
    mesh.remove_duplicated_triangles()
    mesh.remove_degenerate_triangles()
    mesh.remove_non_manifold_edges()
    mesh.remove_unreferenced_vertices()
    mesh.compute_vertex_normals()

    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    triangles = np.asarray(mesh.triangles, dtype=np.int32)
    if vertices.shape[0] < 10_000 or triangles.shape[0] < 20_000:
        raise RuntimeError(
            f"Poisson mesh too small: {vertices.shape[0]} vertices, "
            f"{triangles.shape[0]} triangles"
        )

    source_points = np.asarray(down.points, dtype=np.float64)
    source_colors = np.asarray(down.colors, dtype=np.float64)
    tree = cKDTree(source_points)
    nearest = np.empty(vertices.shape[0], dtype=np.int64)
    for start in range(0, vertices.shape[0], 200_000):
        end = min(vertices.shape[0], start + 200_000)
        _, idx = tree.query(vertices[start:end], k=1, workers=-1)
        nearest[start:end] = idx
    vertex_colors = np.clip(source_colors[nearest], 0.0, 1.0)
    mesh.vertex_colors = o3d.utility.Vector3dVector(vertex_colors)

    return mesh, down, {
        "voxel_m": VOXEL_M,
        "downsampled_points": int(len(down.points)),
        "poisson_depth": POISSON_DEPTH,
        "density_quantile": DENSITY_QUANTILE,
        "density_threshold": threshold,
        "removed_low_density_vertices": removed_low_density,
        "mesh_vertices": int(vertices.shape[0]),
        "mesh_triangles": int(triangles.shape[0]),
    }


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


def fill_small_holes(rgb, occupied, radius_px=1.6):
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


def prepare_renderer(mesh):
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    triangles = np.asarray(mesh.triangles, dtype=np.int32)
    colors = np.asarray(mesh.vertex_colors, dtype=np.float64)

    tri_vertices = vertices[triangles]
    edge1 = tri_vertices[:, 1] - tri_vertices[:, 0]
    edge2 = tri_vertices[:, 2] - tri_vertices[:, 0]
    areas = 0.5 * np.linalg.norm(np.cross(edge1, edge2), axis=1)
    valid = areas > 1e-8
    triangles = triangles[valid]
    areas = areas[valid]
    cdf = np.cumsum(areas)
    cdf /= cdf[-1]
    return vertices, triangles, colors, cdf


def project_samples(
    sampled,
    sampled_colors,
    camera,
    target,
    lens_mm,
    depth_buffer,
    color_buffer,
):
    right, up, forward = camera_basis(camera, target)
    focal_px = float(lens_mm) / SENSOR_WIDTH_MM * WIDTH
    cx = WIDTH * 0.5
    cy = HEIGHT * 0.5

    rel = sampled - camera[None, :]
    cam_x = rel @ right
    cam_y = rel @ up
    cam_z = rel @ forward

    visible = cam_z > 1.0
    if not np.any(visible):
        return 0, 0
    cam_x = cam_x[visible]
    cam_y = cam_y[visible]
    cam_z = cam_z[visible]
    colors = sampled_colors[visible]

    u = np.rint(cx + focal_px * cam_x / cam_z).astype(np.int32)
    v = np.rint(cy - focal_px * cam_y / cam_z).astype(np.int32)
    inside = (u >= 0) & (u < WIDTH) & (v >= 0) & (v < HEIGHT)
    if not np.any(inside):
        return 0, 0

    u = u[inside]
    v = v[inside]
    depth = cam_z[inside].astype(np.float32)
    colors = colors[inside]
    pixel = v.astype(np.int64) * WIDTH + u.astype(np.int64)
    writes = update_zbuffer(depth_buffer, color_buffer, pixel, depth, colors)
    return int(pixel.size), writes


def render_mesh(mesh, camera, base_target):
    vertices, triangles, vertex_colors, cdf = prepare_renderer(mesh)
    rng = np.random.default_rng(20261002)

    buffers = {}
    targets = {}
    for variant in VARIANTS:
        target = base_target.copy()
        target[2] += float(variant["target_z_offset_m"])
        targets[variant["name"]] = target
        buffers[variant["name"]] = {
            "depth": np.full(WIDTH * HEIGHT, np.inf, dtype=np.float32),
            "color": np.zeros((WIDTH * HEIGHT, 3), dtype=np.uint8),
            "projected_samples": 0,
            "zbuffer_writes": 0,
        }

    remaining = SURFACE_SAMPLES
    while remaining > 0:
        count = min(SAMPLE_CHUNK, remaining)
        remaining -= count

        r = rng.random(count)
        tri_idx = np.searchsorted(cdf, r, side="right")
        tri = triangles[tri_idx]

        u = rng.random(count)
        v = rng.random(count)
        su = np.sqrt(u)
        w0 = 1.0 - su
        w1 = su * (1.0 - v)
        w2 = su * v

        p0 = vertices[tri[:, 0]]
        p1 = vertices[tri[:, 1]]
        p2 = vertices[tri[:, 2]]
        sampled = (
            p0 * w0[:, None]
            + p1 * w1[:, None]
            + p2 * w2[:, None]
        )

        c0 = vertex_colors[tri[:, 0]]
        c1 = vertex_colors[tri[:, 1]]
        c2 = vertex_colors[tri[:, 2]]
        sampled_colors = np.clip(
            (
                c0 * w0[:, None]
                + c1 * w1[:, None]
                + c2 * w2[:, None]
            )
            * 255.0,
            0,
            255,
        ).astype(np.uint8)

        for variant in VARIANTS:
            buf = buffers[variant["name"]]
            projected, writes = project_samples(
                sampled,
                sampled_colors,
                camera,
                targets[variant["name"]],
                float(variant["lens_mm"]),
                buf["depth"],
                buf["color"],
            )
            buf["projected_samples"] += projected
            buf["zbuffer_writes"] += writes

    receipts = []
    sky = np.array([158, 178, 207], dtype=np.uint8)
    for variant in VARIANTS:
        name = variant["name"]
        buf = buffers[name]
        occupied = np.isfinite(buf["depth"]).reshape((HEIGHT, WIDTH))
        image = buf["color"].reshape((HEIGHT, WIDTH, 3)).copy()
        before = int(np.count_nonzero(occupied))
        image, filled = fill_small_holes(image, occupied, radius_px=1.6)
        after = int(np.count_nonzero(filled))
        image[~filled] = sky

        path = OUT / f"coimbra-v2-lidar-mesh-{name}.png"
        Image.fromarray(image, mode="RGB").save(path)
        receipts.append(
            {
                **variant,
                "image": path.relative_to(ROOT).as_posix(),
                "surface_samples": SURFACE_SAMPLES,
                "projected_samples": int(buf["projected_samples"]),
                "zbuffer_writes": int(buf["zbuffer_writes"]),
                "occupied_pixels_before_fill": before,
                "occupied_pixels_after_fill": after,
                "occupied_fraction_after_fill": after / (WIDTH * HEIGHT),
            }
        )
    return receipts


def main():
    for required in (CONFIG, TERRAIN, HAG):
        if not required.is_file():
            raise SystemExit(f"Missing input: {required}")

    base_camera_abs, base_target_abs = hero_camera_absolute()
    center_abs = base_target_abs.copy()
    feature, point_path = download_tile()

    xyz, colors, class_counts, hard_points = load_crop(point_path, center_abs)
    mesh, down, mesh_stats = reconstruct_mesh(xyz, colors)

    mesh_path = OUT / "coimbra-v2-lidar-hard-surface-poisson.ply"
    o3d.io.write_triangle_mesh(
        str(mesh_path),
        mesh,
        write_ascii=False,
        compressed=False,
        write_vertex_normals=True,
        write_vertex_colors=True,
    )

    camera = base_camera_abs - center_abs
    camera[2] += 70.0
    base_target = base_target_abs - center_abs
    variants = render_mesh(mesh, camera, base_target)

    manifest = {
        "version": "coimbra-v2-lidar-poisson-mesh-v1",
        "source": "DGT raw classified LiDAR XYZ+RGB",
        "feature_id": feature.get("id"),
        "crop_center_epsg3763": center_abs.tolist(),
        "crop_size_m": [CROP_HALF_M * 2.0, CROP_HALF_M * 2.0],
        "hard_surface_classes": sorted(HARD_CLASSES),
        "hard_surface_points_in_crop": hard_points,
        "class_counts_in_crop": class_counts,
        "mesh": {
            **mesh_stats,
            "file": mesh_path.relative_to(ROOT).as_posix(),
            "bytes": mesh_path.stat().st_size,
        },
        "render": {
            "resolution": [WIDTH, HEIGHT],
            "sensor_width_mm": SENSOR_WIDTH_MM,
            "camera_local": camera.tolist(),
            "base_target_local": base_target.tolist(),
            "variants": variants,
        },
        "note": (
            "300x300m hard-surface Poisson reconstruction from raw DGT LiDAR. "
            "No OSM geometry, no Sketchfab photogrammetry, no MDS/HAG geometry "
            "reconstruction. RGB transferred from raw LiDAR by nearest neighbour."
        ),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))

    point_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
