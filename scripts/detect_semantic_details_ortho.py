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
from skimage import measure, morphology


ROOT = Path(__file__).resolve().parents[1]
ORTHO = ROOT / "data" / "processed" / "bridge_ortho_2025.jpg"
ORTHO_META = ROOT / "data" / "processed" / "bridge_ortho_2025.json"
HAG = ROOT / "bridge_output_008b" / "bridge_height_above_ground_1m.npz"
OUT = ROOT / "data" / "processed" / "bridge_semantic_details_2025.json"
PREVIEW = ROOT / "data" / "processed" / "bridge_semantic_details_2025_preview.jpg"

MODEL_RESOLUTION_M = 0.50
TILE = 1024
OVERLAP = 128
TREE_CLASS = 4
WATER_CLASS = 5
MIN_TREE_HAG_M = 1.8
TREE_DEDUPE_M = 2.0
MAX_TREES = 12000
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
) -> tuple[np.ndarray, np.ndarray]:
    rgb = np.asarray(image, dtype=np.uint8)
    height, width = rgb.shape[:2]
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
            tree_votes[sl] += (pred == TREE_CLASS).astype(np.uint8)
            water_votes[sl] += (pred == WATER_CLASS).astype(np.uint8)
            print(
                f"OEM tile {index}/{total}: "
                f"tree={int(np.sum(pred == TREE_CLASS))} "
                f"water={int(np.sum(pred == WATER_CLASS))}"
            )

    threshold = np.maximum(1, np.ceil(coverage * 0.5)).astype(np.uint8)
    tree = tree_votes >= threshold
    water = water_votes >= threshold

    tree = morphology.remove_small_objects(tree, min_size=20)
    tree = morphology.remove_small_holes(tree, area_threshold=32)
    water = morphology.remove_small_objects(water, min_size=12)
    water = morphology.remove_small_holes(water, area_threshold=20)
    return tree, water


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


def extract_trees(
    tree_mask: np.ndarray,
    hag_data,
    ortho_meta: dict,
    resolution: float,
):
    height = hag_data["height"].astype(np.float32)
    xs = hag_data["xs"].astype(np.float32)
    ys = hag_data["ys"].astype(np.float32)
    center_x = float(hag_data["center_x"])
    center_y = float(hag_data["center_y"])
    minx, _miny, _maxx, maxy = map(float, ortho_meta["bbox_epsg3763"])

    candidate = np.zeros_like(height, dtype=bool)
    radius_map = np.zeros_like(height, dtype=np.float32)

    distance = ndi.distance_transform_edt(tree_mask) * resolution
    for row, y in enumerate(ys):
        py = (maxy - (center_y + float(y))) / resolution
        iy = int(round(py))
        if iy < 0 or iy >= tree_mask.shape[0]:
            continue
        for col, x in enumerate(xs):
            hag = float(height[row, col])
            if hag < MIN_TREE_HAG_M:
                continue
            px = ((center_x + float(x)) - minx) / resolution
            ix = int(round(px))
            if ix < 0 or ix >= tree_mask.shape[1]:
                continue
            if tree_mask[iy, ix]:
                candidate[row, col] = True
                radius_map[row, col] = float(distance[iy, ix])

    local_max = height >= (ndi.maximum_filter(height, size=3, mode="nearest") - 1e-5)
    coords = np.argwhere(candidate & local_max)
    items = []
    for row, col in coords:
        items.append(
            {
                "x": float(xs[col]),
                "y": float(ys[row]),
                "height": float(height[row, col]),
                "radius": float(max(1.1, min(5.8, radius_map[row, col] * 0.88))),
            }
        )

    items.sort(key=lambda item: item["height"], reverse=True)
    kept = []
    min_d2 = TREE_DEDUPE_M * TREE_DEDUPE_M
    cell = TREE_DEDUPE_M
    occupied: dict[tuple[int, int], list[dict]] = {}

    for item in items:
        gx = int(math.floor(item["x"] / cell))
        gy = int(math.floor(item["y"] / cell))
        duplicate = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for old in occupied.get((gx + dx, gy + dy), []):
                    if (
                        (item["x"] - old["x"]) ** 2
                        + (item["y"] - old["y"]) ** 2
                        < min_d2
                    ):
                        duplicate = True
                        break
                if duplicate:
                    break
            if duplicate:
                break
        if duplicate:
            continue
        kept.append(item)
        occupied.setdefault((gx, gy), []).append(item)
        if len(kept) >= MAX_TREES:
            break

    return sorted(kept, key=lambda item: (item["y"], item["x"]))


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
    tree_mask, water_mask = semantic_masks(
        image,
        torch,
        config,
        model,
        device,
    )

    hag_data = np.load(HAG)
    trees = extract_trees(
        tree_mask,
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
            "classes_used": ["tree", "water"],
        },
        "counts": {
            "trees": len(trees),
            "pools": len(pools),
            "tree_mask_pixels": int(tree_mask.sum()),
            "water_mask_pixels": int(water_mask.sum()),
        },
        "trees": trees,
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
