from __future__ import annotations

import json
import math
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "bridge_output_010" / "coimbra-urban-quality.blend"
OSM_LOCAL = ROOT / "data" / "processed" / "bridge_osm_oss_local.json"
TERRAIN = ROOT / "bridge_output_008b" / "bridge_terrain_highres_2m.npz"
OUT = ROOT / "bridge_output_011"
OUT_BLEND = OUT / "coimbra-polo2-photo-patch.blend"
HERO = OUT / "polo2-hero.png"
TOP = OUT / "polo2-patch-overview.png"
MANIFEST = OUT / "photo-patch-manifest.json"

PATCH_CENTER = (-168.37, -748.07)
PATCH_HALF = 110.0
PATCH_MARGIN = 8.0


class TerrainSampler:
    def __init__(self, path: Path):
        data = np.load(path)
        self.z = data["z"].astype(np.float32)
        self.xs = data["xs"].astype(np.float32)
        self.ys = data["ys"].astype(np.float32)
        self.z0 = float(data["z0"])

    def sample(self, x: float, y: float) -> float | None:
        min_x, max_x = sorted((float(self.xs[0]), float(self.xs[-1])))
        min_y, max_y = sorted((float(self.ys[0]), float(self.ys[-1])))
        if not (min_x <= x <= max_x and min_y <= y <= max_y):
            return None

        fx = (x - float(self.xs[0])) / (
            float(self.xs[-1]) - float(self.xs[0])
        ) * (len(self.xs) - 1)
        fy = (float(self.ys[0]) - y) / (
            float(self.ys[0]) - float(self.ys[-1])
        ) * (len(self.ys) - 1)

        x0 = max(0, min(int(np.floor(fx)), len(self.xs) - 1))
        y0 = max(0, min(int(np.floor(fy)), len(self.ys) - 1))
        x1 = min(x0 + 1, len(self.xs) - 1)
        y1 = min(y0 + 1, len(self.ys) - 1)
        tx = fx - x0
        ty = fy - y0

        a = float(self.z[y0, x0])
        b = float(self.z[y0, x1])
        c = float(self.z[y1, x0])
        d = float(self.z[y1, x1])
        return (
            (a * (1.0 - tx) + b * tx) * (1.0 - ty)
            + (c * (1.0 - tx) + d * tx) * ty
            - self.z0
        )


def point_at(obj, target):
    obj.rotation_euler = (
        Vector(target) - obj.location
    ).to_track_quat("-Z", "Y").to_euler()


def inside_xy(x: float, y: float, margin: float = 0.0) -> bool:
    cx, cy = PATCH_CENTER
    h = PATCH_HALF + margin
    return cx - h <= x <= cx + h and cy - h <= y <= cy + h


def object_bbox_xy(obj):
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return (
        min(p.x for p in points),
        max(p.x for p in points),
        min(p.y for p in points),
        max(p.y for p in points),
    )


def bbox_intersects_patch(obj, margin: float = 0.0) -> bool:
    minx, maxx, miny, maxy = object_bbox_xy(obj)
    cx, cy = PATCH_CENTER
    h = PATCH_HALF + margin
    return not (
        maxx < cx - h
        or minx > cx + h
        or maxy < cy - h
        or miny > cy + h
    )


def crop_mesh_object(obj) -> dict:
    before_vertices = len(obj.data.vertices)
    before_faces = len(obj.data.polygons)

    if before_faces == 0:
        keep = any(
            inside_xy(
                float((obj.matrix_world @ vertex.co).x),
                float((obj.matrix_world @ vertex.co).y),
                PATCH_MARGIN,
            )
            for vertex in obj.data.vertices
        )
        if not keep:
            bpy.data.objects.remove(obj, do_unlink=True)
            return {
                "removed": True,
                "before_vertices": before_vertices,
                "before_faces": before_faces,
                "after_vertices": 0,
                "after_faces": 0,
            }
        return {
            "removed": False,
            "before_vertices": before_vertices,
            "before_faces": before_faces,
            "after_vertices": before_vertices,
            "after_faces": before_faces,
        }

    if not bbox_intersects_patch(obj, PATCH_MARGIN):
        bpy.data.objects.remove(obj, do_unlink=True)
        return {
            "removed": True,
            "before_vertices": before_vertices,
            "before_faces": before_faces,
            "after_vertices": 0,
            "after_faces": 0,
        }

    matrix = obj.matrix_world.copy()
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()

    delete_faces = []
    for face in bm.faces:
        world_center = matrix @ face.calc_center_median()
        if not inside_xy(float(world_center.x), float(world_center.y), PATCH_MARGIN):
            delete_faces.append(face)

    if delete_faces:
        bmesh.ops.delete(bm, geom=delete_faces, context="FACES")
    loose_edges = [edge for edge in bm.edges if not edge.link_faces]
    if loose_edges:
        bmesh.ops.delete(bm, geom=loose_edges, context="EDGES")
    loose_verts = [vertex for vertex in bm.verts if not vertex.link_faces]
    if loose_verts:
        bmesh.ops.delete(bm, geom=loose_verts, context="VERTS")

    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()

    after_vertices = len(obj.data.vertices)
    after_faces = len(obj.data.polygons)
    if after_faces == 0:
        bpy.data.objects.remove(obj, do_unlink=True)
        return {
            "removed": True,
            "before_vertices": before_vertices,
            "before_faces": before_faces,
            "after_vertices": 0,
            "after_faces": 0,
        }

    return {
        "removed": False,
        "before_vertices": before_vertices,
        "before_faces": before_faces,
        "after_vertices": after_vertices,
        "after_faces": after_faces,
    }


