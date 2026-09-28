from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
ORTHO = ROOT / "data" / "processed" / "bridge_ortho_2025.jpg"
TERRAIN = ROOT / "data" / "processed" / "bridge_terrain_6m.npz"
TERRAIN_META = ROOT / "data" / "processed" / "bridge_terrain_6m.json"
OSM_LOCAL = ROOT / "data" / "processed" / "bridge_osm_local_epsg3763.json"

OUT = ROOT / "bridge_output_003"
BASE_BLEND = OUT / "coimbra-terrain-base.blend"
MANIFEST = OUT / "base-manifest.json"

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
ROAD_STYLES = {
    "major": ({"motorway", "trunk", "primary", "secondary"}, 2.5, (0.055, 0.060, 0.067, 1.0)),
    "local": ({"tertiary", "residential", "living_street", "unclassified"}, 1.25, (0.085, 0.090, 0.095, 1.0)),
    "service": ({"service"}, 0.70, (0.12, 0.115, 0.11, 1.0)),
    "paths": ({"footway", "path", "pedestrian", "cycleway", "steps", "track"}, 0.34, (0.20, 0.19, 0.17, 1.0)),
}


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def material(name, color, roughness):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
    return mat


def ortho_material():
    mat = bpy.data.materials.new("City_Terrain_DGT_Ortho")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    for node in list(nodes):
        nodes.remove(node)
    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    image_node = nodes.new("ShaderNodeTexImage")
    image = bpy.data.images.load(str(ORTHO), check_existing=False)
    image_node.image = image
    bsdf.inputs["Roughness"].default_value = 0.74
    links.new(image_node.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return mat, image


def parse_number(value):
    if value is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if not match:
        return None
    return float(match.group())


def building_height(tags):
    value = parse_number(tags.get("height"))
    if value is not None:
        return max(3.0, min(90.0, value))
    levels = parse_number(tags.get("building:levels"))
    if levels is not None:
        return max(3.0, min(90.0, levels * 3.0))
    if tags.get("building") in {"church", "cathedral", "chapel"}:
        return 18.0
    return 9.0


def stable_index(value, modulo):
    digest = hashlib.sha256(str(value).encode()).digest()
    return int.from_bytes(digest[:4], "big") % modulo


def terrain_sampler(xs, ys, z, z0):
    x0, x1 = float(xs[0]), float(xs[-1])
    y0, y1 = float(ys[0]), float(ys[-1])
    width = z.shape[1]
    height = z.shape[0]

    def sample(x, y):
        c = int(round((float(x) - x0) / (x1 - x0) * (width - 1)))
        r = int(round((y0 - float(y)) / (y0 - y1) * (height - 1)))
        c = max(0, min(width - 1, c))
        r = max(0, min(height - 1, r))
        return float(z[r, c] - z0)

    return sample


def build_terrain(xs, ys, z, z0, mat):
    rows, cols = z.shape
    vertices = []
    faces = []
    for r in range(rows):
        for c in range(cols):
            vertices.append((float(xs[c]), float(ys[r]), float(z[r, c] - z0)))
    for r in range(rows - 1):
        for c in range(cols - 1):
            a = r * cols + c
            b = a + 1
            d = (r + 1) * cols + c
            e = d + 1
            faces.append((a, d, e, b))

    mesh = bpy.data.meshes.new("City_Terrain_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    uv = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        for loop_index in poly.loop_indices:
            vertex_index = mesh.loops[loop_index].vertex_index
            r = vertex_index // cols
            c = vertex_index % cols
            u = c / (cols - 1)
            v = 1.0 - r / (rows - 1)
            uv.data[loop_index].uv = (u, v)

    obj = bpy.data.objects.new("City_Terrain", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    obj["source"] = "DGT MDT-2m"
    obj["terrain_resolution_m"] = float(abs(xs[1] - xs[0])) if len(xs) > 1 else 0.0
    return obj


def build_buildings(ways, nodes, sample_height, materials):
    vertices = []
    faces = []
    indices = []
    count = 0
    wall_count = len(WALL_COLORS)

    for way in ways:
        tags = way.get("tags", {})
        if "building" not in tags:
            continue
        coords = [nodes.get(str(node_id)) for node_id in way.get("nodes", [])]
        if any(coord is None for coord in coords) or len(coords) < 4:
            continue
        if coords[0] != coords[-1]:
            continue
        coords = coords[:-1]
        if len(coords) < 3:
            continue

        cx = sum(coord[0] for coord in coords) / len(coords)
        cy = sum(coord[1] for coord in coords) / len(coords)
        base_z = sample_height(cx, cy) + 0.35
        height = building_height(tags)

        base = len(vertices)
        n = len(coords)
        wall_slot = stable_index(way["id"], wall_count)
        roof_slot = wall_count + stable_index(f"roof:{way['id']}", len(ROOF_COLORS))

        for x, y in coords:
            vertices.append((x, y, base_z))
        for x, y in coords:
            vertices.append((x, y, base_z + height))

        faces.append(tuple(base + n + i for i in range(n)))
        indices.append(roof_slot)
        faces.append(tuple(base + i for i in reversed(range(n))))
        indices.append(wall_slot)
        for i in range(n):
            j = (i + 1) % n
            faces.append((base + i, base + j, base + n + j, base + n + i))
            indices.append(wall_slot)
        count += 1

    mesh = bpy.data.meshes.new("City_Buildings_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("City_Buildings", mesh)
    bpy.context.collection.objects.link(obj)
    for mat in materials:
        obj.data.materials.append(mat)
    for polygon, index in zip(obj.data.polygons, indices):
        polygon.material_index = index
    obj["source"] = "OpenStreetMap draped on DGT MDT-2m"
    obj["building_count"] = count
    return count, len(vertices), len(faces)


def road_group(highway):
    for group, (types, _, _) in ROAD_STYLES.items():
        if highway in types:
            return group
    return None


def build_roads(ways, nodes, sample_height, materials):
    grouped = {group: [] for group in ROAD_STYLES}
    for way in ways:
        highway = way.get("tags", {}).get("highway")
        group = road_group(highway) if highway else None
        if group is None:
            continue
        coords = []
        for node_id in way.get("nodes", []):
            coord = nodes.get(str(node_id))
            if coord is None:
                continue
            x, y = coord
            coords.append((x, y, sample_height(x, y) + 0.45))
        if len(coords) >= 2:
            grouped[group].append(coords)

    counts = {}
    for group, polylines in grouped.items():
        _, width, _ = ROAD_STYLES[group]
        curve = bpy.data.curves.new(f"City_Roads_{group}_Curve", type="CURVE")
        curve.dimensions = "3D"
        curve.resolution_u = 1
        curve.bevel_depth = width
        curve.bevel_resolution = 1
        for coords in polylines:
            spline = curve.splines.new("POLY")
            spline.points.add(len(coords) - 1)
            for point, coord in zip(spline.points, coords):
                point.co = (*coord, 1.0)
        obj = bpy.data.objects.new(f"City_Roads_{group}", curve)
        bpy.context.collection.objects.link(obj)
        obj.data.materials.append(materials[group])
        obj["source"] = "OpenStreetMap draped on DGT MDT-2m"
        obj["road_way_count"] = len(polylines)
        counts[group] = len(polylines)
    return counts


def point_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_camera_and_sun():
    camera_data = bpy.data.cameras.new("Camera")
    camera = bpy.data.objects.new("Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    camera.location = (-470.0, 670.0, 330.0)
    camera.data.lens = 52.0
    camera.data.sensor_width = 36.0
    point_at(camera, (-293.37, 851.60, 75.0))

    sun_data = bpy.data.lights.new(name="Sun", type="SUN")
    sun_data.energy = 2.1
    sun_data.angle = math.radians(5.0)
    sun = bpy.data.objects.new(name="Sun", object_data=sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(38), math.radians(-18), math.radians(-35))


def main():
    for required in (ORTHO, TERRAIN, TERRAIN_META, OSM_LOCAL):
        if not required.exists():
            raise SystemExit(f"Missing input: {required}")

    terrain = np.load(TERRAIN)
    z = terrain["z"]
    xs = terrain["xs"]
    ys = terrain["ys"]
    z0 = float(terrain["z0"])
    meta = json.loads(TERRAIN_META.read_text())
    osm = json.loads(OSM_LOCAL.read_text())
    nodes = osm["nodes"]
    ways = osm["ways"]

    clear_scene()
    OUT.mkdir(parents=True, exist_ok=True)

    ground_mat, image = ortho_material()
    wall_materials = [material(f"City_Wall_{i:02d}", color, 0.74) for i, color in enumerate(WALL_COLORS)]
    roof_materials = [material(f"City_Roof_{i:02d}", color, 0.82) for i, color in enumerate(ROOF_COLORS)]
    road_materials = {
        group: material(f"City_Roads_{group}_Mat", spec[2], 0.72)
        for group, spec in ROAD_STYLES.items()
    }

    build_terrain(xs, ys, z, z0, ground_mat)
    sample_height = terrain_sampler(xs, ys, z, z0)
    building_count, vertex_count, face_count = build_buildings(
        ways, nodes, sample_height, [*wall_materials, *roof_materials]
    )
    road_counts = build_roads(ways, nodes, sample_height, road_materials)
    add_camera_and_sun()

    scene = bpy.context.scene
    scene["city_source"] = "OpenStreetMap + DGT MDT-2m"
    scene["city_texture_source"] = "DGT Orthophotos 2025"
    scene["city_texture_license"] = "CC BY 4.0"
    scene["city_terrain_source"] = "DGT MDT-2m"
    scene["city_bbox"] = ",".join(str(v) for v in meta["bbox_epsg3763"])
    scene["city_geometry_version"] = "osm-dgt-mdt-terrain-v3"
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
    if background:
        background.inputs["Color"].default_value = (0.07, 0.09, 0.12, 1.0)
        background.inputs["Strength"].default_value = 0.42

    bpy.ops.file.pack_all()

    manifest = {
        "terrain": meta,
        "building_count": building_count,
        "building_vertices": vertex_count,
        "building_faces": face_count,
        "road_way_counts": road_counts,
        "terrain_shape": list(z.shape),
        "terrain_vertices": int(z.shape[0] * z.shape[1]),
        "terrain_faces": int((z.shape[0] - 1) * (z.shape[1] - 1)),
        "packed_texture": image.packed_file is not None,
        "protected_object_glob": "City_*",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    bpy.ops.wm.save_as_mainfile(filepath=str(BASE_BLEND))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
