from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ORTHO = ROOT / "data" / "processed" / "bridge_ortho_2025.jpg"
ORTHO_META = ROOT / "data" / "processed" / "bridge_ortho_2025.json"
OSM = ROOT / "data" / "processed" / "bridge_osm_oss_local.json"
BBOX = ROOT / "bridge_output_023" / "review-bbox.json"
OUT = ROOT / "data" / "processed" / "bridge_semantic_objects_2025.json"

MODEL_ID = "IDEA-Research/grounding-dino-tiny"
MODEL_REVISION = "c7309d120267d81bf3ed68383062e12a9102602d"
TILE = 1024
OVERLAP = 192
BOX_THRESHOLD = 0.16
TEXT_THRESHOLD = 0.14
PROMPT = "solar panel. photovoltaic panel. solar array."


def tile_origins(size: int, tile: int, overlap: int) -> list[int]:
    if size <= tile:
        return [0]
    step = tile - overlap
    values = list(range(0, max(1, size - tile + 1), step))
    last = size - tile
    if values[-1] != last:
        values.append(last)
    return values


def line_for_way(way: dict, nodes: dict) -> list[tuple[float, float]]:
    result = []
    for node_id in way.get("nodes") or []:
        node = nodes.get(str(node_id))
        if node is None:
            continue
        xy = node.get("xy")
        if not xy or len(xy) < 2:
            continue
        result.append((float(xy[0]), float(xy[1])))
    if len(result) >= 2 and result[0] == result[-1]:
        result = result[:-1]
    return result


def polygon_area(points):
    if len(points) < 3:
        return 0.0
    return abs(
        sum(
            points[i][0] * points[(i + 1) % len(points)][1]
            - points[(i + 1) % len(points)][0] * points[i][1]
            for i in range(len(points))
        )
    ) * 0.5


def polygon_centroid(points):
    if not points:
        return (0.0, 0.0)
    signed = sum(
        points[i][0] * points[(i + 1) % len(points)][1]
        - points[(i + 1) % len(points)][0] * points[i][1]
        for i in range(len(points))
    )
    if abs(signed) < 1e-9:
        return (
            sum(p[0] for p in points) / len(points),
            sum(p[1] for p in points) / len(points),
        )
    factor = 1.0 / (3.0 * signed)
    cx = sum(
        (points[i][0] + points[(i + 1) % len(points)][0])
        * (
            points[i][0] * points[(i + 1) % len(points)][1]
            - points[(i + 1) % len(points)][0] * points[i][1]
        )
        for i in range(len(points))
    ) * factor
    cy = sum(
        (points[i][1] + points[(i + 1) % len(points)][1])
        * (
            points[i][0] * points[(i + 1) % len(points)][1]
            - points[(i + 1) % len(points)][0] * points[i][1]
        )
        for i in range(len(points))
    ) * factor
    return float(cx), float(cy)


def point_in_polygon(x: float, y: float, polygon) -> bool:
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)):
            x_cross = (xj - xi) * (y - yi) / max(1e-12, yj - yi) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def longest_axis(points):
    best = (1.0, 0.0, 0.0)
    for p0, p1 in zip(points, points[1:] + points[:1]):
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        length = math.hypot(dx, dy)
        if length > best[2]:
            best = (dx / length, dy / length, length)
    return [float(best[0]), float(best[1])]


def in_bbox(point, bbox, margin=0.0):
    x, y = point
    return (
        bbox[0] - margin <= x <= bbox[2] + margin
        and bbox[1] - margin <= y <= bbox[3] + margin
    )


def local_to_pixel(x, y, meta):
    minx, _miny, _maxx, maxy = map(float, meta["bbox_epsg3763"])
    center_x, center_y = map(float, meta["center_epsg3763"])
    res = float(meta["resolution_m"])
    x_abs = center_x + x
    y_abs = center_y + y
    return (
        (x_abs - minx) / res,
        (maxy - y_abs) / res,
    )


def pixel_to_local(px, py, meta):
    minx, _miny, _maxx, maxy = map(float, meta["bbox_epsg3763"])
    center_x, center_y = map(float, meta["center_epsg3763"])
    res = float(meta["resolution_m"])
    x_abs = minx + px * res
    y_abs = maxy - py * res
    return x_abs - center_x, y_abs - center_y


