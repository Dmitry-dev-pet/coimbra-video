from __future__ import annotations

import json
import math
from pathlib import Path

import cv2
import numpy as np
from pyproj import Transformer


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "coimbra_v2_001.json"
INSPECTION = ROOT / "bridge_output_v2_001" / "registration" / "photogrammetry-inspection.json"
TOPDOWN = ROOT / "bridge_output_v2_001" / "registration" / "photogrammetry-topdown.png"
VERTICES = ROOT / "bridge_output_v2_001" / "registration" / "photogrammetry-vertices.npz"
DGT_ROOT = ROOT / "bridge_output_v2_001" / "dgt"
ORTHO = DGT_ROOT / "ortho" / "coimbra-v2-001-ortho-2025.jpg"
ORTHO_META = DGT_ROOT / "ortho" / "coimbra-v2-001-ortho-2025.json"
PREPARED = DGT_ROOT / "prepared"
TERRAIN = PREPARED / "coimbra-v2-001-terrain-2m.npz"
HAG = PREPARED / "coimbra-v2-001-height-above-ground-1m.npz"
OUT = ROOT / "bridge_output_v2_001" / "registration"
REGISTRATION = OUT / "registration.json"
MATCHES = OUT / "registration-matches.jpg"


def resize_for_features(image: np.ndarray, max_side: int = 2600):
    scale = min(1.0, max_side / max(image.shape[:2]))
    if scale == 1.0:
        return image, 1.0
    resized = cv2.resize(
        image,
        (int(round(image.shape[1] * scale)), int(round(image.shape[0] * scale))),
        interpolation=cv2.INTER_AREA,
    )
    return resized, scale


def enhanced_gray(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)


def model_xy(points: np.ndarray, inspection: dict) -> np.ndarray:
    width, height = inspection["topdown_size"]
    bounds = inspection["topdown_model_xy"]
    x = bounds["min_x"] + points[:, 0] / (width - 1) * (
        bounds["max_x"] - bounds["min_x"]
    )
    y = bounds["max_y"] - points[:, 1] / (height - 1) * (
        bounds["max_y"] - bounds["min_y"]
    )
    return np.column_stack([x, y]).astype(np.float64)


def dgt_local_xy(
    points: np.ndarray, meta: dict, center_abs: np.ndarray
) -> np.ndarray:
    width, height = meta["image_size"]
    minx, miny, maxx, maxy = meta["bbox_epsg3763"]
    x = minx + points[:, 0] / (width - 1) * (maxx - minx)
    y = maxy - points[:, 1] / (height - 1) * (maxy - miny)
    absolute = np.column_stack([x, y]).astype(np.float64)
    return absolute - center_abs


