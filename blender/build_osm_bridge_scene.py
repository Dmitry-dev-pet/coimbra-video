from __future__ import annotations

import json
import math
import re
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "coimbra_bridge.json"
OSM = ROOT / "data" / "osm" / "coimbra-route.json"
OUT = ROOT / "bridge_output"
BASE_BLEND = OUT / "coimbra-base.blend"
MANIFEST = OUT / "base-manifest.json"

EARTH_RADIUS_M_PER_DEG = 111_320.0

ROAD_STYLES = {
    "major": {
        "types": {"motorway", "trunk", "primary", "secondary"},
        "width": 2.2,
        "color": (0.14, 0.15, 0.17, 1.0),
    },
    "local": {
        "types": {"tertiary", "residential", "living_street", "unclassified"},
        "width": 1.15,
        "color": (0.19, 0.20, 0.22, 1.0),
    },
    "service": {
        "types": {"service"},
        "width": 0.65,
        "color": (0.23, 0.24, 0.25, 1.0),
    },
    "paths": {
        "types": {"footway", "path", "pedestrian", "cycleway", "steps", "track"},
        "width": 0.32,
        "color": (0.32, 0.31, 0.29, 1.0),
    },
}


def make_material(name: str, color, roughness: float = 0.5, emission: float = 0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = color
            bsdf.inputs["Emission Strength"].default_value = emission
    return mat


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def local_xy(lon: float, lat: float, lon0: float, lat0: float):
    x = (lon - lon0) * EARTH_RADIUS_M_PER_DEG * math.cos(math.radians(lat0))
    y = (lat - lat0) * EARTH_RADIUS_M_PER_DEG
    return x, y


def parse_number(value):
    if value is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def building_height(tags: dict) -> float:
    direct = parse_number(tags.get("height"))
    if direct is not None:
        return max(3.0, min(90.0, direct))

    levels = parse_number(tags.get("building:levels"))
    if levels is not None:
        return max(3.0, min(90.0, levels * 3.0))

    kind = tags.get("building", "")
    if kind in {"church", "cathedral", "chapel"}:
        return 18.0
    if kind in {"university", "school", "hospital", "public"}:
        return 14.0
    return 9.0


def build_buildings(ways, nodes, lon0, lat0, material):
    vertices = []
    faces = []
    building_count = 0

    for way in ways:
        tags = way.get("tags", {})
        if "building" not in tags:
            continue

        node_ids = way.get("nodes", [])
        coords = []
        for node_id in node_ids:
            node = nodes.get(node_id)
            if node is None:
                coords = []
                break
            coords.append(local_xy(node["lon"], node["lat"], lon0, lat0))

        if len(coords) < 4:
            continue
        if coords[0] != coords[-1]:
            continue
        coords = coords[:-1]
        if len(coords) < 3:
            continue

        height = building_height(tags)
        base_index = len(vertices)
        n = len(coords)

        for x, y in coords:
            vertices.append((x, y, 0.25))
        for x, y in coords:
            vertices.append((x, y, height))

        faces.append(tuple(base_index + n + i for i in range(n)))
        faces.append(tuple(base_index + i for i in reversed(range(n))))
        for i in range(n):
            j = (i + 1) % n
            faces.append(
                (
                    base_index + i,
                    base_index + j,
                    base_index + n + j,
                    base_index + n + i,
                )
            )
        building_count += 1

    mesh = bpy.data.meshes.new("City_Buildings_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()

    obj = bpy.data.objects.new("City_Buildings", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    obj["source"] = "OpenStreetMap"
    obj["building_count"] = building_count
    return obj, building_count, len(vertices), len(faces)


def road_group(highway: str):
    for name, style in ROAD_STYLES.items():
        if highway in style["types"]:
            return name
    return None


def build_roads(ways, nodes, lon0, lat0, materials):
    grouped = {name: [] for name in ROAD_STYLES}

    for way in ways:
        tags = way.get("tags", {})
        highway = tags.get("highway")
        if not highway:
            continue
        group = road_group(highway)
        if group is None:
            continue

        coords = []
        for node_id in way.get("nodes", []):
            node = nodes.get(node_id)
            if node is None:
                continue
            x, y = local_xy(node["lon"], node["lat"], lon0, lat0)
            coords.append((x, y, 0.35))
        if len(coords) >= 2:
            grouped[group].append(coords)

    result = {}
    for group, polylines in grouped.items():
        curve = bpy.data.curves.new(f"City_Roads_{group}_Curve", type="CURVE")
        curve.dimensions = "3D"
        curve.resolution_u = 1
        curve.bevel_depth = ROAD_STYLES[group]["width"]
        curve.bevel_resolution = 1

        for coords in polylines:
            spline = curve.splines.new("POLY")
            spline.points.add(len(coords) - 1)
            for point, coord in zip(spline.points, coords):
                point.co = (*coord, 1.0)

        obj = bpy.data.objects.new(f"City_Roads_{group}", curve)
        bpy.context.collection.objects.link(obj)
        obj.data.materials.append(materials[group])
        obj["source"] = "OpenStreetMap"
        obj["road_way_count"] = len(polylines)
        result[group] = len(polylines)

    return result


def add_ground(width_m: float, height_m: float, material):
    bpy.ops.mesh.primitive_cube_add(location=(0.0, 0.0, -1.0))
    ground = bpy.context.object
    ground.name = "City_Ground"
    ground.dimensions = (width_m + 80.0, height_m + 80.0, 2.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    ground.data.materials.append(material)
    ground["source"] = "OpenStreetMap-derived scene"
    return ground


def add_attribution(camera, material):
    data = bpy.data.curves.new("City_Attribution_Font", type="FONT")
    data.body = "© OpenStreetMap contributors · ODbL"
    data.align_x = "LEFT"
    data.align_y = "BOTTOM"
    data.size = 0.075
    data.extrude = 0.002
    data.materials.append(material)

    text = bpy.data.objects.new("City_Attribution", data)
    bpy.context.collection.objects.link(text)
    text.parent = camera
    text.location = (-1.35, -0.72, -3.0)
    text.rotation_euler = (0.0, 0.0, 0.0)
    text["source"] = "OpenStreetMap attribution"
    return text


def point_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def main() -> None:
    if not OSM.exists():
        raise SystemExit(f"Missing {OSM}; run scripts/fetch_osm_bridge.py")

    cfg = json.loads(CONFIG.read_text())
    data = json.loads(OSM.read_text())
    clear_scene()
    OUT.mkdir(parents=True, exist_ok=True)

    lon0, lat0 = cfg["center_wgs84"]
    west, south, east, north = cfg["bbox_wgs84"]
    width_m = (east - west) * EARTH_RADIUS_M_PER_DEG * math.cos(math.radians(lat0))
    height_m = (north - south) * EARTH_RADIUS_M_PER_DEG

    nodes = {
        element["id"]: element
        for element in data["elements"]
        if element.get("type") == "node"
    }
    ways = [
        element
        for element in data["elements"]
        if element.get("type") == "way"
    ]

    ground_mat = make_material("City_Ground_Mat", (0.08, 0.095, 0.10, 1.0), 0.75)
    building_mat = make_material("City_Building_Mat", (0.62, 0.57, 0.49, 1.0), 0.65)
    road_materials = {
        group: make_material(
            f"City_Roads_{group}_Mat",
            style["color"],
            0.72,
        )
        for group, style in ROAD_STYLES.items()
    }
    attribution_mat = make_material(
        "City_Attribution_Mat",
        (0.92, 0.94, 0.98, 1.0),
        0.4,
        emission=0.8,
    )

    add_ground(width_m, height_m, ground_mat)
    buildings, building_count, vertex_count, face_count = build_buildings(
        ways, nodes, lon0, lat0, building_mat
    )
    road_counts = build_roads(ways, nodes, lon0, lat0, road_materials)

    camera_data = bpy.data.cameras.new("Camera")
    camera = bpy.data.objects.new("Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    camera.location = (-470.0, 670.0, 180.0)
    camera.data.lens = 52.0
    camera.data.sensor_width = 36.0
    point_at(camera, (-293.37, 851.60, 15.0))

    add_attribution(camera, attribution_mat)

    sun_data = bpy.data.lights.new(name="Sun", type="SUN")
    sun_data.energy = 2.0
    sun_data.angle = math.radians(5.0)
    sun = bpy.data.objects.new(name="Sun", object_data=sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(38), math.radians(-18), math.radians(-35))

    scene = bpy.context.scene
    scene["city_source"] = "OpenStreetMap via Overpass API"
    scene["city_bbox"] = ",".join(str(v) for v in cfg["bbox_wgs84"])
    scene["city_geometry_version"] = "osm-extrusion-v1"
    scene.render.engine = "BLENDER_EEVEE"
    if scene.eevee is not None:
        scene.eevee.taa_render_samples = 1
    scene.render.resolution_x = 854
    scene.render.resolution_y = 480
    scene.render.resolution_percentage = 100
    scene.render.fps = 30
    scene.frame_start = 1
    scene.frame_end = 180

    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs["Color"].default_value = (0.08, 0.10, 0.13, 1.0)
        background.inputs["Strength"].default_value = 0.45

    manifest = {
        "source": scene["city_source"],
        "bbox_wgs84": cfg["bbox_wgs84"],
        "center_wgs84": cfg["center_wgs84"],
        "width_m": width_m,
        "height_m": height_m,
        "building_count": building_count,
        "building_vertices": vertex_count,
        "building_faces": face_count,
        "road_way_counts": road_counts,
        "protected_object_glob": "City_*",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")

    bpy.ops.wm.save_as_mainfile(filepath=str(BASE_BLEND))
    print(json.dumps(manifest, indent=2))
    print(f"Wrote {BASE_BLEND}")


if __name__ == "__main__":
    main()