def bbox_to_pixels(bbox, meta, image_size):
    p0 = local_to_pixel(bbox[0], bbox[3], meta)
    p1 = local_to_pixel(bbox[2], bbox[1], meta)
    x0 = max(0, int(math.floor(min(p0[0], p1[0]))))
    y0 = max(0, int(math.floor(min(p0[1], p1[1]))))
    x1 = min(image_size[0], int(math.ceil(max(p0[0], p1[0]))))
    y1 = min(image_size[1], int(math.ceil(max(p0[1], p1[1]))))
    return x0, y0, x1, y1


def iou(a, b):
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[2], b[2])
    y1 = min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return inter / max(1e-9, area_a + area_b - inter)


def match_building(center, buildings):
    matches = [
        item for item in buildings
        if point_in_polygon(center[0], center[1], item["polygon"])
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: item["area_m2"])
    return matches[0]


def collect_osm_features(source, review_bbox):
    nodes = source["nodes"]
    buildings = []
    parking = []
    pitches = []
    osm_solar = []

    for way in source["ways"]:
        tags = way.get("tags") or {}
        polygon = line_for_way(way, nodes)
        if len(polygon) < 3:
            continue
        center = polygon_centroid(polygon)
        if not in_bbox(center, review_bbox, margin=30.0):
            continue

        area = polygon_area(polygon)
        if area < 2.0:
            continue

        record = {
            "way_id": int(way["id"]),
            "polygon": [[float(x), float(y)] for x, y in polygon],
            "center": [float(center[0]), float(center[1])],
            "area_m2": float(area),
            "axis": longest_axis(polygon),
            "tags": tags,
        }

        if "building" in tags:
            buildings.append(record)

        if str(tags.get("amenity") or "").lower() == "parking":
            parking.append(record)

        leisure = str(tags.get("leisure") or "").lower()
        if leisure in {"pitch", "track", "playground"}:
            record = dict(record)
            record["kind"] = leisure
            record["sport"] = str(tags.get("sport") or "")
            pitches.append(record)

        solar = (
            str(tags.get("generator:source") or "").lower() == "solar"
            or str(tags.get("plant:source") or "").lower() == "solar"
            or str(tags.get("power") or "").lower() in {"solar_panel", "photovoltaic"}
            or str(tags.get("man_made") or "").lower() == "solar_panel"
        )
        if solar:
            osm_solar.append(record)

    return buildings, parking, pitches, osm_solar