def grid_indices(
    xs: np.ndarray,
    ys: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if len(xs) < 2 or len(ys) < 2:
        raise RuntimeError("DGT grid is too small")
    dx = float(xs[1] - xs[0])
    dy = float(ys[1] - ys[0])
    if dx == 0.0 or dy == 0.0:
        raise RuntimeError("DGT grid has zero coordinate step")

    cols = np.rint((x - float(xs[0])) / dx).astype(np.int64)
    rows = np.rint((y - float(ys[0])) / dy).astype(np.int64)
    valid = (
        (rows >= 0)
        & (rows < len(ys))
        & (cols >= 0)
        & (cols < len(xs))
    )
    return rows, cols, valid


def sample_grid(
    values: np.ndarray,
    xs: np.ndarray,
    ys: np.ndarray,
    x: float,
    y: float,
) -> float:
    rows, cols, valid = grid_indices(
        xs,
        ys,
        np.asarray([x], dtype=np.float64),
        np.asarray([y], dtype=np.float64),
    )
    if not bool(valid[0]):
        raise RuntimeError(f"Point {x:.3f},{y:.3f} lies outside DGT grid")
    return float(values[int(rows[0]), int(cols[0])])


def surface_at(
    terrain: dict[str, np.ndarray],
    hag: dict[str, np.ndarray],
    x: float,
    y: float,
) -> float:
    ground = sample_grid(terrain["z"], terrain["xs"], terrain["ys"], x, y)
    above = sample_grid(hag["height"], hag["xs"], hag["ys"], x, y)
    return ground + max(0.0, above)


def estimate_vertical_offset(
    vertices: np.ndarray,
    affine: np.ndarray,
    scale: float,
    terrain: dict[str, np.ndarray],
    hag: dict[str, np.ndarray],
    terrain_z0: float,
) -> tuple[float, dict]:
    local_xy = np.column_stack(
        [
            affine[0, 0] * vertices[:, 0]
            + affine[0, 1] * vertices[:, 1]
            + affine[0, 2],
            affine[1, 0] * vertices[:, 0]
            + affine[1, 1] * vertices[:, 1]
            + affine[1, 2],
        ]
    )

    hrows, hcols, valid = grid_indices(
        hag["xs"], hag["ys"], local_xy[:, 0], local_xy[:, 1]
    )
    hrows = hrows[valid]
    hcols = hcols[valid]
    model_z = vertices[valid, 2] * scale

    if model_z.size < 500:
        raise RuntimeError(
            f"Too few photogrammetry vertices overlap DGT HAG: {model_z.size}"
        )

    width = len(hag["xs"])
    linear = hrows * width + hcols
    order = np.argsort(linear)
    linear = linear[order]
    model_z = model_z[order]
    unique, first = np.unique(linear, return_index=True)
    model_surface = np.maximum.reduceat(model_z, first)

    unique_rows = unique // width
    unique_cols = unique % width
    cell_x = hag["xs"][unique_cols].astype(np.float64)
    cell_y = hag["ys"][unique_rows].astype(np.float64)
    hag_surface = hag["height"][unique_rows, unique_cols].astype(np.float64)

    trows, tcols, terrain_valid = grid_indices(
        terrain["xs"], terrain["ys"], cell_x, cell_y
    )
    dgt_surface = np.full(model_surface.shape, np.nan, dtype=np.float64)
    dgt_surface[terrain_valid] = (
        terrain["z"][trows[terrain_valid], tcols[terrain_valid]].astype(np.float64)
        + np.maximum(0.0, hag_surface[terrain_valid])
    )

    finite = np.isfinite(dgt_surface) & np.isfinite(model_surface)
    residuals = dgt_surface[finite] - model_surface[finite]

    if residuals.size < 250:
        raise RuntimeError(
            f"Too few DGT surface overlap cells for vertical registration: {residuals.size}"
        )

    median = float(np.median(residuals))
    mad = float(np.median(np.abs(residuals - median)))
    threshold = max(2.0, 4.0 * mad)
    clipped = residuals[np.abs(residuals - median) <= threshold]
    if clipped.size < 200:
        raise RuntimeError("Vertical registration rejected too many DGT samples")

    absolute_offset = float(np.median(clipped))
    return absolute_offset - terrain_z0, {
        "overlap_cells": int(residuals.size),
        "kept_cells": int(clipped.size),
        "median_absolute_z_offset_m": absolute_offset,
        "mad_m": mad,
        "clip_threshold_m": threshold,
        "surface_source": "DGT terrain 2m + max-pooled LiDAR HAG 1m",
    }


def load_npz(path: Path, keys: tuple[str, ...]) -> dict[str, np.ndarray]:
    data = np.load(path)
    result = {}
    for key in keys:
        if key not in data:
            raise RuntimeError(f"{path.name} missing {key}")
        result[key] = data[key]
    return result


def main() -> None:
    for path in (
        CONFIG,
        INSPECTION,
        TOPDOWN,
        VERTICES,
        ORTHO,
        ORTHO_META,
        TERRAIN,
        HAG,
    ):
        if not path.is_file():
            raise SystemExit(f"Missing V2-001 registration input: {path}")

    cfg = json.loads(CONFIG.read_text())
    inspection = json.loads(INSPECTION.read_text())
    ortho_meta = json.loads(ORTHO_META.read_text())

    terrain_file = np.load(TERRAIN)
    center_abs = np.array(
        [float(terrain_file["center_x"]), float(terrain_file["center_y"])],
        dtype=np.float64,
    )
    terrain_z0 = float(terrain_file["z0"])
    terrain = {
        "z": terrain_file["z"].astype(np.float64),
        "xs": terrain_file["xs"].astype(np.float64),
        "ys": terrain_file["ys"].astype(np.float64),
    }
    hag = load_npz(HAG, ("height", "xs", "ys"))
    hag = {key: value.astype(np.float64) for key, value in hag.items()}

    photo_full = cv2.imread(str(TOPDOWN), cv2.IMREAD_COLOR)
    dgt_full = cv2.imread(str(ORTHO), cv2.IMREAD_COLOR)
    if photo_full is None or dgt_full is None:
        raise RuntimeError("Could not load registration images")

    photo, photo_scale = resize_for_features(photo_full)
    dgt, dgt_scale = resize_for_features(dgt_full)

    detector = cv2.SIFT_create(nfeatures=10_000)
    kp_photo, desc_photo = detector.detectAndCompute(enhanced_gray(photo), None)
    kp_dgt, desc_dgt = detector.detectAndCompute(enhanced_gray(dgt), None)
    if desc_photo is None or desc_dgt is None:
        raise RuntimeError("SIFT found no usable descriptors")

    matcher = cv2.BFMatcher(cv2.NORM_L2)
    pairs = matcher.knnMatch(desc_photo, desc_dgt, k=2)
    good = [a for a, b in pairs if a.distance < 0.72 * b.distance]
    if len(good) < 40:
        raise RuntimeError(f"Too few photogrammetry/DGT feature matches: {len(good)}")

    photo_px = np.array(
        [kp_photo[m.queryIdx].pt for m in good], dtype=np.float64
    ) / photo_scale
    dgt_px = np.array(
        [kp_dgt[m.trainIdx].pt for m in good], dtype=np.float64
    ) / dgt_scale

    source_xy = model_xy(photo_px, inspection)
    target_xy = dgt_local_xy(dgt_px, ortho_meta, center_abs)

    affine, inlier_mask = cv2.estimateAffinePartial2D(
        source_xy,
        target_xy,
        method=cv2.RANSAC,
        ransacReprojThreshold=6.0,
        maxIters=20_000,
        confidence=0.999,
        refineIters=50,
    )
    if affine is None or inlier_mask is None:
        raise RuntimeError("Could not estimate V2 photogrammetry similarity transform")

    inliers = inlier_mask.ravel().astype(bool)
    inlier_count = int(inliers.sum())
    inlier_ratio = float(inlier_count / len(good))
    if inlier_count < 24 or inlier_ratio < 0.15:
        raise RuntimeError(
            f"Weak V2 registration: {inlier_count} inliers, ratio={inlier_ratio:.3f}"
        )

    a = float(affine[0, 0])
    b = float(affine[1, 0])
    scale = math.hypot(a, b)
    rotation = math.atan2(b, a)
    if not 0.01 <= scale <= 100.0:
        raise RuntimeError(f"Implausible photogrammetry scale: {scale}")

    vertices = np.load(VERTICES)["xyz"].astype(np.float64)
    z_offset_local, z_evidence = estimate_vertical_offset(
        vertices, affine, scale, terrain, hag, terrain_z0
    )
    z_offset_local += float(cfg["hero"]["photogrammetry_z_bias_m"])

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3763", always_xy=True)
    camera_cfg = cfg["hero"]["camera_anchor"]
    target_cfg = cfg["hero"]["target"]
    camera_abs = transformer.transform(camera_cfg["lon"], camera_cfg["lat"])
    target_abs = transformer.transform(target_cfg["lon"], target_cfg["lat"])

    camera_x = float(camera_abs[0] - center_abs[0])
    camera_y = float(camera_abs[1] - center_abs[1])
    target_x = float(target_abs[0] - center_abs[0])
    target_y = float(target_abs[1] - center_abs[1])

    camera_ground = sample_grid(
        terrain["z"], terrain["xs"], terrain["ys"], camera_x, camera_y
    )
    target_surface = surface_at(terrain, hag, target_x, target_y)

    camera_local = [
        camera_x,
        camera_y,
        float(camera_ground + cfg["hero"]["camera_height_agl_m"] - terrain_z0),
    ]
    target_local = [
        target_x,
        target_y,
        float(
            target_surface
            + cfg["hero"]["target_height_above_surface_m"]
            - terrain_z0
        ),
    ]

    inlier_matches = [m for m, ok in zip(good, inliers) if ok][:120]
    evidence = cv2.drawMatches(
        photo,
        kp_photo,
        dgt,
        kp_dgt,
        inlier_matches,
        None,
        flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS,
    )
    OUT.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(MATCHES), evidence)

    payload = {
        "version": "coimbra-v2-001-registration-v1",
        "method": (
            "SIFT + RANSAC 2D similarity; "
            "DGT terrain 2m + LiDAR HAG 1m vertical median"
        ),
        "feature_matches": len(good),
        "inliers": inlier_count,
        "inlier_ratio": inlier_ratio,
        "model_to_local_epsg3763": affine.tolist(),
        "scale": scale,
        "rotation_z_radians": rotation,
        "rotation_z_degrees": math.degrees(rotation),
        "translation_local_xy_m": [float(affine[0, 2]), float(affine[1, 2])],
        "translation_local_z_m": z_offset_local,
        "dgt_center_epsg3763": center_abs.tolist(),
        "terrain_z0_m": terrain_z0,
        "vertical_evidence": z_evidence,
        "hero_camera_local": camera_local,
        "hero_target_local": target_local,
        "matches_image": MATCHES.relative_to(ROOT).as_posix(),
    }
    REGISTRATION.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
