#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import time
import urllib.parse
import urllib.request

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pyproj import Transformer


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def square_crop(z: np.ndarray, xs: np.ndarray, ys: np.ndarray):
    if z.ndim != 2:
        raise ValueError("terrain z must be 2D")
    h, w = z.shape
    if len(xs) != w or len(ys) != h:
        raise ValueError("terrain axes do not match z shape")
    side = min(h, w)
    row0 = (h - side) // 2
    col0 = (w - side) // 2
    row1 = row0 + side
    col1 = col0 + side
    return (
        z[row0:row1, col0:col1],
        xs[col0:col1],
        ys[row0:row1],
        {"row0": row0, "row1": row1, "col0": col0, "col1": col1},
    )


def height_to_u8(z: np.ndarray, water_m: float, max_m: float) -> np.ndarray:
    if not max_m > water_m:
        raise ValueError("max_elevation_m must exceed water_elevation_m")
    scaled = np.clip((z.astype(np.float64) - water_m) / (max_m - water_m), 0.0, 1.0)
    out = np.rint(scaled * 255.0).astype(np.uint8)
    out[z <= water_m] = 0
    return out


def epsg_bounds(xs: np.ndarray, ys: np.ndarray) -> tuple[float, float, float, float]:
    return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())


def wgs84_bbox(bounds):
    xmin, ymin, xmax, ymax = bounds
    t = Transformer.from_crs("EPSG:3763", "EPSG:4326", always_xy=True)
    corners = [t.transform(xmin, ymin), t.transform(xmin, ymax),
               t.transform(xmax, ymin), t.transform(xmax, ymax)]
    lons = [p[0] for p in corners]
    lats = [p[1] for p in corners]
    return [min(lons), min(lats), max(lons), max(lats)]


def town_payload(towns: list[dict], bounds) -> tuple[list[dict], list[dict]]:
    xmin, ymin, xmax, ymax = bounds
    to3763 = Transformer.from_crs("EPSG:4326", "EPSG:3763", always_xy=True)
    accepted = []
    rejected = []
    for town in towns:
        easting, northing = to3763.transform(float(town["lon"]), float(town["lat"]))
        col = (easting - xmin) / (xmax - xmin)
        row = (ymax - northing) / (ymax - ymin)
        if not (0.0 <= col <= 1.0 and 0.0 <= row <= 1.0):
            rejected.append({**town, "reason": "outside square DGT crop"})
            continue
        # OpenTTD axes are swapped relative to ordinary image coordinates.
        accepted.append({
            "name": town["name"],
            "population": int(town["population"]),
            "city": bool(town.get("city", False)),
            "x": round(float(row), 12),
            "y": round(float(col), 12),
        })
    return accepted, rejected


def fetch_osm(bbox, endpoints: list[str]) -> dict:
    west, south, east, north = bbox
    query = f"""[out:json][timeout:60];
(
  way["highway"]({south},{west},{north},{east});
  way["railway"]({south},{west},{north},{east});
);
out tags geom;"""
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    errors = []
    for endpoint in endpoints:
        try:
            request = urllib.request.Request(
                endpoint,
                data=body,
                headers={"User-Agent": "coimbra-openttd/001"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=75) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            errors.append(f"{endpoint}: {exc}")
    raise RuntimeError("; ".join(errors))


def osm_geojson(payload: dict) -> dict:
    features = []
    for element in payload.get("elements", []):
        geom = element.get("geometry") or []
        coords = [[float(p["lon"]), float(p["lat"])] for p in geom]
        if len(coords) < 2:
            continue
        tags = element.get("tags") or {}
        props = {
            "osm_id": int(element["id"]),
            "highway": tags.get("highway"),
            "railway": tags.get("railway"),
            "name": tags.get("name"),
            "bridge": tags.get("bridge"),
            "tunnel": tags.get("tunnel"),
            "layer": tags.get("layer"),
        }
        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "LineString", "coordinates": coords},
        })
    return {"type": "FeatureCollection", "features": features}


