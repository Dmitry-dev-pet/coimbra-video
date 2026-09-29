from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from pyproj import Transformer


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "bridge_output_003" / "coimbra-terrain-base.blend"
TERRAIN = ROOT / "data" / "processed" / "bridge_terrain_6m.npz"
TERRAIN_META = ROOT / "data" / "processed" / "bridge_terrain_6m.json"
CONFIG = ROOT / "config" / "coimbra_bridge.json"
OSM = ROOT / "data" / "osm" / "coimbra-route-mosaiq.osm.pbf"
MOSAIQ_DIR = Path(
    os.environ.get("MOSAIQ_ADDON_DIR", ROOT / "_mosaiq" / "mosaiq_osm_vr")
).resolve()
OUT_DIR = ROOT / "bridge_output_007"
OUT_BLEND = OUT_DIR / "coimbra-mosaiq-ab.blend"
CURRENT_PREVIEW = OUT_DIR / "current-preview.png"
MOSAIQ_PREVIEW = OUT_DIR / "mosaiq-preview.png"
MANIFEST = OUT_DIR / "mosaiq-manifest.json"

WEB_MERCATOR_R = 6378137.0


def inverse_web_mercator(x: float, y: float) -> tuple[float, float]:
    lon = math.degrees(x / WEB_MERCATOR_R)
    lat = math.degrees(math.atan(math.sinh(y / WEB_MERCATOR_R)))
    return lon, lat


def web_mercator(lon: float, lat: float) -> tuple[float, float]:
    lat = max(min(lat, 85.05112878), -85.05112878)
    x = math.radians(lon) * WEB_MERCATOR_R
    y = math.log(
        math.tan(math.pi / 4.0 + math.radians(lat) / 2.0)
    ) * WEB_MERCATOR_R
    return x, y


def terrain_sampler():
    terrain = np.load(TERRAIN)
    z = terrain["z"]
    xs = terrain["xs"]
    ys = terrain["ys"]
    z0 = float(terrain["z0"])
    x0, x1 = float(xs[0]), float(xs[-1])
    y0, y1 = float(ys[0]), float(ys[-1])
    width = z.shape[1]
    height = z.shape[0]

    def sample(x: float, y: float) -> float:
        c = int(round((x - x0) / (x1 - x0) * (width - 1)))
        r = int(round((y0 - y) / (y0 - y1) * (height - 1)))
        c = max(0, min(width - 1, c))
        r = max(0, min(height - 1, r))
        return float(z[r, c] - z0)

    return sample


def remove_current_osm_geometry() -> list[str]:
    removed = []
    for obj in list(bpy.data.objects):
        if obj.name == "City_Terrain":
            continue
        if obj.name == "City_Buildings" or obj.name.startswith("City_Roads_"):
            removed.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
    return removed


def categorize(original_name: str, obj_type: str) -> str:
    name = original_name.lower()
    if name.startswith("area_"):
        return "areas"
    if name.startswith("sidewalk_"):
        return "sidewalks"
    if name.startswith("crosswalk_"):
        return "crosswalks"
    if name.startswith("parking_"):
        return "parking_lanes"
    if name.startswith("road_marking_"):
        return "road_markings"
    if name.startswith("road_"):
        return "roads"
    if name.startswith("way_") or name.startswith("rel_"):
        return "buildings"
    if name.startswith("tree_row_"):
        return "tree_rows"
    if obj_type == "EMPTY":
        return "poi_instances"
    return "other"


