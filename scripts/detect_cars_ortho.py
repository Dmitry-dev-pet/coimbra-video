from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
ORTHO = ROOT / "data" / "processed" / "bridge_ortho_2025.jpg"
ORTHO_META = ROOT / "data" / "processed" / "bridge_ortho_2025.json"
TERRAIN_META = ROOT / "data" / "processed" / "bridge_terrain_6m.json"
OUT = ROOT / "data" / "processed" / "bridge_cars_ortho_2025.json"
PREVIEW = ROOT / "data" / "processed" / "bridge_cars_ortho_2025_preview.jpg"

MODEL = "yolo26n-obb.pt"
ULTRALYTICS_VERSION = "8.4.161"
TILE = 1024
OVERLAP = 160
CONFIDENCE = 0.18
DEDUPE_DISTANCE_M = 1.5

PALETTE = [
    (168, 24, 19),   # red
    (24, 55, 150),   # blue
    (205, 205, 195), # white
    (70, 72, 74),    # grey
    (190, 115, 18),  # yellow
    (28, 105, 50),   # green
]


def nearest_palette(rgb: tuple[int, int, int]) -> int:
    r, g, b = rgb
    best = 0
    best_distance = float("inf")
    for index, candidate in enumerate(PALETTE):
        distance = sum((a - b_) ** 2 for a, b_ in zip((r, g, b), candidate))
        if distance < best_distance:
            best_distance = distance
            best = index
    return best


def sample_color(image: Image.Image, cx: float, cy: float) -> tuple[int, int, int]:
    x = int(round(cx))
    y = int(round(cy))
    x0 = max(0, x - 2)
    y0 = max(0, y - 2)
    x1 = min(image.width, x + 3)
    y1 = min(image.height, y + 3)
    crop = np.asarray(image.crop((x0, y0, x1, y1)), dtype=np.uint8).reshape(-1, 3)
    median = np.median(crop, axis=0)
    return tuple(int(v) for v in median)


def tile_origins(size: int, tile: int, overlap: int) -> list[int]:
    if size <= tile:
        return [0]
    step = tile - overlap
    origins = list(range(0, max(1, size - tile + 1), step))
    last = size - tile
    if origins[-1] != last:
        origins.append(last)
    return origins


def geometry_from_quad(points: np.ndarray, resolution: float):
    edge_candidates = []
    for i in range(4):
        p0 = points[i]
        p1 = points[(i + 1) % 4]
        vec_px = p1 - p0
        length_px = float(np.linalg.norm(vec_px))
        edge_candidates.append((length_px, vec_px))
    edge_candidates.sort(key=lambda item: item[0], reverse=True)
    long_px, long_vec = edge_candidates[0]
    short_px = min(item[0] for item in edge_candidates)
    long_m = long_px * resolution
    short_m = short_px * resolution
    world_vec = np.array([long_vec[0], -long_vec[1]], dtype=float)
    angle = math.atan2(float(world_vec[1]), float(world_vec[0]))
    return long_m, short_m, angle