def draw_preview(
    heightmap: Image.Image,
    towns: list[dict],
    network: dict | None,
    bounds,
    out: Path,
) -> None:
    base = heightmap.convert("RGB")
    draw = ImageDraw.Draw(base)
    w, h = base.size
    to3763 = Transformer.from_crs("EPSG:4326", "EPSG:3763", always_xy=True)
    xmin, ymin, xmax, ymax = bounds

    def px(lon, lat):
        e, n = to3763.transform(float(lon), float(lat))
        x = (e - xmin) / (xmax - xmin) * (w - 1)
        y = (ymax - n) / (ymax - ymin) * (h - 1)
        return x, y

    if network:
        for feature in network.get("features", []):
            props = feature.get("properties") or {}
            points = [px(lon, lat) for lon, lat in feature["geometry"]["coordinates"]]
            if len(points) < 2:
                continue
            width = 2 if props.get("railway") else 1
            draw.line(points, fill=(235, 235, 235), width=width)

    for town in towns:
        x, y = px(town["lon"], town["lat"])
        r = 4
        draw.ellipse((x-r, y-r, x+r, y+r), fill=(255, 255, 255), outline=(0, 0, 0))
        draw.text((x+6, y-7), town["name"], fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))

    draw.rectangle((0, h-24, w, h), fill=(0, 0, 0))
    draw.text((8, h-19), "Coimbra OpenTTD 001 · DGT terrain · OSM transport reference", fill=(255,255,255))
    base.save(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--fetch-osm", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    terrain_path = ROOT / config["terrain_npz"]
    terrain_meta_path = ROOT / config["terrain_meta"]
    terrain_meta = json.loads(terrain_meta_path.read_text(encoding="utf-8"))
    terrain = np.load(terrain_path)
    z = np.asarray(terrain["z"], dtype=np.float32)
    xs = np.asarray(terrain["xs"], dtype=np.float64)
    ys = np.asarray(terrain["ys"], dtype=np.float64)

    # The pinned Coimbra terrain stores local metre coordinates around its
    # EPSG:3763 centre. Recover absolute national-grid coordinates before
    # projecting towns/OSM into the raster.
    center = terrain_meta.get("center_epsg3763")
    if center and np.max(np.abs(xs)) < 10000 and np.max(np.abs(ys)) < 10000:
        xs = xs + float(center[0])
        ys = ys + float(center[1])

    z_crop, xs_crop, ys_crop, crop = square_crop(z, xs, ys)
    bounds = epsg_bounds(xs_crop, ys_crop)
    bbox = wgs84_bbox(bounds)

    height_cfg = config["heightmap"]
    gray = height_to_u8(
        z_crop,
        float(height_cfg["water_elevation_m"]),
        float(height_cfg["max_elevation_m"]),
    )
    size = int(height_cfg["size_px"])
    image = Image.fromarray(gray, mode="L").resize((size, size), Image.Resampling.BICUBIC)
    border = int(height_cfg.get("sea_border_px", 0))
    if border:
        arr = np.asarray(image).copy()
        arr[:border, :] = 0
        arr[-border:, :] = 0
        arr[:, :border] = 0
        arr[:, -border:] = 0
        image = Image.fromarray(arr, mode="L")

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    heightmap_path = out / "coimbra-heightmap.png"
    image.save(heightmap_path)

    towns, rejected = town_payload(config["towns"], bounds)
    towns_path = out / "coimbra-towns.json"
    towns_path.write_text(json.dumps(towns, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    network = None
    network_error = None
    network_path = out / "coimbra-osm-network.geojson"
    if args.fetch_osm:
        try:
            raw = fetch_osm(bbox, config["overpass_endpoints"])
            network = osm_geojson(raw)
            network_path.write_text(json.dumps(network, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception as exc:
            network_error = str(exc)
            (out / "osm-fetch-error.txt").write_text(network_error + "\n", encoding="utf-8")

    draw_preview(image, config["towns"], network, bounds, out / "coimbra-preview.png")

    transport_stats = {}
    if network:
        features = network["features"]
        transport_stats = {
            "features": len(features),
            "highways": sum(bool(f["properties"].get("highway")) for f in features),
            "railways": sum(bool(f["properties"].get("railway")) for f in features),
            "bridges": sum(bool(f["properties"].get("bridge")) for f in features),
            "tunnels": sum(bool(f["properties"].get("tunnel")) for f in features),
        }

    manifest = {
        "version": config["version"],
        "review_only": True,
        "openttd_import_ready": True,
        "scenario_file_generated": False,
        "source": {
            "terrain_npz": config["terrain_npz"],
            "terrain_npz_sha256": sha256(terrain_path),
            "terrain_meta": config["terrain_meta"],
            "terrain_meta_sha256": sha256(terrain_meta_path),
            "terrain_source": terrain_meta.get("source"),
        },
        "square_crop": crop,
        "crop_bbox_epsg3763": [round(v, 3) for v in bounds],
        "crop_bbox_wgs84": [round(v, 8) for v in bbox],
        "heightmap": {
            "size": [size, size],
            "water_elevation_m": height_cfg["water_elevation_m"],
            "max_elevation_m": height_cfg["max_elevation_m"],
            "sea_border_px": border,
            "sha256": sha256(heightmap_path),
        },
        "towns": {
            "accepted": len(towns),
            "rejected": rejected,
            "sha256": sha256(towns_path),
        },
        "osm": {
            "attribution": config["osm_attribution"],
            "fetched": network is not None,
            "error": network_error,
            "stats": transport_stats,
            "sha256": sha256(network_path) if network_path.exists() else None,
        },
        "note": "Use coimbra-heightmap.png in Scenario Editor, then Town Generation -> Load from file with coimbra-towns.json. OSM GeoJSON is reference data for the next road-import milestone.",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "README-import.txt").write_text(
        "Coimbra OpenTTD 001\n"
        "1. Open OpenTTD Scenario Editor.\n"
        "2. Generate/load map from coimbra-heightmap.png (clockwise orientation).\n"
        "3. Town Generation -> Load from file -> coimbra-towns.json.\n"
        "4. Save as a Scenario.\n"
        "Road/rail GeoJSON is reference evidence for the next milestone; it is not yet an automatic .scn road import.\n"
        + config["osm_attribution"] + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
