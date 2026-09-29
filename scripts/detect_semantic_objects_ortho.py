from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ORTHO = ROOT / "data" / "processed" / "bridge_ortho_2025.jpg"
ORTHO_META = ROOT / "data" / "processed" / "bridge_ortho_2025.json"
OSM = ROOT / "data" / "processed" / "bridge_osm_oss_local.json"
BBOX = ROOT / "bridge_output_023" / "review-bbox.json"
OUT = ROOT / "data" / "processed" / "bridge_semantic_objects_2025.json"
QA_DIR = ROOT / "bridge_output_023"
QA_OVERLAY = QA_DIR / "solar-detections-qa.png"
QA_CONTACT_SHEET = QA_DIR / "solar-candidates-sheet.png"
QA_SUMMARY = QA_DIR / "solar-qa-summary.json"

SOLAR_DETECTOR = "OpenCV roof-component detector"
SOLAR_MIN_AREA_M2 = 0.8
SOLAR_MAX_AREA_M2 = 220.0


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


def building_pixel_polygon(building, meta):
    return np.asarray(
        [local_to_pixel(x, y, meta) for x, y in building["polygon"]],
        dtype=np.float32,
    )


def contour_axis(contour):
    points = contour.reshape(-1, 2).astype(np.float32)
    rect = cv2.minAreaRect(points)
    box = cv2.boxPoints(rect)
    edges = []
    for i in range(4):
        a = box[i]
        b = box[(i + 1) % 4]
        delta = b - a
        length = float(np.linalg.norm(delta))
        edges.append((length, delta))
    edges.sort(key=lambda item: item[0], reverse=True)
    long_px, delta = edges[0]
    short_px = min(item[0] for item in edges)
    world = np.asarray([float(delta[0]), float(-delta[1])], dtype=np.float32)
    norm = float(np.linalg.norm(world))
    if norm < 1e-8:
        axis = [1.0, 0.0]
    else:
        axis = [float(world[0] / norm), float(world[1] / norm)]
    return rect, axis, float(long_px), float(short_px)