def main() -> None:
    if not ORTHO.is_file() or not ORTHO_META.is_file() or not TERRAIN_META.is_file():
        raise SystemExit("Missing orthophoto or terrain metadata")

    ortho_meta = json.loads(ORTHO_META.read_text())
    terrain_meta = json.loads(TERRAIN_META.read_text())
    minx, miny, maxx, maxy = map(float, ortho_meta["bbox_epsg3763"])
    resolution = float(ortho_meta["resolution_m"])
    center_x, center_y = map(float, terrain_meta["center_epsg3763"])

    image = Image.open(ORTHO).convert("RGB")
    model = YOLO(MODEL)

    detections = []
    x_origins = tile_origins(image.width, TILE, OVERLAP)
    y_origins = tile_origins(image.height, TILE, OVERLAP)
    total_tiles = len(x_origins) * len(y_origins)
    tile_index = 0

    for y0 in y_origins:
        for x0 in x_origins:
            tile_index += 1
            tile = np.asarray(image.crop((x0, y0, x0 + TILE, y0 + TILE)))
            results = model.predict(
                source=tile,
                imgsz=TILE,
                conf=CONFIDENCE,
                iou=0.55,
                device="cpu",
                verbose=False,
            )
            result = results[0]
            if result.obb is None or len(result.obb) == 0:
                print(f"tile {tile_index}/{total_tiles}: 0 vehicle boxes")
                continue

            quads = result.obb.xyxyxyxy.cpu().numpy()
            scores = result.obb.conf.cpu().numpy()
            classes = result.obb.cls.cpu().numpy().astype(int)
            found = 0
            for quad, score, class_index in zip(quads, scores, classes):
                class_name = str(model.names.get(int(class_index), class_index))
                if class_name not in {"small vehicle", "large vehicle"}:
                    continue

                global_quad = quad.copy()
                global_quad[:, 0] += x0
                global_quad[:, 1] += y0
                center_px = global_quad.mean(axis=0)
                long_m, short_m, angle = geometry_from_quad(global_quad, resolution)

                if class_name == "small vehicle":
                    if not (2.3 <= long_m <= 7.0 and 1.0 <= short_m <= 3.2):
                        continue
                else:
                    if not (4.0 <= long_m <= 16.0 and 1.4 <= short_m <= 4.5):
                        continue

                cx_px, cy_px = map(float, center_px)
                x_abs = minx + cx_px * resolution
                y_abs = maxy - cy_px * resolution
                rgb = sample_color(image, cx_px, cy_px)

                detections.append(
                    {
                        "class": class_name,
                        "confidence": float(score),
                        "center_px": [cx_px, cy_px],
                        "center_local": [x_abs - center_x, y_abs - center_y],
                        "length_m": float(long_m),
                        "width_m": float(short_m),
                        "angle_rad": float(angle),
                        "rgb": list(rgb),
                        "palette_slot": nearest_palette(rgb),
                        "quad_px": global_quad.astype(float).tolist(),
                    }
                )
                found += 1
            print(f"tile {tile_index}/{total_tiles}: {found} vehicle boxes")

    # Overlapping image tiles produce duplicate boxes. Keep the highest-confidence
    # box when centers are within a car-scale radius.
    detections.sort(key=lambda item: item["confidence"], reverse=True)
    kept = []
    min_distance_sq = DEDUPE_DISTANCE_M ** 2
    for item in detections:
        x, y = item["center_local"]
        duplicate = False
        for old in kept:
            ox, oy = old["center_local"]
            if (x - ox) ** 2 + (y - oy) ** 2 < min_distance_sq:
                duplicate = True
                break
        if not duplicate:
            kept.append(item)

    kept.sort(key=lambda item: (item["center_local"][1], item["center_local"][0]))
    counts = {
        "small vehicle": sum(item["class"] == "small vehicle" for item in kept),
        "large vehicle": sum(item["class"] == "large vehicle" for item in kept),
    }

    payload = {
        "source": "DGT Orthophotos 2025",
        "source_resolution_m": resolution,
        "detector": MODEL,
        "detector_training": "DOTAv1 OBB",
        "ultralytics_version": ULTRALYTICS_VERSION,
        "confidence_threshold": CONFIDENCE,
        "dedupe_distance_m": DEDUPE_DISTANCE_M,
        "counts": counts,
        "total": len(kept),
        "detections": kept,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")

    # Downsampled visual QA image with oriented boxes.
    max_preview = 2000
    scale = min(1.0, max_preview / max(image.size))
    preview_size = (int(image.width * scale), int(image.height * scale))
    preview = image.resize(preview_size)
    draw = ImageDraw.Draw(preview)
    for item in kept:
        points = [
            (point[0] * scale, point[1] * scale)
            for point in item["quad_px"]
        ]
        points.append(points[0])
        color = (255, 80, 20) if item["class"] == "small vehicle" else (255, 210, 0)
        draw.line(points, fill=color, width=max(1, int(2 * scale + 1)))
    preview.save(PREVIEW, quality=88)

    print(json.dumps({"total": len(kept), "counts": counts, "preview": str(PREVIEW)}, indent=2))


if __name__ == "__main__":
    main()