def detect_solar(image, crop_box, meta, buildings):
    import torch
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

    torch.set_num_threads(max(1, min(4, torch.get_num_threads())))
    processor = AutoProcessor.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
    )
    model = AutoModelForZeroShotObjectDetection.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
    )
    model.eval()

    x_crop, y_crop, x_end, y_end = crop_box
    crop = image.crop(crop_box).convert("RGB")
    x_origins = tile_origins(crop.width, TILE, OVERLAP)
    y_origins = tile_origins(crop.height, TILE, OVERLAP)
    raw = []

    tile_index = 0
    total = len(x_origins) * len(y_origins)
    for y0 in y_origins:
        for x0 in x_origins:
            tile_index += 1
            tile = crop.crop((x0, y0, min(x0 + TILE, crop.width), min(y0 + TILE, crop.height)))
            inputs = processor(images=tile, text=PROMPT, return_tensors="pt")
            with torch.no_grad():
                outputs = model(**inputs)
            result = processor.post_process_grounded_object_detection(
                outputs,
                inputs.input_ids,
                box_threshold=BOX_THRESHOLD,
                text_threshold=TEXT_THRESHOLD,
                target_sizes=[tile.size[::-1]],
            )[0]

            scores = result["scores"].detach().cpu().numpy()
            boxes = result["boxes"].detach().cpu().numpy()
            labels = result.get("text_labels", result.get("labels", []))

            found = 0
            for index, (score, box) in enumerate(zip(scores, boxes)):
                bx0, by0, bx1, by1 = map(float, box)
                gx0 = x_crop + x0 + bx0
                gy0 = y_crop + y0 + by0
                gx1 = x_crop + x0 + bx1
                gy1 = y_crop + y0 + by1

                width_m = (gx1 - gx0) * float(meta["resolution_m"])
                height_m = (gy1 - gy0) * float(meta["resolution_m"])
                area_m2 = width_m * height_m
                if not (0.7 <= min(width_m, height_m) <= 25.0):
                    continue
                if not (1.0 <= area_m2 <= 600.0):
                    continue

                cx_px = 0.5 * (gx0 + gx1)
                cy_px = 0.5 * (gy0 + gy1)
                center = pixel_to_local(cx_px, cy_px, meta)
                building = match_building(center, buildings)
                if building is None:
                    continue

                # Solar arrays on aerial RGB are usually dark blue/gray. Use
                # color only as a weak rejection filter, never as the detector.
                patch = np.asarray(
                    image.crop(
                        (
                            int(max(0, gx0)),
                            int(max(0, gy0)),
                            int(min(image.width, gx1)),
                            int(min(image.height, gy1)),
                        )
                    ).convert("RGB"),
                    dtype=np.float32,
                )
                if patch.size == 0:
                    continue
                mean_rgb = patch.reshape(-1, 3).mean(axis=0)
                luminance = float(
                    0.2126 * mean_rgb[0]
                    + 0.7152 * mean_rgb[1]
                    + 0.0722 * mean_rgb[2]
                )
                if luminance > 220.0 and float(score) < 0.28:
                    continue

                label = (
                    labels[index]
                    if hasattr(labels, "__len__") and len(labels) > index
                    else "solar panel"
                )
                raw.append(
                    {
                        "score": float(score),
                        "label": str(label),
                        "box_px": [gx0, gy0, gx1, gy1],
                        "center_local": [float(center[0]), float(center[1])],
                        "width_m": float(width_m),
                        "height_m": float(height_m),
                        "area_m2": float(area_m2),
                        "mean_rgb": [round(float(v), 1) for v in mean_rgb],
                        "building_way_id": building["way_id"],
                        "building_axis": building["axis"],
                    }
                )
                found += 1
            print(f"GroundingDINO tile {tile_index}/{total}: {found} accepted solar boxes")

    raw.sort(key=lambda item: item["score"], reverse=True)
    kept = []
    for item in raw:
        if any(iou(item["box_px"], old["box_px"]) > 0.38 for old in kept):
            continue
        kept.append(item)
    return kept


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-solar", action="store_true")
    args = parser.parse_args()

    for required in (ORTHO, ORTHO_META, OSM, BBOX):
        if not required.is_file():
            raise SystemExit(f"Missing input: {required}")

    image = Image.open(ORTHO).convert("RGB")
    meta = json.loads(ORTHO_META.read_text())
    source = json.loads(OSM.read_text())
    review = json.loads(BBOX.read_text())
    review_bbox = list(map(float, review["bbox_local"]))

    buildings, parking, pitches, osm_solar = collect_osm_features(
        source,
        review_bbox,
    )
    crop_box = bbox_to_pixels(review_bbox, meta, image.size)

    solar = []
    if not args.skip_solar:
        solar = detect_solar(image, crop_box, meta, buildings)

    payload = {
        "version": "coimbra-semantic-objects-v1",
        "review_frame": int(review["frame"]),
        "review_bbox_local": review_bbox,
        "ortho_crop_px": list(map(int, crop_box)),
        "solar_detector": {
            "model": MODEL_ID,
            "revision": MODEL_REVISION,
            "prompt": PROMPT,
            "box_threshold": BOX_THRESHOLD,
            "text_threshold": TEXT_THRESHOLD,
        },
        "counts": {
            "buildings_in_crop": len(buildings),
            "solar_detections": len(solar),
            "osm_solar": len(osm_solar),
            "parking": len(parking),
            "pitches": len(pitches),
        },
        "solar": solar,
        "osm_solar": osm_solar,
        "parking": parking,
        "pitches": pitches,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload["counts"], indent=2))


if __name__ == "__main__":
    main()
