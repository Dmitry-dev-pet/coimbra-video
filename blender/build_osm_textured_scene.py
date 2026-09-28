from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "coimbra_bridge.json"
OSM = ROOT / "data" / "osm" / "coimbra-route.json"
ORTHO = ROOT / "data" / "processed" / "bridge_ortho_2025.jpg"
ORTHO_META = ROOT / "data" / "processed" / "bridge_ortho_2025.json"
OUT = ROOT / "bridge_output_002"
BASE_BLEND = OUT / "coimbra-textured-base.blend"
MANIFEST = OUT / "base-manifest.json"

EARTH_RADIUS_M_PER_DEG = 111_320.0

ROAD_STYLES = {
    "major": {
        "types": {"motorway", "trunk", "primary", "secondary"},
        "width": 2.5,
        "color": (0.055, 0.060, 0.067, 1.0),
        "roughness": 0.62,
    },
    "local": {
        "types": {"tertiary", "residential", "living_street", "unclassified"},
        "width": 1.25,
        "color": (0.085, 0.090, 0.095, 1.0),
        "roughness": 0.68,
    },
    "service": {
        "types": {"service"},
        "width": 0.70,
        "color": (0.12, 0.115, 0.11, 1.0),
        "roughness": 0.74,
    },
    "paths": {
        "types": {"footway", "path", "pedestrian", "cycleway", "steps", "track"},
        "width": 0.34,
        "color": (0.20, 0.19, 0.17, 1.0),
        "roughness": 0.82,
    },
}

WALL_COLORS = [
    (0.72, 0.66, 0.56, 1.0),
    (0.80, 0.76, 0.68, 1.0),
    (0.67, 0.62, 0.55, 1.0),
    (0.86, 0.83, 0.76, 1.0),
    (0.58, 0.55, 0.51, 1.0),
]
ROOF_COLORS = [
    (0.43, 0.16, 0.09, 1.0),
    (0.55, 0.21, 0.11, 1.0),
    (0.34, 0.16, 0.10, 1.0),
    (0.30, 0.30, 0.29, 1.0),
]


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def make_principled(
    name: str,
    color,
    roughness: float,
    metallic: float = 0.0,
):
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
    return material