def main() -> None:
    for required in (BASE, TERRAIN, TERRAIN_META, CONFIG, OSM):
        if not required.is_file():
            raise SystemExit(f"Missing input: {required}")
    if not (MOSAIQ_DIR / "__init__.py").is_file():
        raise SystemExit(f"MOSAIQ add-on not found: {MOSAIQ_DIR}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(BASE))

    scene = bpy.context.scene
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(CURRENT_PREVIEW)
    scene.frame_set(1)
    bpy.ops.render.render(write_still=True)

    removed = remove_current_osm_geometry()

    cfg = json.loads(CONFIG.read_text())
    meta = json.loads(TERRAIN_META.read_text())
    west, south, east, north = map(float, cfg["bbox_wgs84"])
    cx, cy = map(float, meta["center_epsg3763"])

    addon_parent = str(MOSAIQ_DIR.parent)
    if addon_parent not in sys.path:
        sys.path.insert(0, addon_parent)

    import mosaiq_osm_vr

    mosaiq_osm_vr.register()
    props = bpy.context.scene.osm_bbox_props
    props.minlon = west
    props.minlat = south
    props.maxlon = east
    props.maxlat = north
    props.origin_shift = True
    props.import_roads = True
    props.import_pois = True

    before_collections = set(bpy.data.collections.keys())
    result = bpy.ops.osm_bbox.import_pbf("EXEC_DEFAULT", filepath=str(OSM))
    if "FINISHED" not in result:
        raise RuntimeError(f"MOSAIQ import failed: {result}")

    new_collections = [
        collection
        for collection in bpy.data.collections
        if collection.name not in before_collections
        and collection.name.startswith("OSM_PBF_")
    ]
    if len(new_collections) != 1:
        raise RuntimeError(
            f"Expected one MOSAIQ collection, got {[c.name for c in new_collections]}"
        )
    collection = new_collections[0]

    for obj in list(collection.objects):
        if obj.name == "ground_aoi":
            bpy.data.objects.remove(obj, do_unlink=True)

    merc_x0, merc_y0 = web_mercator(west, south)
    to_3763 = Transformer.from_crs("EPSG:4326", "EPSG:3763", always_xy=True)
    sample_height = terrain_sampler()

    def project_xy(local_x: float, local_y: float) -> tuple[float, float]:
        lon, lat = inverse_web_mercator(
            float(local_x) + merc_x0,
            float(local_y) + merc_y0,
        )
        x_abs, y_abs = to_3763.transform(lon, lat)
        return float(x_abs - cx), float(y_abs - cy)

    stats = {
        "buildings": 0,
        "roads": 0,
        "areas": 0,
        "sidewalks": 0,
        "crosswalks": 0,
        "parking_lanes": 0,
        "road_markings": 0,
        "tree_rows": 0,
        "poi_instances": 0,
        "other": 0,
    }
    mesh_vertices = 0
    mesh_faces = 0
    generated = []

    for obj in list(collection.objects):
        original_name = obj.name
        category = categorize(original_name, obj.type)
        stats[category] += 1

        if obj.type == "MESH":
            matrix = obj.matrix_world.copy()
            inverse = matrix.inverted()
            world_points = [matrix @ vertex.co for vertex in obj.data.vertices]
            projected = [project_xy(point.x, point.y) for point in world_points]

            if category == "buildings" and projected:
                center_x = sum(point[0] for point in projected) / len(projected)
                center_y = sum(point[1] for point in projected) / len(projected)
                ground = sample_height(center_x, center_y)
                new_world = [
                    Vector((xy[0], xy[1], old.z + ground))
                    for xy, old in zip(projected, world_points)
                ]
            else:
                new_world = [
                    Vector((xy[0], xy[1], old.z + sample_height(xy[0], xy[1])))
                    for xy, old in zip(projected, world_points)
                ]

            for vertex, target in zip(obj.data.vertices, new_world):
                vertex.co = inverse @ target
            obj.data.update()
            mesh_vertices += len(obj.data.vertices)
            mesh_faces += len(obj.data.polygons)

        elif obj.type == "EMPTY":
            world = obj.matrix_world.translation.copy()
            x, y = project_xy(world.x, world.y)
            target = Vector((x, y, world.z + sample_height(x, y)))
            if obj.parent is None:
                obj.location = target
            else:
                obj.matrix_world.translation = target

        obj["source"] = "MOSAIQ OSM VR"
        obj["mosaiq_original_name"] = original_name
        obj.name = f"MOSAIQ_{original_name}"
        generated.append(obj.name)

    scene = bpy.context.scene
    scene["city_geometry_candidate"] = "MOSAIQ OSM VR"
    scene["city_geometry_candidate_commit"] = os.environ.get(
        "MOSAIQ_COMMIT", "unknown"
    )
    scene["city_geometry_candidate_bbox_wgs84"] = ",".join(
        str(v) for v in cfg["bbox_wgs84"]
    )
    scene["city_geometry_candidate_projection"] = (
        "MOSAIQ Web Mercator -> EPSG:3763 local -> DGT MDT-2m"
    )

    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(MOSAIQ_PREVIEW)
    scene.frame_set(1)
    bpy.ops.render.render(write_still=True)

    asset_files = []
    assets_dir = MOSAIQ_DIR / "assets"
    if assets_dir.is_dir():
        asset_files = sorted(
            p.name
            for p in assets_dir.iterdir()
            if p.is_file() and p.suffix.lower() == ".glb"
        )

    manifest = {
        "experiment": "COIMBRA-MOSAIQ-AB-007",
        "bbox_wgs84": cfg["bbox_wgs84"],
        "terrain_source": meta["source"],
        "terrain_center_epsg3763": meta["center_epsg3763"],
        "mosaiq_commit": os.environ.get("MOSAIQ_COMMIT", "unknown"),
        "removed_current_geometry": removed,
        "generated_collection": collection.name,
        "generated_object_count": len(generated),
        "category_counts": stats,
        "mesh_vertices": mesh_vertices,
        "mesh_faces": mesh_faces,
        "public_mosaiq_glb_assets": asset_files,
        "note": (
            "Public MOSAIQ ships POI/vehicle instancing logic but no GLB asset pack; "
            "empty assets means POI and parked-car instances cannot appear."
        ),
        "current_preview": str(CURRENT_PREVIEW.relative_to(ROOT)),
        "mosaiq_preview": str(MOSAIQ_PREVIEW.relative_to(ROOT)),
        "blend": str(OUT_BLEND.relative_to(ROOT)),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