def crop_scene() -> dict:
    keep_nonmesh = {
        "World",
    }
    stats = {}
    for obj in list(bpy.context.scene.objects):
        if obj.type == "MESH":
            name = obj.name
            stats[name] = crop_mesh_object(obj)
        elif obj.type in {"CAMERA", "LIGHT", "EMPTY", "CURVE", "FONT"}:
            # The patch gets its own camera and lighting. Remove old camera/light
            # objects and any non-mesh decoration that cannot be spatially cropped
            # reliably.
            if obj.name not in keep_nonmesh:
                bpy.data.objects.remove(obj, do_unlink=True)

    return stats


def add_building_bevel():
    obj = bpy.data.objects.get("City_Buildings")
    if obj is None or obj.type != "MESH":
        return None
    modifier = obj.modifiers.get("PhotoPatch_Bevel") or obj.modifiers.new(
        "PhotoPatch_Bevel", "BEVEL"
    )
    modifier.width = 0.07
    modifier.segments = 2
    modifier.limit_method = "ANGLE"
    modifier.angle_limit = math.radians(28.0)
    return {
        "object": obj.name,
        "width": modifier.width,
        "segments": modifier.segments,
    }


def line_for_way(way, nodes):
    line = []
    for node_id in way.get("nodes") or []:
        node = nodes.get(str(node_id))
        if node:
            x, y = node["xy"]
            line.append((float(x), float(y)))
    return line


def nearest_road_pose(nodes, ways):
    ax, ay = PATCH_CENTER
    wanted = {"primary", "secondary", "tertiary", "residential"}
    best = None

    for way in ways:
        tags = way.get("tags") or {}
        highway = str(tags.get("highway") or "").lower()
        if highway not in wanted:
            continue
        line = line_for_way(way, nodes)
        for p0, p1 in zip(line[:-1], line[1:]):
            x0, y0 = p0
            x1, y1 = p1
            dx = x1 - x0
            dy = y1 - y0
            length2 = dx * dx + dy * dy
            if length2 < 1e-6:
                continue
            t = ((ax - x0) * dx + (ay - y0) * dy) / length2
            t = max(0.0, min(1.0, t))
            px = x0 + dx * t
            py = y0 + dy * t
            distance2 = (px - ax) ** 2 + (py - ay) ** 2
            if best is None or distance2 < best["distance2"]:
                tangent = Vector((dx, dy))
                tangent.normalize()
                best = {
                    "xy": (px, py),
                    "tangent": tangent,
                    "way_id": int(way.get("id") or 0),
                    "highway": highway,
                    "distance2": distance2,
                }
    if best is None:
        raise RuntimeError("No suitable road found near Polo II patch center")
    return best