def make_ortho_material():
    material = bpy.data.materials.new("City_Ground_DGT_Ortho")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    for node in list(nodes):
        nodes.remove(node)

    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    image_node = nodes.new("ShaderNodeTexImage")
    image = bpy.data.images.load(str(ORTHO), check_existing=False)
    image_node.image = image
    image.colorspace_settings.name = "sRGB"
    bsdf.inputs["Roughness"].default_value = 0.72
    bsdf.inputs["Specular IOR Level"].default_value = 0.22
    links.new(image_node.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return material, image


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


def stable_index(value, modulo: int) -> int:
    digest = hashlib.sha256(str(value).encode()).digest()
    return int.from_bytes(digest[:4], "big") % modulo


def build_ground(width_m: float, height_m: float, material):
    bpy.ops.mesh.primitive_plane_add(size=2.0, location=(0.0, 0.0, 0.0))
    ground = bpy.context.object
    ground.name = "City_Ground"
    ground.dimensions = (width_m, height_m, 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    ground.data.materials.append(material)
    ground["source"] = "DGT Orthophotos 2025"
    ground["texture_license"] = "CC BY 4.0"
    return ground


def build_buildings(ways, nodes, lon0, lat0, materials):
    vertices = []
    faces = []
    material_indices = []
    building_count = 0

    wall_slots = list(range(len(WALL_COLORS)))
    roof_slots = list(range(len(WALL_COLORS), len(WALL_COLORS) + len(ROOF_COLORS)))

    for way in ways:
        tags = way.get("tags", {})
        if "building" not in tags:
            continue

        coords = []
        for node_id in way.get("nodes", []):
            node = nodes.get(node_id)
            if node is None:
                coords = []
                break
            coords.append(local_xy(node["lon"], node["lat"], lon0, lat0))
        if len(coords) < 4 or coords[0] != coords[-1]:
            continue

        coords = coords[:-1]
        if len(coords) < 3:
            continue

        height = building_height(tags)
        base_index = len(vertices)
        n = len(coords)
        wall_slot = wall_slots[stable_index(way["id"], len(wall_slots))]
        roof_slot = roof_slots[stable_index(f"roof:{way['id']}", len(roof_slots))]

        for x, y in coords:
            vertices.append((x, y, 0.30))
        for x, y in coords:
            vertices.append((x, y, height))

        faces.append(tuple(base_index + n + i for i in range(n)))
        material_indices.append(roof_slot)
        faces.append(tuple(base_index + i for i in reversed(range(n))))
        material_indices.append(wall_slot)

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
            material_indices.append(wall_slot)

        building_count += 1

    mesh = bpy.data.meshes.new("City_Buildings_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()

    obj = bpy.data.objects.new("City_Buildings", mesh)
    bpy.context.collection.objects.link(obj)
    for material in materials:
        obj.data.materials.append(material)

    for polygon, material_index in zip(obj.data.polygons, material_indices):
        polygon.material_index = material_index

    obj["source"] = "OpenStreetMap"
    obj["building_count"] = building_count
    obj["material_model"] = "deterministic-walls-roofs-v1"
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
            coords.append((x, y, 0.42))
        if len(coords) >= 2:
            grouped[group].append(coords)

    counts = {}
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
        obj["road_material_model"] = "asphalt-class-v2"
        counts[group] = len(polylines)
    return counts


def point_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_camera_and_sun():
    camera_data = bpy.data.cameras.new("Camera")
    camera = bpy.data.objects.new("Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    camera.location = (-470.0, 670.0, 180.0)
    camera.data.lens = 52.0
    camera.data.sensor_width = 36.0
    point_at(camera, (-293.37, 851.60, 15.0))

    sun_data = bpy.data.lights.new(name="Sun", type="SUN")
    sun_data.energy = 2.0
    sun_data.angle = math.radians(5.0)
    sun = bpy.data.objects.new(name="Sun", object_data=sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(38), math.radians(-18), math.radians(-35))
    return camera


def main() -> None:
    for required in (OSM, ORTHO, ORTHO_META):
        if not required.exists():
            raise SystemExit(f"Missing required input: {required}")

    cfg = json.loads(CONFIG.read_text())
    data = json.loads(OSM.read_text())
    ortho_meta = json.loads(ORTHO_META.read_text())
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

    ground_mat, ortho_image = make_ortho_material()
    wall_materials = [
        make_principled(f"City_Wall_{i:02d}", color, 0.74)
        for i, color in enumerate(WALL_COLORS)
    ]
    roof_materials = [
        make_principled(f"City_Roof_{i:02d}", color, 0.82)
        for i, color in enumerate(ROOF_COLORS)
    ]
    road_materials = {
        group: make_principled(
            f"City_Roads_{group}_Mat",
            style["color"],
            style["roughness"],
        )
        for group, style in ROAD_STYLES.items()
    }

    build_ground(width_m, height_m, ground_mat)
    _, building_count, vertex_count, face_count = build_buildings(
        ways,
        nodes,
        lon0,
        lat0,
        [*wall_materials, *roof_materials],
    )
    road_counts = build_roads(ways, nodes, lon0, lat0, road_materials)
    add_camera_and_sun()

    scene = bpy.context.scene
    scene["city_source"] = "OpenStreetMap via Overpass API"
    scene["city_texture_source"] = "DGT Orthophotos 2025"
    scene["city_texture_license"] = "CC BY 4.0"
    scene["city_bbox"] = ",".join(str(v) for v in cfg["bbox_wgs84"])
    scene["city_geometry_version"] = "osm-extrusion-textured-v2"
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

    bpy.ops.file.pack_all()

    manifest = {
        "geometry_source": scene["city_source"],
        "texture_source": scene["city_texture_source"],
        "texture_license": scene["city_texture_license"],
        "texture": ortho_meta,
        "bbox_wgs84": cfg["bbox_wgs84"],
        "building_count": building_count,
        "building_vertices": vertex_count,
        "building_faces": face_count,
        "wall_materials": len(wall_materials),
        "roof_materials": len(roof_materials),
        "road_way_counts": road_counts,
        "protected_object_glob": "City_*",
        "packed_texture": ortho_image.packed_file is not None,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")

    bpy.ops.wm.save_as_mainfile(filepath=str(BASE_BLEND))
    print(json.dumps(manifest, indent=2))
    print(f"Wrote {BASE_BLEND}")


if __name__ == "__main__":
    main()
