from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.geometry import tessellate_polygon


ROOT = Path(__file__).resolve().parents[1]
BLENDER_DIR = ROOT / "blender"
if str(BLENDER_DIR) not in sys.path:
    sys.path.insert(0, str(BLENDER_DIR))

import build_semantic_details as details  # type: ignore
import enhance_hero_buildings as hero  # type: ignore


SOURCE = ROOT / "bridge_output_019" / "coimbra-full-route-pitched-roofs.blend"
SEMANTIC = ROOT / "data" / "processed" / "bridge_semantic_details_2025.json"
OBJECTS = ROOT / "data" / "processed" / "bridge_semantic_objects_2025.json"
TERRAIN = ROOT / "bridge_output_008b" / "bridge_terrain_highres_2m.npz"
OUT = ROOT / "bridge_output_023"
IMAGE = OUT / "semantic-objects.png"
INTERNAL = OUT / "semantic-objects-internal.json"


def make_material(name, color, roughness=0.6, metallic=0.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = color
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
    return mat


def oriented_box(vertices, faces, indices, center, axis_x, axis_y, sx, sy, sz, material_index):
    hero.add_oriented_box(
        vertices,
        faces,
        indices,
        center=Vector(center),
        axis_x=Vector(axis_x),
        axis_y=Vector(axis_y),
        sx=float(sx),
        sy=float(sy),
        sz=float(sz),
        material_index=material_index,
    )


def remove_old_solar():
    removed = []
    for obj in list(bpy.data.objects):
        if obj.name == "Detail_Solar" or obj.name.startswith("Semantic_Solar"):
            removed.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
    return removed


def raycast_height(scene, x, y):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    origin = Vector((float(x), float(y), 1000.0))
    direction = Vector((0.0, 0.0, -1.0))
    hit, location, normal, _index, obj, _matrix = scene.ray_cast(
        depsgraph,
        origin,
        direction,
        distance=2000.0,
    )
    if not hit:
        return None, None, None
    return (
        float(location.z),
        obj.name if obj is not None else None,
        float(normal.z),
    )


def build_solar(scene, detections, osm_solar):
    mats = [
        make_material("Semantic_Solar_Blue", (0.012, 0.050, 0.14, 1.0), 0.18, 0.18),
        make_material("Semantic_Solar_Frame", (0.38, 0.40, 0.42, 1.0), 0.28, 0.62),
    ]
    vertices, faces, indices = [], [], []
    accepted = []
    rejected = {
        "no_hit": 0,
        "non_building_hit": 0,
        "non_roof_normal": 0,
    }

    candidates = list(detections)
    # OSM solar is authoritative when present; add a conservative array at the
    # polygon centroid if the orthophoto detector has not already matched nearby.
    for item in osm_solar:
        cx, cy = map(float, item["center"])
        if any(
            math.hypot(cx - float(old["center_local"][0]), cy - float(old["center_local"][1])) < 5.0
            for old in candidates
        ):
            continue
        area = max(2.0, min(120.0, float(item["area_m2"])))
        side = math.sqrt(area)
        candidates.append(
            {
                "score": 1.0,
                "label": "OSM solar",
                "center_local": [cx, cy],
                "width_m": max(1.5, side),
                "height_m": max(1.0, side * 0.55),
                "area_m2": area,
                "building_axis": item.get("axis") or [1.0, 0.0],
                "building_way_id": item.get("way_id"),
                "source": "OSM",
            }
        )

    for item in candidates:
        cx, cy = map(float, item["center_local"])
        z, hit_name, normal_z = raycast_height(scene, cx, cy)
        if z is None:
            rejected["no_hit"] += 1
            continue

        # Orthophoto candidates are allowed onto the scene only when the
        # downward ray actually lands on the governed building mesh. This
        # prevents stale OSM/OEM detections from becoming panels on trees,
        # roads, facade helpers or semantic ground objects.
        if item.get("source") != "OSM":
            if hit_name != "City_Buildings":
                rejected["non_building_hit"] += 1
                continue
            if normal_z is None or normal_z < 0.35:
                rejected["non_roof_normal"] += 1
                continue

        axis = Vector(item.get("building_axis") or [1.0, 0.0])
        axis = Vector((axis.x, axis.y, 0.0))
        if axis.length < 1e-8:
            axis = Vector((1.0, 0.0, 0.0))
        axis.normalize()
        side = Vector((-axis.y, axis.x, 0.0))

        major = max(float(item["width_m"]), float(item["height_m"]))
        minor = min(float(item["width_m"]), float(item["height_m"]))
        major = max(1.2, min(12.0, major))
        minor = max(0.85, min(7.0, minor))

        center = Vector((cx, cy, z + 0.11))
        oriented_box(
            vertices, faces, indices,
            center, axis, side,
            major, minor, 0.10, 0,
        )

        # Grid separators turn a detector box into a readable PV array.
        cols = max(1, int(major / 1.25))
        rows = max(1, int(minor / 1.85))
        for col in range(1, cols):
            offset = -major * 0.5 + major * col / cols
            p = center + axis * offset + Vector((0.0, 0.0, 0.065))
            oriented_box(
                vertices, faces, indices,
                p, side, axis,
                minor, 0.035, 0.035, 1,
            )
        for row in range(1, rows):
            offset = -minor * 0.5 + minor * row / rows
            p = center + side * offset + Vector((0.0, 0.0, 0.065))
            oriented_box(
                vertices, faces, indices,
                p, axis, side,
                major, 0.035, 0.035, 1,
            )

        accepted.append(
            {
                "center": [cx, cy, z + 0.12],
                "score": float(item.get("score", 1.0)),
                "source": item.get("source", "OpenCV+DGT+OpenEarthMap"),
                "hit": hit_name,
                "hit_normal_z": normal_z,
            }
        )

    mesh = bpy.data.meshes.new("Semantic_Solar_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Semantic_Solar", mesh)
    bpy.context.collection.objects.link(obj)
    for mat in mats:
        mesh.materials.append(mat)
    for polygon, slot in zip(mesh.polygons, indices):
        polygon.material_index = slot
    obj["source"] = "OpenCV + OpenEarthMap + OSM + DGT Orthophotos 2025"
    obj["array_count"] = len(accepted)
    obj["rejected_non_building_hit"] = rejected["non_building_hit"]
    return obj, accepted, rejected


def polygon_surface(vertices, faces, indices, polygon, terrain, material_index, z_offset=0.035):
    signed = hero.polygon_signed_area(polygon)
    ordered = polygon if signed > 0 else list(reversed(polygon))
    loop = []
    for x, y in ordered:
        z = terrain.sample(float(x), float(y))
        if z is None:
            return False
        loop.append(Vector((float(x), float(y), z + z_offset)))

    triangles = tessellate_polygon([loop])
    for triangle in triangles:
        resolved = [
            loop[value] if isinstance(value, int) else value
            for value in triangle
        ]
        if len(resolved) != 3:
            continue
        start = len(vertices)
        vertices.extend(tuple(point) for point in resolved)
        faces.append((start, start + 1, start + 2))
        indices.append(material_index)
    return True


def add_edge_lines(vertices, faces, indices, polygon, terrain, material_index, width=0.10, z_offset=0.075):
    for p0, p1 in zip(polygon, polygon[1:] + polygon[:1]):
        a = Vector((float(p0[0]), float(p0[1]), 0.0))
        b = Vector((float(p1[0]), float(p1[1]), 0.0))
        delta = b - a
        length = delta.length
        if length < 0.8:
            continue
        axis = delta.normalized()
        side = Vector((-axis.y, axis.x, 0.0))
        mid = (a + b) * 0.5
        z = terrain.sample(float(mid.x), float(mid.y))
        if z is None:
            continue
        oriented_box(
            vertices, faces, indices,
            (mid.x, mid.y, z + z_offset),
            axis, side,
            length, width, 0.035, material_index,
        )


def sport_material(kind, sport):
    text = (sport or "").lower()
    if "tennis" in text:
        return (0.24, 0.33, 0.18, 1.0)
    if "basketball" in text or "multi" in text:
        return (0.36, 0.14, 0.09, 1.0)
    if kind == "track":
        return (0.42, 0.17, 0.09, 1.0)
    if kind == "playground":
        return (0.28, 0.34, 0.38, 1.0)
    return (0.12, 0.30, 0.09, 1.0)


def build_ground_objects(parking, pitches, terrain):
    materials = [
        make_material("Semantic_Parking_Asphalt", (0.16, 0.17, 0.17, 1.0), 0.88),
        make_material("Semantic_Ground_Line", (0.80, 0.80, 0.72, 1.0), 0.74),
        make_material("Semantic_Pitch_Green", (0.12, 0.30, 0.09, 1.0), 0.94),
        make_material("Semantic_Pitch_Red", (0.42, 0.17, 0.09, 1.0), 0.93),
        make_material("Semantic_Pitch_Hard", (0.30, 0.25, 0.20, 1.0), 0.91),
    ]
    vertices, faces, indices = [], [], []
    accepted_parking, accepted_pitches = [], []

    for item in parking:
        polygon = [(float(x), float(y)) for x, y in item["polygon"]]
        if polygon_surface(vertices, faces, indices, polygon, terrain, 0, 0.025):
            add_edge_lines(vertices, faces, indices, polygon, terrain, 1, width=0.08)
            cx, cy = map(float, item["center"])
            z = terrain.sample(cx, cy)
            if z is not None:
                accepted_parking.append(
                    {"center": [cx, cy, z + 0.05], "area_m2": float(item["area_m2"])}
                )

    for item in pitches:
        polygon = [(float(x), float(y)) for x, y in item["polygon"]]
        kind = str(item.get("kind") or "pitch")
        sport = str(item.get("sport") or "")
        color = sport_material(kind, sport)
        # Reuse one of three broad material families.
        if color[1] > color[0]:
            slot = 2
        elif color[0] > 0.38 and color[1] < 0.22:
            slot = 3
        else:
            slot = 4

        if polygon_surface(vertices, faces, indices, polygon, terrain, slot, 0.035):
            add_edge_lines(vertices, faces, indices, polygon, terrain, 1, width=0.12)
            cx, cy = map(float, item["center"])
            z = terrain.sample(cx, cy)
            if z is not None:
                accepted_pitches.append(
                    {
                        "center": [cx, cy, z + 0.07],
                        "area_m2": float(item["area_m2"]),
                        "kind": kind,
                        "sport": sport,
                    }
                )

    mesh = bpy.data.meshes.new("Semantic_GroundObjects_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Semantic_GroundObjects", mesh)
    bpy.context.collection.objects.link(obj)
    for mat in materials:
        mesh.materials.append(mat)
    for polygon, slot in zip(mesh.polygons, indices):
        polygon.material_index = slot
    obj["parking_count"] = len(accepted_parking)
    obj["pitch_count"] = len(accepted_pitches)
    return obj, accepted_parking, accepted_pitches


def point_in_any(x, y, records):
    for item in records:
        polygon = [(float(px), float(py)) for px, py in item["polygon"]]
        if hero.point_in_polygon(float(x), float(y), polygon):
            return True
    return False


def visible(scene, camera, point):
    co = world_to_camera_view(scene, camera, Vector(point))
    return co.z > 0.0 and -0.05 <= co.x <= 1.05 and -0.05 <= co.y <= 1.05


def choose_frame(scene, camera, solar, parking, pitches, undergrowth):
    original = scene.frame_current
    under_sample = undergrowth[:: max(1, len(undergrowth) // 700)]
    best = None

    for frame in range(1, 361, 2):
        scene.frame_set(frame)
        solar_count = sum(visible(scene, camera, item["center"]) for item in solar)
        parking_count = sum(visible(scene, camera, item["center"]) for item in parking)
        pitch_count = sum(visible(scene, camera, item["center"]) for item in pitches)
        under_count = sum(
            visible(
                scene,
                camera,
                (item["x"], item["y"], item["z"] + item["height"] * 0.45),
            )
            for item in under_sample
        )
        score = solar_count * 12.0 + pitch_count * 8.0 + parking_count * 4.0 + under_count * 0.04
        row = (score, solar_count, pitch_count, parking_count, under_count, frame)
        if best is None or row > best:
            best = row

    scene.frame_set(original)
    assert best is not None
    return {
        "frame": int(best[5]),
        "solar_visible": int(best[1]),
        "pitches_visible": int(best[2]),
        "parking_visible": int(best[3]),
        "sampled_undergrowth_visible": int(best[4]),
        "score": float(best[0]),
    }


def main():
    for required in (SOURCE, SEMANTIC, OBJECTS, TERRAIN):
        if not required.is_file():
            raise SystemExit(f"Missing input: {required}")

    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    scene = bpy.context.scene
    camera = scene.camera
    if camera is None:
        raise RuntimeError("production camera missing")

    terrain = hero.TerrainSampler(TERRAIN)
    semantic = json.loads(SEMANTIC.read_text())
    objects = json.loads(OBJECTS.read_text())

    removed_solar = remove_old_solar()

    hardscape = list(objects.get("parking") or []) + list(objects.get("pitches") or [])
    filtered_trees = [
        item for item in (semantic.get("trees") or [])
        if not point_in_any(item["x"], item["y"], hardscape)
    ]
    filtered_masses = [
        item for item in (semantic.get("canopy_masses") or [])
        if not point_in_any(item["x"], item["y"], hardscape)
    ]
    filtered_under = [
        item for item in (semantic.get("undergrowth") or [])
        if not point_in_any(item["x"], item["y"], hardscape)
    ]

    ground_obj, parking, pitches = build_ground_objects(
        objects.get("parking") or [],
        objects.get("pitches") or [],
        terrain,
    )
    solar_obj, solar, solar_rejections = build_solar(
        scene,
        objects.get("solar") or [],
        objects.get("osm_solar") or [],
    )

    details.remove_old_tree_layer()
    tree_obj, trees = details.build_semantic_trees(filtered_trees, terrain)
    mass_obj, masses = details.build_canopy_masses(filtered_masses, terrain)
    under_obj, undergrowth = details.build_undergrowth(filtered_under, terrain)
    pool_obj, pools = details.build_pools(semantic.get("pools") or [], terrain)

    review = choose_frame(scene, camera, solar, parking, pitches, undergrowth)
    scene.frame_set(review["frame"])
    scene.camera = camera
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.filepath = str(IMAGE)
    bpy.ops.render.render(write_still=True)

    internal = {
        "version": "coimbra-semantic-objects-render-v1",
        "image": IMAGE.relative_to(ROOT).as_posix(),
        "removed_old_solar_objects": removed_solar,
        "placed_trees": len(trees),
        "placed_canopy_mass_points": len(masses),
        "placed_undergrowth_points": len(undergrowth),
        "placed_pools": len(pools),
        "solar_arrays": len(solar),
        "solar_rejections": solar_rejections,
        "parking_areas": len(parking),
        "sports_areas": len(pitches),
        "review": review,
        "mesh_faces": {
            "trees": len(tree_obj.data.polygons),
            "canopy": len(mass_obj.data.polygons),
            "undergrowth": len(under_obj.data.polygons),
            "pools": len(pool_obj.data.polygons),
            "ground_objects": len(ground_obj.data.polygons),
            "solar": len(solar_obj.data.polygons),
        },
    }
    INTERNAL.write_text(json.dumps(internal, indent=2) + "\n")
    print(json.dumps(internal, indent=2))


if __name__ == "__main__":
    main()