def set_photo_world(scene):
    world = scene.world or bpy.data.worlds.new("PhotoPatch_World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs["Color"].default_value = (0.075, 0.095, 0.13, 1.0)
        bg.inputs["Strength"].default_value = 0.55

    sun_data = bpy.data.lights.new("PhotoPatch_Sun", "SUN")
    sun_data.energy = 2.0
    sun_data.angle = math.radians(8.0)
    sun_data.color = (1.0, 0.82, 0.64)
    sun = bpy.data.objects.new("PhotoPatch_Sun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (
        math.radians(42.0),
        math.radians(-16.0),
        math.radians(-38.0),
    )

    fill_data = bpy.data.lights.new("PhotoPatch_Fill", "AREA")
    fill_data.energy = 1300.0
    fill_data.shape = "DISK"
    fill_data.size = 70.0
    fill_data.color = (0.58, 0.72, 1.0)
    fill = bpy.data.objects.new("PhotoPatch_Fill", fill_data)
    bpy.context.collection.objects.link(fill)
    cx, cy = PATCH_CENTER
    fill.location = (cx - 55.0, cy - 25.0, 85.0)
    point_at(fill, (cx, cy, 18.0))


def add_camera(scene, terrain: TerrainSampler, nodes, ways):
    pose = nearest_road_pose(nodes, ways)
    road_x, road_y = pose["xy"]
    tangent = pose["tangent"]
    side = Vector((-tangent.y, tangent.x))

    # Oblique architectural/miniature still: a little behind and to the side
    # of the road, high enough to read roofs but close enough to read street
    # furniture.
    camera_x = road_x - float(tangent.x) * 34.0 + float(side.x) * 22.0
    camera_y = road_y - float(tangent.y) * 34.0 + float(side.y) * 22.0
    camera_ground = terrain.sample(camera_x, camera_y)
    road_ground = terrain.sample(road_x, road_y)
    if camera_ground is None or road_ground is None:
        raise RuntimeError("Photo camera fell outside terrain")

    target_x = road_x + float(tangent.x) * 26.0
    target_y = road_y + float(tangent.y) * 26.0
    target_ground = terrain.sample(target_x, target_y)
    if target_ground is None:
        target_ground = road_ground

    camera_data = bpy.data.cameras.new("PhotoPatch_Camera")
    camera = bpy.data.objects.new("PhotoPatch_Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    scene.camera = camera
    camera.location = (camera_x, camera_y, camera_ground + 19.0)
    camera.data.lens = 48.0
    camera.data.sensor_width = 36.0
    camera.data.clip_start = 0.1
    camera.data.clip_end = 800.0
    camera.data.dof.use_dof = True
    camera.data.dof.focus_distance = (
        Vector((target_x, target_y, target_ground + 4.0)) - camera.location
    ).length
    camera.data.dof.aperture_fstop = 4.2
    point_at(camera, (target_x, target_y, target_ground + 4.0))

    return {
        "road_way_id": pose["way_id"],
        "highway": pose["highway"],
        "road_anchor": [road_x, road_y, road_ground],
        "location": list(camera.location),
        "target": [target_x, target_y, target_ground + 4.0],
        "lens": camera.data.lens,
        "fstop": camera.data.dof.aperture_fstop,
    }


def render_hero(scene):
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.filepath = str(HERO)
    bpy.ops.render.render(write_still=True)


def render_overview(scene, terrain: TerrainSampler):
    original_camera = scene.camera
    cx, cy = PATCH_CENTER
    ground = terrain.sample(cx, cy) or 0.0

    data = bpy.data.cameras.new("PhotoPatch_Overview")
    camera = bpy.data.objects.new("PhotoPatch_Overview", data)
    bpy.context.collection.objects.link(camera)
    scene.camera = camera
    camera.location = (cx, cy, ground + 320.0)
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = PATCH_HALF * 2.15
    camera.rotation_euler = (0.0, 0.0, 0.0)
    camera.rotation_euler[0] = 0.0
    camera.rotation_euler = (0.0, 0.0, 0.0)
    point_at(camera, (cx, cy, ground))

    scene.render.resolution_x = 900
    scene.render.resolution_y = 900
    scene.render.filepath = str(TOP)
    bpy.ops.render.render(write_still=True)

    bpy.data.objects.remove(camera, do_unlink=True)
    scene.camera = original_camera


def main():
    for required in (BASE, OSM_LOCAL, TERRAIN):
        if not required.is_file():
            raise SystemExit(f"Missing input: {required}")

    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(BASE))

    source = json.loads(OSM_LOCAL.read_text())
    terrain = TerrainSampler(TERRAIN)

    before = {
        "objects": len(bpy.context.scene.objects),
        "mesh_objects": sum(obj.type == "MESH" for obj in bpy.context.scene.objects),
        "vertices": sum(
            len(obj.data.vertices)
            for obj in bpy.context.scene.objects
            if obj.type == "MESH"
        ),
        "faces": sum(
            len(obj.data.polygons)
            for obj in bpy.context.scene.objects
            if obj.type == "MESH"
        ),
    }

    crop = crop_scene()
    bevel = add_building_bevel()

    scene = bpy.context.scene
    set_photo_world(scene)
    camera = add_camera(scene, terrain, source["nodes"], source["ways"])

    scene["photo_patch_version"] = "coimbra-polo2-photo-patch-v1"
    scene["photo_patch_center"] = list(PATCH_CENTER)
    scene["photo_patch_size_m"] = PATCH_HALF * 2.0
    scene["photo_patch_source"] = "Coimbra 010 cropped for single still"

    after = {
        "objects": len(scene.objects),
        "mesh_objects": sum(obj.type == "MESH" for obj in scene.objects),
        "vertices": sum(
            len(obj.data.vertices)
            for obj in scene.objects
            if obj.type == "MESH"
        ),
        "faces": sum(
            len(obj.data.polygons)
            for obj in scene.objects
            if obj.type == "MESH"
        ),
    }

    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))
    render_hero(scene)
    render_overview(scene, terrain)

    manifest = {
        "version": "coimbra-polo2-photo-patch-v1",
        "patch_center_xy": list(PATCH_CENTER),
        "patch_size_m": PATCH_HALF * 2.0,
        "base": BASE.relative_to(ROOT).as_posix(),
        "output": OUT_BLEND.relative_to(ROOT).as_posix(),
        "hero": HERO.relative_to(ROOT).as_posix(),
        "overview": TOP.relative_to(ROOT).as_posix(),
        "before": before,
        "after": after,
        "reduction": {
            "vertices_fraction": after["vertices"] / max(1, before["vertices"]),
            "faces_fraction": after["faces"] / max(1, before["faces"]),
        },
        "camera": camera,
        "building_bevel": bevel,
        "crop_objects": crop,
        "note": (
            "This scene is intentionally a single-photo patch, not a replacement "
            "for the full Coimbra 010 scene."
        ),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