def detect_solar_cv(image, meta, buildings):
    import cv2

    rgb_full = np.asarray(image, dtype=np.uint8)
    resolution = float(meta["resolution_m"])
    detections = []

    for building in buildings:
        poly = building_pixel_polygon(building, meta)
        if len(poly) < 3:
            continue
        minx = max(0, int(math.floor(float(poly[:, 0].min()))) - 2)
        miny = max(0, int(math.floor(float(poly[:, 1].min()))) - 2)
        maxx = min(image.width, int(math.ceil(float(poly[:, 0].max()))) + 3)
        maxy = min(image.height, int(math.ceil(float(poly[:, 1].max()))) + 3)
        if maxx - minx < 5 or maxy - miny < 5:
            continue

        crop = rgb_full[miny:maxy, minx:maxx]
        local_poly = np.rint(poly - np.asarray([minx, miny], dtype=np.float32)).astype(np.int32)
        roof_mask = np.zeros(crop.shape[:2], dtype=np.uint8)
        cv2.fillPoly(roof_mask, [local_poly], 255)

        hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
        h, s, v = cv2.split(hsv)

        # PV arrays in DGT RGB imagery are typically dark blue, blue-gray or
        # near-black rectangles. Keep both families, but only inside a known
        # OSM building footprint.
        blue = (
            (h >= 82) & (h <= 145)
            & (s >= 35)
            & (v >= 22) & (v <= 205)
        )
        dark = (v >= 18) & (v <= 92) & (s >= 10)
        mask = ((blue | dark).astype(np.uint8) * 255)
        mask = cv2.bitwise_and(mask, roof_mask)

        kernel = np.ones((3, 3), dtype=np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(
            mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        for contour in contours:
            area_px = float(cv2.contourArea(contour))
            area_m2 = area_px * resolution * resolution
            if not (SOLAR_MIN_AREA_M2 <= area_m2 <= SOLAR_MAX_AREA_M2):
                continue

            rect, axis, long_px, short_px = contour_axis(contour)
            if short_px < 2.0 or long_px < 3.0:
                continue
            rect_area = max(1.0, long_px * short_px)
            rectangularity = area_px / rect_area
            aspect = long_px / max(1e-6, short_px)
            if rectangularity < 0.48 or aspect > 14.0:
                continue

            cx_local_px, cy_local_px = map(float, rect[0])
            gx = minx + cx_local_px
            gy = miny + cy_local_px
            center = pixel_to_local(gx, gy, meta)

            component_mask = np.zeros(crop.shape[:2], dtype=np.uint8)
            cv2.drawContours(component_mask, [contour], -1, 255, thickness=-1)
            pixels = crop[component_mask.astype(bool)]
            if pixels.size == 0:
                continue
            mean_rgb = pixels.reshape(-1, 3).mean(axis=0)
            r, g, b = map(float, mean_rgb)
            luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b

            # Reject obvious roof shadows / red tile blobs. Black PV remains
            # possible; blue channel need not dominate if luminance is low.
            blue_support = b >= r * 0.92 and b >= g * 0.72
            dark_support = luminance <= 82.0 and abs(r - g) <= 38.0
            if not (blue_support or dark_support):
                continue

            # Huge components covering most of a roof are usually shadows or
            # dark membranes, not panel arrays.
            if area_m2 > float(building["area_m2"]) * 0.62:
                continue

            detections.append(
                {
                    "score": float(
                        min(
                            0.99,
                            0.45
                            + 0.30 * rectangularity
                            + 0.18 * min(1.0, area_m2 / 18.0),
                        )
                    ),
                    "label": "solar panel candidate",
                    "center_local": [float(center[0]), float(center[1])],
                    "width_m": float(long_px * resolution),
                    "height_m": float(short_px * resolution),
                    "area_m2": float(area_m2),
                    "mean_rgb": [round(r, 1), round(g, 1), round(b, 1)],
                    "building_way_id": building["way_id"],
                    "building_axis": axis,
                    "rectangularity": float(rectangularity),
                    "source": "OpenCV+DGT",
                }
            )

    detections.sort(key=lambda item: item["score"], reverse=True)

    kept = []
    for item in detections:
        cx, cy = item["center_local"]
        duplicate = False
        for old in kept:
            ox, oy = old["center_local"]
            distance = math.hypot(cx - ox, cy - oy)
            threshold = 0.4 * max(
                item["width_m"],
                item["height_m"],
                old["width_m"],
                old["height_m"],
            )
            if distance < max(1.0, threshold):
                duplicate = True
                break
        if not duplicate:
            kept.append(item)
    return kept



def detection_world_corners(item):
    cx, cy = map(float, item["center_local"])
    axis = np.asarray(item.get("building_axis") or [1.0, 0.0], dtype=np.float32)
    norm = float(np.linalg.norm(axis))
    if norm < 1e-8:
        axis = np.asarray([1.0, 0.0], dtype=np.float32)
    else:
        axis = axis / norm
    side = np.asarray([-axis[1], axis[0]], dtype=np.float32)
    half_w = float(item["width_m"]) * 0.5
    half_h = float(item["height_m"]) * 0.5
    center = np.asarray([cx, cy], dtype=np.float32)
    return np.asarray(
        [
            center - axis * half_w - side * half_h,
            center + axis * half_w - side * half_h,
            center + axis * half_w + side * half_h,
            center - axis * half_w + side * half_h,
        ],
        dtype=np.float32,
    )


def evenly_spaced_indices(count, limit=64):
    if count <= 0:
        return []
    if count <= limit:
        return list(range(count))
    return sorted(
        set(
            int(round(i * (count - 1) / (limit - 1)))
            for i in range(limit)
        )
    )


def qa_summary(detections, sampled_indices):
    scores = np.asarray([float(item["score"]) for item in detections], dtype=np.float64)
    areas = np.asarray([float(item["area_m2"]) for item in detections], dtype=np.float64)
    rectangularity = np.asarray(
        [float(item.get("rectangularity", 0.0)) for item in detections],
        dtype=np.float64,
    )

    def stats(values):
        if values.size == 0:
            return {"min": None, "p25": None, "median": None, "p75": None, "max": None}
        return {
            "min": float(values.min()),
            "p25": float(np.quantile(values, 0.25)),
            "median": float(np.quantile(values, 0.50)),
            "p75": float(np.quantile(values, 0.75)),
            "max": float(values.max()),
        }

    return {
        "version": "coimbra-solar-qa-v1",
        "detections": len(detections),
        "unique_buildings": len({int(item["building_way_id"]) for item in detections}),
        "score": stats(scores),
        "area_m2": stats(areas),
        "rectangularity": stats(rectangularity),
        "score_bands": {
            "gte_0_90": int(np.sum(scores >= 0.90)) if scores.size else 0,
            "0_80_to_0_90": int(np.sum((scores >= 0.80) & (scores < 0.90))) if scores.size else 0,
            "0_70_to_0_80": int(np.sum((scores >= 0.70) & (scores < 0.80))) if scores.size else 0,
            "lt_0_70": int(np.sum(scores < 0.70)) if scores.size else 0,
        },
        "sampled_indices": [int(index) for index in sampled_indices],
        "overlay": QA_OVERLAY.relative_to(ROOT).as_posix(),
        "contact_sheet": QA_CONTACT_SHEET.relative_to(ROOT).as_posix(),
    }


def render_solar_qa(image, meta, buildings, detections, crop_box):
    QA_DIR.mkdir(parents=True, exist_ok=True)
    rgb_full = np.asarray(image, dtype=np.uint8)
    x0, y0, x1, y1 = map(int, crop_box)
    overlay = rgb_full[y0:y1, x0:x1].copy()
    if overlay.size == 0:
        raise RuntimeError("solar QA crop is empty")

    max_side = max(overlay.shape[0], overlay.shape[1])
    scale = min(1.0, 4096.0 / max_side)
    if scale < 1.0:
        overlay = cv2.resize(
            overlay,
            (
                max(1, int(round(overlay.shape[1] * scale))),
                max(1, int(round(overlay.shape[0] * scale))),
            ),
            interpolation=cv2.INTER_AREA,
        )

    building_ids = {int(item["building_way_id"]) for item in detections}
    building_map = {int(item["way_id"]): item for item in buildings}
    for way_id in building_ids:
        item = building_map.get(way_id)
        if item is None:
            continue
        pts = np.asarray(
            [
                (
                    (local_to_pixel(px, py, meta)[0] - x0) * scale,
                    (local_to_pixel(px, py, meta)[1] - y0) * scale,
                )
                for px, py in item["polygon"]
            ],
            dtype=np.int32,
        )
        if len(pts) >= 3:
            cv2.polylines(overlay, [pts], True, (210, 210, 210), 1, cv2.LINE_AA)

    sampled_indices = evenly_spaced_indices(len(detections), limit=64)
    sampled_set = set(sampled_indices)
    for index, item in enumerate(detections):
        corners = detection_world_corners(item)
        pts = np.asarray(
            [
                (
                    (local_to_pixel(float(px), float(py), meta)[0] - x0) * scale,
                    (local_to_pixel(float(px), float(py), meta)[1] - y0) * scale,
                )
                for px, py in corners
            ],
            dtype=np.int32,
        )
        score = float(item["score"])
        if score >= 0.90:
            color = (255, 55, 55)
            thickness = 3
        elif score >= 0.80:
            color = (255, 165, 35)
            thickness = 2
        else:
            color = (255, 225, 40)
            thickness = 2
        cv2.polylines(overlay, [pts], True, color, thickness, cv2.LINE_AA)
        if index in sampled_set:
            center_px = local_to_pixel(*map(float, item["center_local"]), meta)
            label_xy = (
                int(round((center_px[0] - x0) * scale)),
                int(round((center_px[1] - y0) * scale)),
            )
            cv2.putText(
                overlay,
                str(index),
                label_xy,
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                overlay,
                str(index),
                label_xy,
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (20, 20, 20),
                1,
                cv2.LINE_AA,
            )

    cv2.imwrite(str(QA_OVERLAY), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))

    tile_size = 180
    columns = 8
    rows = max(1, math.ceil(max(1, len(sampled_indices)) / columns))
    sheet = np.full((rows * tile_size, columns * tile_size, 3), 235, dtype=np.uint8)
    resolution = float(meta["resolution_m"])

    for slot, index in enumerate(sampled_indices):
        item = detections[index]
        cx, cy = local_to_pixel(*map(float, item["center_local"]), meta)
        candidate_px = max(float(item["width_m"]), float(item["height_m"])) / resolution
        radius = int(round(max(28.0, min(120.0, candidate_px * 1.8 + 18.0))))
        sx0 = max(0, int(round(cx)) - radius)
        sy0 = max(0, int(round(cy)) - radius)
        sx1 = min(image.width, int(round(cx)) + radius)
        sy1 = min(image.height, int(round(cy)) + radius)
        tile = rgb_full[sy0:sy1, sx0:sx1].copy()
        if tile.size == 0:
            continue

        corners = detection_world_corners(item)
        pts = np.asarray(
            [
                (
                    local_to_pixel(float(px), float(py), meta)[0] - sx0,
                    local_to_pixel(float(px), float(py), meta)[1] - sy0,
                )
                for px, py in corners
            ],
            dtype=np.int32,
        )
        cv2.polylines(tile, [pts], True, (255, 45, 45), 2, cv2.LINE_AA)
        tile = cv2.resize(tile, (tile_size, tile_size), interpolation=cv2.INTER_AREA)
        cv2.rectangle(tile, (0, 0), (tile_size - 1, 26), (10, 10, 10), -1)
        label = f"#{index} s={float(item['score']):.2f} a={float(item['area_m2']):.1f}"
        cv2.putText(
            tile,
            label,
            (5, 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        row, col = divmod(slot, columns)
        sheet[
            row * tile_size : (row + 1) * tile_size,
            col * tile_size : (col + 1) * tile_size,
        ] = tile

    cv2.imwrite(str(QA_CONTACT_SHEET), cv2.cvtColor(sheet, cv2.COLOR_RGB2BGR))
    summary = qa_summary(detections, sampled_indices)
    QA_SUMMARY.write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.parse_args()

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

    solar = detect_solar_cv(image, meta, buildings)
    qa = render_solar_qa(image, meta, buildings, solar, crop_box)

    payload = {
        "version": "coimbra-semantic-objects-v1",
        "review_frame": int(review["frame"]),
        "review_bbox_local": review_bbox,
        "ortho_crop_px": list(map(int, crop_box)),
        "solar_detector": {
            "name": SOLAR_DETECTOR,
            "source": "DGT Orthophotos 2025",
            "constraint": "OSM building footprints",
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
        "qa": qa,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload["counts"], indent=2))


if __name__ == "__main__":
    main()
