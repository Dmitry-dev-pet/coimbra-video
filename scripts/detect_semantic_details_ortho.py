from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from skimage import measure, morphology, segmentation


ROOT = Path(__file__).resolve().parents[1]
ORTHO = ROOT / "data" / "processed" / "bridge_ortho_2025.jpg"
ORTHO_META = ROOT / "data" / "processed" / "bridge_ortho_2025.json"
HAG = ROOT / "bridge_output_008b" / "bridge_height_above_ground_1m.npz"
OUT = ROOT / "data" / "processed" / "bridge_semantic_details_2025.json"
PREVIEW = ROOT / "data" / "processed" / "bridge_semantic_details_2025_preview.jpg"

MODEL_RESOLUTION_M = 0.50
TILE = 1024
OVERLAP = 128
RANGELAND_CLASS = 1
TREE_CLASS = 4
WATER_CLASS = 5
MIN_TREE_HAG_M = 1.8
TREE_DEDUPE_M = 2.0
MAX_TREES = 12000
MAX_CANOPY_MASS_POINTS = 22000
MIN_CANOPY_REGION_M2 = 60.0
CANOPY_STEP_M = 1.65
MAX_UNDERGROWTH_POINTS = 18000
MIN_UNDERGROWTH_REGION_M2 = 24.0
UNDERGROWTH_STEP_M = 1.35
POOL_MIN_AREA_M2 = 8.0
POOL_MAX_AREA_M2 = 900.0


def tile_origins(size: int, tile: int, overlap: int) -> list[int]:
    if size <= tile:
        return [0]
    step = tile - overlap
    origins = list(range(0, max(1, size - tile + 1), step))
    last = size - tile
    if origins[-1] != last:
        origins.append(last)
    return origins


def setup_oem(oem_root: Path, arch: Path, weights: Path):
    old_cwd = Path.cwd()
    os.chdir(oem_root)
    try:
        for path in (oem_root, oem_root / "oem_lightweight", oem_root / "fasterseg_api"):
            if str(path) not in sys.path:
                sys.path.insert(0, str(path))

        import torch
        from config import config
        from oem_lightweight.model import fasterseg

        config.use_tta = False
        model_info = fasterseg(str(arch), str(weights))
        model = model_info["model"]
        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        model.to(device)
        model.eval()
        return torch, config, model, device
    finally:
        os.chdir(old_cwd)


def infer_tile(torch, config, model, device, rgb: np.ndarray) -> np.ndarray:
    from torchvision import transforms

    transform = transforms.Compose(
        [
            transforms.ToTensor(),
            transforms.Normalize(**config.stats),
        ]
    )
    tensor = transform(rgb.astype(np.uint8))[None, :, :, :].to(device)
    with torch.no_grad():
        output = model(tensor)
        pred = output[0].permute(1, 2, 0).cpu().numpy().argmax(2)
    return pred.astype(np.uint8)


def semantic_masks(
    image: Image.Image,
    torch,
    config,
    model,
    device,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rgb = np.asarray(image, dtype=np.uint8)
    height, width = rgb.shape[:2]
    rangeland_votes = np.zeros((height, width), dtype=np.uint8)
    tree_votes = np.zeros((height, width), dtype=np.uint8)
    water_votes = np.zeros((height, width), dtype=np.uint8)
    coverage = np.zeros((height, width), dtype=np.uint8)

    xs = tile_origins(width, TILE, OVERLAP)
    ys = tile_origins(height, TILE, OVERLAP)
    total = len(xs) * len(ys)
    index = 0
    for y0 in ys:
        for x0 in xs:
            index += 1
            tile = rgb[y0 : y0 + TILE, x0 : x0 + TILE]
            valid_h, valid_w = tile.shape[:2]
            if valid_h != TILE or valid_w != TILE:
                padded = np.empty((TILE, TILE, 3), dtype=np.uint8)
                padded[:] = tile[-1, -1]
                padded[:valid_h, :valid_w] = tile
                tile = padded

            pred = infer_tile(torch, config, model, device, tile)
            pred = pred[:valid_h, :valid_w]
            sl = np.s_[y0 : y0 + valid_h, x0 : x0 + valid_w]
            coverage[sl] += 1
            rangeland_votes[sl] += (pred == RANGELAND_CLASS).astype(np.uint8)
            tree_votes[sl] += (pred == TREE_CLASS).astype(np.uint8)
            water_votes[sl] += (pred == WATER_CLASS).astype(np.uint8)
            print(
                f"OEM tile {index}/{total}: "
                f"rangeland={int(np.sum(pred == RANGELAND_CLASS))} "
                f"tree={int(np.sum(pred == TREE_CLASS))} "
                f"water={int(np.sum(pred == WATER_CLASS))}"
            )

    threshold = np.maximum(1, np.ceil(coverage * 0.5)).astype(np.uint8)
    rangeland = rangeland_votes >= threshold
    tree = tree_votes >= threshold
    water = water_votes >= threshold

    rangeland = morphology.remove_small_objects(rangeland, min_size=16)
    rangeland = morphology.remove_small_holes(rangeland, area_threshold=24)
    tree = morphology.remove_small_objects(tree, min_size=20)
    tree = morphology.remove_small_holes(tree, area_threshold=32)
    water = morphology.remove_small_objects(water, min_size=12)
    water = morphology.remove_small_holes(water, area_threshold=20)
    return rangeland, tree, water


def local_to_pixel(
    x_local: float,
    y_local: float,
    *,
    center_x: float,
    center_y: float,
    minx: float,
    maxy: float,
    resolution: float,
):
    x_abs = center_x + x_local
    y_abs = center_y + y_local
    px = (x_abs - minx) / resolution
    py = (maxy - y_abs) / resolution
    return px, py


def pixel_to_local(
    px: float,
    py: float,
    *,
    center_x: float,
    center_y: float,
    minx: float,
    maxy: float,
    resolution: float,
):
    x_abs = minx + px * resolution
    y_abs = maxy - py * resolution
    return x_abs - center_x, y_abs - center_y


def hag_grid_for_model(
    hag_data,
    ortho_meta: dict,
    shape: tuple[int, int],
    resolution: float,
) -> np.ndarray:
    height = hag_data["height"].astype(np.float32)
    xs = hag_data["xs"].astype(np.float32)
    ys = hag_data["ys"].astype(np.float32)
    center_x = float(hag_data["center_x"])
    center_y = float(hag_data["center_y"])
    minx, _miny, _maxx, maxy = map(float, ortho_meta["bbox_epsg3763"])

    rows, cols = shape
    x_local = (
        minx + (np.arange(cols, dtype=np.float32) + 0.5) * resolution
        - center_x
    )
    y_local = (
        maxy - (np.arange(rows, dtype=np.float32) + 0.5) * resolution
        - center_y
    )

    x_index = np.interp(
        x_local,
        xs,
        np.arange(len(xs), dtype=np.float32),
    )
    if ys[0] > ys[-1]:
        y_index = np.interp(
            y_local,
            ys[::-1],
            np.arange(len(ys), dtype=np.float32)[::-1],
        )
    else:
        y_index = np.interp(
            y_local,
            ys,
            np.arange(len(ys), dtype=np.float32),
        )

    xi = np.clip(np.rint(x_index).astype(np.int32), 0, len(xs) - 1)
    yi = np.clip(np.rint(y_index).astype(np.int32), 0, len(ys) - 1)
    return height[yi[:, None], xi[None, :]]


def crown_labels(tree_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    distance_px = ndi.distance_transform_edt(tree_mask)

    # Shape-driven crown seeds. The semantic mask says "this is canopy";
    # LiDAR is deliberately not used to choose tree centers.
    local_max = (
        distance_px
        >= ndi.maximum_filter(distance_px, size=9, mode="nearest") - 1e-6
    )
    seeds = local_max & tree_mask & (distance_px >= 2.2)
    markers, _ = ndi.label(seeds)

    if int(markers.max()) <= 0:
        markers, _ = ndi.label(tree_mask)

    labels = segmentation.watershed(
        -distance_px,
        markers,
        mask=tree_mask,
        watershed_line=False,
    )
    return labels.astype(np.int32), distance_px


def robust_crown_height(values: np.ndarray, crown_radius_m: float):
    valid = values[np.isfinite(values)]
    valid = valid[(valid >= 0.0) & (valid <= 40.0)]
    elevated = valid[valid >= 1.2]

    if elevated.size >= 3:
        return (
            float(np.percentile(elevated, 90)),
            "crown-p90-lidar-hag",
            int(elevated.size),
        )

    # HAG can be weak over foliage. In that case keep the semantically proven
    # crown instead of deleting the tree, but use a conservative geometry-only
    # fallback height.
    fallback = 4.2 + min(5.0, crown_radius_m * 1.35)
    return float(fallback), "crown-semantic-fallback", int(elevated.size)


def extract_trees(
    tree_mask: np.ndarray,
    hag_data,
    ortho_meta: dict,
    resolution: float,
):
    center_x = float(hag_data["center_x"])
    center_y = float(hag_data["center_y"])
    minx, _miny, _maxx, maxy = map(float, ortho_meta["bbox_epsg3763"])

    labels, distance_px = crown_labels(tree_mask)
    hag_grid = hag_grid_for_model(
        hag_data,
        ortho_meta,
        tree_mask.shape,
        resolution,
    )

    candidates = []
    for region in measure.regionprops(labels):
        area_m2 = float(region.area) * resolution * resolution
        if area_m2 < 2.5:
            continue

        cy_px, cx_px = region.centroid
        radius_area = math.sqrt(area_m2 / math.pi)
        radius_distance = float(distance_px[labels == region.label].max()) * resolution
        radius = max(
            1.0,
            min(6.2, max(radius_area * 0.82, radius_distance * 0.92)),
        )

        region_values = hag_grid[labels == region.label]
        height, height_source, hag_samples = robust_crown_height(
            region_values,
            radius,
        )

        x_local, y_local = pixel_to_local(
            float(cx_px),
            float(cy_px),
            center_x=center_x,
            center_y=center_y,
            minx=minx,
            maxy=maxy,
            resolution=resolution,
        )

        candidates.append(
            {
                "x": float(x_local),
                "y": float(y_local),
                "height": float(max(3.0, min(20.0, height))),
                "radius": float(radius),
                "height_source": height_source,
                "crown_area_m2": area_m2,
                "hag_samples": hag_samples,
            }
        )

    if len(candidates) > MAX_TREES:
        # Prefer larger, better-supported crowns; use stable spatial tie-break.
        import hashlib

        def rank(item):
            token = ("%.2f:%.2f" % (item["x"], item["y"])).encode()
            tie = int.from_bytes(hashlib.sha256(token).digest()[:8], "big")
            support = min(30, int(item["hag_samples"]))
            score = (
                float(item["crown_area_m2"]) * 1000.0
                + support * 50.0
                + min(20.0, float(item["height"])) * 10.0
            )
            return (-score, tie)

        candidates.sort(key=rank)
        candidates = candidates[:MAX_TREES]

    return sorted(candidates, key=lambda item: (item["y"], item["x"])), labels, hag_grid


def masked_local_height(
    hag_grid: np.ndarray,
    region_mask: np.ndarray,
    cy: int,
    cx: int,
    radius_px: int = 6,
):
    y0 = max(0, cy - radius_px)
    y1 = min(hag_grid.shape[0], cy + radius_px + 1)
    x0 = max(0, cx - radius_px)
    x1 = min(hag_grid.shape[1], cx + radius_px + 1)

    values = hag_grid[y0:y1, x0:x1][region_mask[y0:y1, x0:x1]]
    values = values[np.isfinite(values)]
    values = values[(values >= 0.0) & (values <= 40.0)]
    if values.size < 3:
        return None, int(values.size)
    return float(np.percentile(values, 75)), int(values.size)


def extract_canopy_masses(
    tree_mask: np.ndarray,
    hag_data,
    ortho_meta: dict,
    resolution: float,
    hag_grid: np.ndarray | None = None,
):
    center_x = float(hag_data["center_x"])
    center_y = float(hag_data["center_y"])
    minx, _miny, _maxx, maxy = map(float, ortho_meta["bbox_epsg3763"])

    if hag_grid is None:
        hag_grid = hag_grid_for_model(
            hag_data,
            ortho_meta,
            tree_mask.shape,
            resolution,
        )

    labels = measure.label(tree_mask, connectivity=2)
    step_px = max(2, int(round(CANOPY_STEP_M / resolution)))
    points = []
    region_summaries = []

    for region in measure.regionprops(labels):
        area_m2 = float(region.area) * resolution * resolution
        if area_m2 < MIN_CANOPY_REGION_M2:
            continue

        region_mask = labels == region.label
        minr, minc, maxr, maxc = region.bbox
        component = region_mask[minr:maxr, minc:maxc]
        local_distance = ndi.distance_transform_edt(component) * resolution
        accepted = 0
        forest_points = 0
        scrub_points = 0

        for local_y in range(step_px // 2, component.shape[0], step_px):
            offset = (step_px // 2) if ((local_y // step_px) % 2) else 0
            for local_x in range(step_px // 2 + offset, component.shape[1], step_px):
                if not component[local_y, local_x]:
                    continue
                edge_distance = float(local_distance[local_y, local_x])
                if edge_distance < 0.45:
                    continue

                py = int(minr + local_y)
                px = int(minc + local_x)
                x_local, y_local = pixel_to_local(
                    float(px),
                    float(py),
                    center_x=center_x,
                    center_y=center_y,
                    minx=minx,
                    maxy=maxy,
                    resolution=resolution,
                )

                # Crucially: height samples come only from this same connected
                # canopy region, so neighboring buildings/slopes cannot leak in.
                hag_height, hag_samples = masked_local_height(
                    hag_grid,
                    region_mask,
                    py,
                    px,
                    radius_px=max(3, int(round(3.0 / resolution))),
                )

                if hag_height is not None and hag_height >= 3.6:
                    kind = "forest"
                    height = max(2.8, min(9.0, hag_height * 0.60))
                    radius = max(1.15, min(2.65, 1.10 + edge_distance * 0.34))
                    forest_points += 1
                    height_source = "region-local-p75-lidar-hag"
                else:
                    kind = "scrub"
                    height = max(1.10, min(3.4, 1.20 + edge_distance * 0.38))
                    radius = max(0.95, min(2.15, 0.95 + edge_distance * 0.28))
                    scrub_points += 1
                    height_source = "semantic-scrub"

                points.append(
                    {
                        "x": float(x_local),
                        "y": float(y_local),
                        "height": float(height),
                        "radius": float(radius),
                        "kind": kind,
                        "height_source": height_source,
                        "hag_samples": hag_samples,
                        "region_area_m2": area_m2,
                    }
                )
                accepted += 1

        region_summaries.append(
            {
                "area_m2": area_m2,
                "points": accepted,
                "forest_points": forest_points,
                "scrub_points": scrub_points,
            }
        )

    if len(points) > MAX_CANOPY_MASS_POINTS:
        import hashlib

        def rank(item):
            token = ("mass:%.2f:%.2f" % (item["x"], item["y"])).encode()
            return hashlib.sha256(token).digest()

        points.sort(key=rank)
        points = points[:MAX_CANOPY_MASS_POINTS]

    return points, region_summaries


def extract_undergrowth(
    rangeland_mask: np.ndarray,
    image: Image.Image,
    hag_data,
    ortho_meta: dict,
    resolution: float,
):
    rgb = np.asarray(image, dtype=np.uint8)
    center_x = float(hag_data["center_x"])
    center_y = float(hag_data["center_y"])
    minx, _miny, _maxx, maxy = map(float, ortho_meta["bbox_epsg3763"])

    hag_grid = hag_grid_for_model(
        hag_data,
        ortho_meta,
        rangeland_mask.shape,
        resolution,
    )
    labels = measure.label(rangeland_mask, connectivity=2)
    step_px = max(2, int(round(UNDERGROWTH_STEP_M / resolution)))

    points = []
    regions = []
    for region in measure.regionprops(labels):
        area_m2 = float(region.area) * resolution * resolution
        if area_m2 < MIN_UNDERGROWTH_REGION_M2:
            continue

        region_mask = labels == region.label
        minr, minc, maxr, maxc = region.bbox
        component = region_mask[minr:maxr, minc:maxc]
        local_distance = ndi.distance_transform_edt(component) * resolution
        accepted = 0
        green_points = 0
        dry_points = 0

        for local_y in range(step_px // 2, component.shape[0], step_px):
            offset = (step_px // 2) if ((local_y // step_px) % 2) else 0
            for local_x in range(step_px // 2 + offset, component.shape[1], step_px):
                if not component[local_y, local_x]:
                    continue
                edge_distance = float(local_distance[local_y, local_x])
                if edge_distance < 0.35:
                    continue

                py = int(minr + local_y)
                px = int(minc + local_x)
                r, g, b = map(float, rgb[py, px])

                # OpenEarthMap rangeland includes both lush and dry Mediterranean
                # scrub. Keep both, but render them with different materials.
                green_score = g - 0.5 * (r + b)
                dry_score = r - b
                if green_score >= 2.0:
                    kind = "green-scrub"
                    green_points += 1
                else:
                    kind = "dry-scrub"
                    dry_points += 1

                x_local, y_local = pixel_to_local(
                    float(px),
                    float(py),
                    center_x=center_x,
                    center_y=center_y,
                    minx=minx,
                    maxy=maxy,
                    resolution=resolution,
                )

                hag_height, hag_samples = masked_local_height(
                    hag_grid,
                    region_mask,
                    py,
                    px,
                    radius_px=max(2, int(round(2.0 / resolution))),
                )
                if hag_height is None:
                    height = 0.85 + min(1.15, edge_distance * 0.28)
                    height_source = "semantic-fallback"
                else:
                    # Low vegetation only. Tall HAG outliers are capped rather
                    # than turning rangeland into accidental trees/buildings.
                    height = max(
                        0.65,
                        min(2.8, 0.65 + min(3.2, hag_height) * 0.55),
                    )
                    height_source = "region-local-lidar"

                radius = max(
                    0.72,
                    min(1.85, 0.72 + edge_distance * 0.30),
                )
                points.append(
                    {
                        "x": float(x_local),
                        "y": float(y_local),
                        "height": float(height),
                        "radius": float(radius),
                        "kind": kind,
                        "height_source": height_source,
                        "hag_samples": hag_samples,
                        "region_area_m2": area_m2,
                    }
                )
                accepted += 1

        regions.append(
            {
                "area_m2": area_m2,
                "points": accepted,
                "green_points": green_points,
                "dry_points": dry_points,
            }
        )

    if len(points) > MAX_UNDERGROWTH_POINTS:
        import hashlib

        def rank(item):
            token = ("under:%.2f:%.2f" % (item["x"], item["y"])).encode()
            return hashlib.sha256(token).digest()

        points.sort(key=rank)
        points = points[:MAX_UNDERGROWTH_POINTS]

    return points, regions

def region_hag(
    cx_local: float,
    cy_local: float,
    hag_data,
) -> float:
    xs = hag_data["xs"].astype(np.float32)
    ys = hag_data["ys"].astype(np.float32)
    col = int(np.argmin(np.abs(xs - cx_local)))
    row = int(np.argmin(np.abs(ys - cy_local)))
    return float(hag_data["height"][row, col])


def extract_pools(
    water_mask: np.ndarray,
    image: Image.Image,
    hag_data,
    ortho_meta: dict,
    resolution: float,
):
    rgb = np.asarray(image, dtype=np.uint8)
    labels = measure.label(water_mask, connectivity=2)
    minx, _miny, _maxx, maxy = map(float, ortho_meta["bbox_epsg3763"])
    center_x = float(hag_data["center_x"])
    center_y = float(hag_data["center_y"])
    pools = []

    for region in measure.regionprops(labels):
        area_m2 = float(region.area) * resolution * resolution
        if not (POOL_MIN_AREA_M2 <= area_m2 <= POOL_MAX_AREA_M2):
            continue
        if region.solidity < 0.55:
            continue

        minr, minc, maxr, maxc = region.bbox
        width_m = (maxc - minc) * resolution
        height_m = (maxr - minr) * resolution
        if min(width_m, height_m) < 1.7 or max(width_m, height_m) > 65.0:
            continue

        component = (labels[minr:maxr, minc:maxc] == region.label).astype(np.uint8)
        pixels = rgb[minr:maxr, minc:maxc][component.astype(bool)]
        if pixels.size == 0:
            continue
        mean_rgb = pixels.mean(axis=0)
        r, g, b = map(float, mean_rgb)
        blue_score = b - 0.5 * (r + g)
        cyan_score = 0.5 * (g + b) - r
        if max(blue_score, cyan_score) < 6.0:
            continue

        cy_px, cx_px = region.centroid
        cx_local, cy_local = pixel_to_local(
            cx_px,
            cy_px,
            center_x=center_x,
            center_y=center_y,
            minx=minx,
            maxy=maxy,
            resolution=resolution,
        )
        hag = region_hag(cx_local, cy_local, hag_data)
        if hag > 1.8:
            continue

        contours, _ = cv2.findContours(
            component,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        if not contours:
            continue
        contour = max(contours, key=cv2.contourArea)
        epsilon = max(1.0, 0.015 * cv2.arcLength(contour, True))
        approx = cv2.approxPolyDP(contour, epsilon, True).reshape(-1, 2)
        if len(approx) < 4:
            rect = cv2.minAreaRect(contour)
            approx = cv2.boxPoints(rect)

        polygon = []
        for px, py in approx:
            lx, ly = pixel_to_local(
                float(minc + px),
                float(minr + py),
                center_x=center_x,
                center_y=center_y,
                minx=minx,
                maxy=maxy,
                resolution=resolution,
            )
            polygon.append([lx, ly])

        if len(polygon) > 16:
            continue

        pools.append(
            {
                "center_local": [cx_local, cy_local],
                "polygon_local": polygon,
                "area_m2": area_m2,
                "solidity": float(region.solidity),
                "hag_m": hag,
                "mean_rgb": [round(r, 1), round(g, 1), round(b, 1)],
                "blue_score": round(float(max(blue_score, cyan_score)), 1),
            }
        )

    pools.sort(key=lambda item: item["area_m2"], reverse=True)
    return pools


def make_preview(
    image: Image.Image,
    tree_mask: np.ndarray,
    water_mask: np.ndarray,
    trees: list[dict],
    pools: list[dict],
    ortho_meta: dict,
    hag_data,
    resolution: float,
):
    preview = image.copy().convert("RGB")
    overlay = np.asarray(preview).copy()
    overlay[tree_mask] = (40, 180, 60)
    overlay[water_mask] = (30, 120, 255)
    preview = Image.blend(
        preview,
        Image.fromarray(overlay.astype(np.uint8)),
        0.34,
    )
    draw = ImageDraw.Draw(preview)
    minx, _miny, _maxx, maxy = map(float, ortho_meta["bbox_epsg3763"])
    center_x = float(hag_data["center_x"])
    center_y = float(hag_data["center_y"])

    for item in trees:
        px, py = local_to_pixel(
            item["x"],
            item["y"],
            center_x=center_x,
            center_y=center_y,
            minx=minx,
            maxy=maxy,
            resolution=resolution,
        )
        rr = max(2, int(item["radius"] / resolution))
        draw.ellipse((px - rr, py - rr, px + rr, py + rr), outline=(255, 240, 40), width=1)

    for item in pools:
        points = []
        for x, y in item["polygon_local"]:
            px, py = local_to_pixel(
                x,
                y,
                center_x=center_x,
                center_y=center_y,
                minx=minx,
                maxy=maxy,
                resolution=resolution,
            )
            points.append((px, py))
        if len(points) >= 3:
            draw.line(points + [points[0]], fill=(255, 40, 220), width=3)

    scale = min(1.0, 2200 / max(preview.size))
    if scale < 1.0:
        preview = preview.resize(
            (int(preview.width * scale), int(preview.height * scale)),
            Image.Resampling.LANCZOS,
        )
    PREVIEW.parent.mkdir(parents=True, exist_ok=True)
    preview.save(PREVIEW, quality=88)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--oem-root", required=True)
    parser.add_argument("--arch", required=True)
    parser.add_argument("--weights", required=True)
    args = parser.parse_args()

    if not ORTHO.is_file() or not ORTHO_META.is_file() or not HAG.is_file():
        raise SystemExit("Missing DGT orthophoto metadata or HAG grid")

    meta = json.loads(ORTHO_META.read_text())
    source_resolution = float(meta["resolution_m"])
    source = Image.open(ORTHO).convert("RGB")

    scale = source_resolution / MODEL_RESOLUTION_M
    model_size = (
        max(1, int(round(source.width * scale))),
        max(1, int(round(source.height * scale))),
    )
    image = source.resize(model_size, Image.Resampling.LANCZOS)
    del source

    torch, config, model, device = setup_oem(
        Path(args.oem_root).resolve(),
        Path(args.arch).resolve(),
        Path(args.weights).resolve(),
    )
    rangeland_mask, tree_mask, water_mask = semantic_masks(
        image,
        torch,
        config,
        model,
        device,
    )

    hag_data = np.load(HAG)
    trees, crown_map, hag_grid = extract_trees(
        tree_mask,
        hag_data,
        meta,
        MODEL_RESOLUTION_M,
    )
    canopy_masses, canopy_regions = extract_canopy_masses(
        tree_mask,
        hag_data,
        meta,
        MODEL_RESOLUTION_M,
        hag_grid=hag_grid,
    )
    undergrowth, undergrowth_regions = extract_undergrowth(
        rangeland_mask,
        image,
        hag_data,
        meta,
        MODEL_RESOLUTION_M,
    )
    pools = extract_pools(
        water_mask,
        image,
        hag_data,
        meta,
        MODEL_RESOLUTION_M,
    )

    payload = {
        "version": "coimbra-semantic-details-v1",
        "source": "DGT Orthophotos 2025 + DGT LiDAR HAG",
        "source_resolution_m": source_resolution,
        "model_resolution_m": MODEL_RESOLUTION_M,
        "semantic_model": {
            "project": "cliffbb/oem-lightweight",
            "model": "FasterSeg",
            "dataset": "OpenEarthMap",
            "classes_used": ["rangeland", "tree", "water"],
        },
        "counts": {
            "trees": len(trees),
            "crown_segments": int(crown_map.max()),
            "tree_heights_from_lidar": sum(
                item.get("height_source") == "crown-p90-lidar-hag"
                for item in trees
            ),
            "tree_heights_fallback": sum(
                item.get("height_source") == "crown-semantic-fallback"
                for item in trees
            ),
            "pools": len(pools),
            "canopy_mass_points": len(canopy_masses),
            "canopy_regions": len(canopy_regions),
            "undergrowth_points": len(undergrowth),
            "undergrowth_regions": len(undergrowth_regions),
            "rangeland_mask_pixels": int(rangeland_mask.sum()),
            "tree_mask_pixels": int(tree_mask.sum()),
            "water_mask_pixels": int(water_mask.sum()),
        },
        "trees": trees,
        "canopy_masses": canopy_masses,
        "canopy_regions": canopy_regions,
        "undergrowth": undergrowth,
        "undergrowth_regions": undergrowth_regions,
        "pools": pools,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    make_preview(
        image,
        tree_mask,
        water_mask,
        trees,
        pools,
        meta,
        hag_data,
        MODEL_RESOLUTION_M,
    )
    print(json.dumps(payload["counts"], indent=2))


if __name__ == "__main__":
    main()
