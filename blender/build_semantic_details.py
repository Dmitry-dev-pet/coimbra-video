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

import add_vegetation as vegetation  # type: ignore
import enhance_hero_buildings as hero  # type: ignore


SOURCE = ROOT / "bridge_output_019" / "coimbra-full-route-pitched-roofs.blend"
DETECTIONS = ROOT / "data" / "processed" / "bridge_semantic_details_2025.json"
TERRAIN = ROOT / "bridge_output_008b" / "bridge_terrain_highres_2m.npz"
OUT = ROOT / "bridge_output_021"
IMAGE = OUT / "semantic-details.png"
INTERNAL = OUT / "semantic-details-internal.json"


def remove_old_tree_layer():
    removed = []
    for obj in list(bpy.data.objects):
        if obj.name == "Vegetation_Trees" or obj.name.startswith("Semantic_Trees"):
            removed.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
    return removed


def tree_materials():
    return [
        vegetation.tree_material("Semantic_Trunk", (0.13, 0.065, 0.025, 1.0), 0.86),
        vegetation.tree_material("Semantic_Leaves_A", (0.035, 0.16, 0.035, 1.0), 0.91),
        vegetation.tree_material("Semantic_Leaves_B", (0.07, 0.24, 0.045, 1.0), 0.91),
        vegetation.tree_material("Semantic_Leaves_C", (0.14, 0.30, 0.055, 1.0), 0.90),
    ]


def build_semantic_trees(items, terrain):
    vertices = []
    faces = []
    indices = []
    accepted = []

    for index, item in enumerate(items):
        x = float(item["x"])
        y = float(item["y"])
        z = terrain.sample(x, y)
        if z is None:
            continue

        height = max(3.0, min(18.0, float(item["height"])))
        crown_radius = max(1.15, min(5.8, float(item["radius"])))
        token = f"semantic-tree:{x:.2f}:{y:.2f}"
        u0 = hero.stable_unit(token, 0)
        u1 = hero.stable_unit(token, 1)
        u2 = hero.stable_unit(token, 2)
        u3 = hero.stable_unit(token, 3)

        trunk_height = height * (0.23 + u0 * 0.10)
        trunk_radius = max(0.12, min(0.42, height * 0.022))
        rotation = u1 * math.tau

        vegetation.add_prism(
            vertices,
            faces,
            indices,
            center=Vector((x, y, z)),
            radius=trunk_radius,
            z0=z + 0.03,
            z1=z + trunk_height,
            sides=7,
            material_index=0,
            rotation=rotation,
        )

        leaf_slot = 1 + int(u2 * 3.0) % 3
        crown_height = max(2.0, height - trunk_height * 0.55)
        vegetation.add_crown(
            vertices,
            faces,
            indices,
            center=Vector((x, y, z)),
            base_z=z + trunk_height * 0.58,
            height=crown_height,
            radius=crown_radius,
            sides=10,
            material_index=leaf_slot,
            rotation=rotation,
            variant=0,
        )

        # A small offset secondary crown avoids the "single perfect ball"
        # appearance while keeping the entire city in one consolidated mesh.
        if height >= 5.0 and u3 > 0.22:
            angle = hero.stable_unit(token, 4) * math.tau
            offset = crown_radius * (0.16 + hero.stable_unit(token, 5) * 0.12)
            secondary = Vector(
                (
                    x + math.cos(angle) * offset,
                    y + math.sin(angle) * offset,
                    z,
                )
            )
            vegetation.add_crown(
                vertices,
                faces,
                indices,
                center=secondary,
                base_z=z + trunk_height * 0.72,
                height=crown_height * 0.70,
                radius=crown_radius * 0.70,
                sides=9,
                material_index=leaf_slot,
                rotation=rotation + 0.37,
                variant=0,
            )

        accepted.append(
            {
                "x": x,
                "y": y,
                "z": z,
                "height": height,
                "radius": crown_radius,
            }
        )

    mesh = bpy.data.meshes.new("Semantic_Trees_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Semantic_Trees", mesh)
    bpy.context.collection.objects.link(obj)

    mats = tree_materials()
    for mat in mats:
        mesh.materials.append(mat)
    for polygon, slot in zip(mesh.polygons, indices):
        polygon.material_index = slot
        polygon.use_smooth = slot != 0

    obj["source"] = "OpenEarthMap FasterSeg + DGT Orthophotos 2025 + DGT LiDAR HAG"
    obj["tree_count"] = len(accepted)
    return obj, accepted


def canopy_materials():
    return [
        vegetation.tree_material("Semantic_Forest_Mass_A", (0.028, 0.12, 0.028, 1.0), 0.94),
        vegetation.tree_material("Semantic_Forest_Mass_B", (0.055, 0.18, 0.038, 1.0), 0.94),
        vegetation.tree_material("Semantic_Scrub_A", (0.10, 0.20, 0.055, 1.0), 0.95),
        vegetation.tree_material("Semantic_Scrub_B", (0.16, 0.27, 0.075, 1.0), 0.95),
    ]


def build_canopy_masses(items, terrain):
    vertices = []
    faces = []
    indices = []
    accepted = []

    for index, item in enumerate(items):
        x = float(item["x"])
        y = float(item["y"])
        z = terrain.sample(x, y)
        if z is None:
            continue

        token = f"mass:{x:.2f}:{y:.2f}"
        u0 = hero.stable_unit(token, 0)
        u1 = hero.stable_unit(token, 1)
        kind = str(item.get("kind") or "scrub")
        base_height = float(item["height"])
        radius = float(item["radius"])

        if kind == "forest":
            height = base_height * (0.82 + u0 * 0.34)
            slot = 0 if u1 < 0.55 else 1
            sides = 7
        else:
            height = base_height * (0.78 + u0 * 0.28)
            slot = 2 if u1 < 0.58 else 3
            sides = 6

        center = Vector((x, y, z))
        vegetation.add_crown(
            vertices,
            faces,
            indices,
            center=center,
            base_z=z + 0.05,
            height=max(0.9, height),
            radius=max(0.75, radius),
            sides=sides,
            material_index=slot,
            rotation=hero.stable_unit(token, 2) * math.tau,
            variant=0,
        )

        accepted.append(
            {
                "x": x,
                "y": y,
                "z": z,
                "kind": kind,
                "height": height,
                "radius": radius,
            }
        )

    mesh = bpy.data.meshes.new("Semantic_Canopy_Masses_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Semantic_Canopy_Masses", mesh)
    bpy.context.collection.objects.link(obj)

    for mat in canopy_materials():
        mesh.materials.append(mat)
    for polygon, slot in zip(mesh.polygons, indices):
        polygon.material_index = slot
        polygon.use_smooth = True

    obj["source"] = "OpenEarthMap tree-mask canopy regions + DGT terrain"
    obj["mass_point_count"] = len(accepted)
    return obj, accepted


def undergrowth_materials():
    return [
        vegetation.tree_material("Semantic_Undergrowth_Green_A", (0.10, 0.22, 0.055, 1.0), 0.97),
        vegetation.tree_material("Semantic_Undergrowth_Green_B", (0.16, 0.29, 0.075, 1.0), 0.97),
        vegetation.tree_material("Semantic_Undergrowth_Dry_A", (0.26, 0.27, 0.10, 1.0), 0.98),
        vegetation.tree_material("Semantic_Undergrowth_Dry_B", (0.34, 0.30, 0.12, 1.0), 0.98),
    ]


def build_undergrowth(items, terrain):
    vertices = []
    faces = []
    indices = []
    accepted = []

    for item in items:
        x = float(item["x"])
        y = float(item["y"])
        z = terrain.sample(x, y)
        if z is None:
            continue

        token = f"undergrowth:{x:.2f}:{y:.2f}"
        kind = str(item.get("kind") or "green-scrub")
        base_height = float(item["height"])
        radius = float(item["radius"])
        u0 = hero.stable_unit(token, 0)
        u1 = hero.stable_unit(token, 1)

        if kind == "green-scrub":
            slot = 0 if u1 < 0.60 else 1
        else:
            slot = 2 if u1 < 0.58 else 3

        height = max(0.55, min(3.0, base_height * (0.78 + 0.34 * u0)))
        vegetation.add_crown(
            vertices,
            faces,
            indices,
            center=Vector((x, y, z)),
            base_z=z + 0.02,
            height=height,
            radius=max(0.65, min(1.95, radius)),
            sides=6,
            material_index=slot,
            rotation=hero.stable_unit(token, 2) * math.tau,
            variant=0,
        )
        accepted.append(
            {
                "x": x,
                "y": y,
                "z": z,
                "height": height,
                "radius": radius,
                "kind": kind,
            }
        )

    mesh = bpy.data.meshes.new("Semantic_Undergrowth_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Semantic_Undergrowth", mesh)
    bpy.context.collection.objects.link(obj)

    for mat in undergrowth_materials():
        mesh.materials.append(mat)
    for polygon, slot in zip(mesh.polygons, indices):
        polygon.material_index = slot
        polygon.use_smooth = True

    obj["source"] = "OpenEarthMap rangeland + DGT ortho color + local HAG"
    obj["undergrowth_count"] = len(accepted)
    return obj, accepted


def pool_materials():
    water = hero.material("Semantic_Pool_Water", (0.025, 0.24, 0.43, 1.0), 0.18)
    water.use_nodes = True
    bsdf = water.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = 0.04
        if "Coat Weight" in bsdf.inputs:
            bsdf.inputs["Coat Weight"].default_value = 0.35
        if "Coat Roughness" in bsdf.inputs:
            bsdf.inputs["Coat Roughness"].default_value = 0.12
    rim = hero.material("Semantic_Pool_Rim", (0.70, 0.69, 0.63, 1.0), 0.76)
    return [water, rim]


def build_pools(items, terrain):
    vertices = []
    faces = []
    indices = []
    accepted = []

    for item in items:
        polygon = [(float(x), float(y)) for x, y in item["polygon_local"]]
        if len(polygon) < 3:
            continue
        cx, cy = map(float, item["center_local"])
        z = terrain.sample(cx, cy)
        if z is None:
            continue

        signed = hero.polygon_signed_area(polygon)
        ordered = polygon if signed > 0 else list(reversed(polygon))
        loop = [Vector((x, y, z + 0.10)) for x, y in ordered]
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
            indices.append(0)

        # Pale coping around the water polygon makes small pools read clearly
        # from an oblique aerial view.
        for p0, p1 in zip(polygon, polygon[1:] + polygon[:1]):
            a = Vector((p0[0], p0[1], 0.0))
            b = Vector((p1[0], p1[1], 0.0))
            delta = b - a
            length = delta.length
            if length < 0.5:
                continue
            along = delta.normalized()
            outward = Vector((-along.y, along.x, 0.0))
            midpoint = (a + b) * 0.5 + Vector((0.0, 0.0, z + 0.13))
            hero.add_oriented_box(
                vertices,
                faces,
                indices,
                center=midpoint,
                axis_x=along,
                axis_y=outward,
                sx=length,
                sy=0.28,
                sz=0.12,
                material_index=1,
            )

        accepted.append(
            {
                "center": [cx, cy, z + 0.10],
                "area_m2": float(item["area_m2"]),
            }
        )

    mesh = bpy.data.meshes.new("Semantic_Pools_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Semantic_Pools", mesh)
    bpy.context.collection.objects.link(obj)
    for mat in pool_materials():
        mesh.materials.append(mat)
    for polygon, slot in zip(mesh.polygons, indices):
        polygon.material_index = slot

    obj["source"] = "OpenEarthMap water class + DGT Orthophotos 2025"
    obj["pool_count"] = len(accepted)
    return obj, accepted


def visible(scene, camera, point):
    co = world_to_camera_view(scene, camera, Vector(point))
    return (
        co.z > 0.0
        and -0.04 <= co.x <= 1.04
        and -0.04 <= co.y <= 1.04
    )


def choose_review_frame(scene, camera, trees, masses, undergrowth, pools):
    original = scene.frame_current
    tree_sample = trees[:: max(1, len(trees) // 650)]
    mass_sample = masses[:: max(1, len(masses) // 850)]
    under_sample = undergrowth[:: max(1, len(undergrowth) // 900)]
    best = None

    for frame in range(1, 361, 2):
        scene.frame_set(frame)
        visible_pools = [
            pool for pool in pools
            if visible(scene, camera, pool["center"])
        ]
        tree_count = sum(
            visible(
                scene,
                camera,
                (
                    tree["x"],
                    tree["y"],
                    tree["z"] + tree["height"] * 0.55,
                ),
            )
            for tree in tree_sample
        )
        mass_count = sum(
            visible(
                scene,
                camera,
                (
                    item["x"],
                    item["y"],
                    item["z"] + item["height"] * 0.55,
                ),
            )
            for item in mass_sample
        )
        under_count = sum(
            visible(
                scene,
                camera,
                (
                    item["x"],
                    item["y"],
                    item["z"] + item["height"] * 0.55,
                ),
            )
            for item in under_sample
        )

        # Prefer a vegetation-rich production frame. Pools are still useful
        # landmarks, but they no longer dominate camera selection.
        pool_score = sum(
            2.0 + min(8.0, pool["area_m2"] * 0.05)
            for pool in visible_pools
        )
        score = (
            tree_count * 0.12
            + mass_count * 0.18
            + under_count * 0.22
            + pool_score
        )
        row = (
            score,
            under_count,
            mass_count,
            tree_count,
            len(visible_pools),
            frame,
        )
        if best is None or row > best:
            best = row

    scene.frame_set(original)
    assert best is not None
    return {
        "frame": int(best[5]),
        "visible_pools": int(best[4]),
        "sampled_visible_trees": int(best[3]),
        "sampled_visible_canopy_masses": int(best[2]),
        "sampled_visible_undergrowth": int(best[1]),
        "score": float(best[0]),
    }


def point_at(camera, target):
    camera.rotation_euler = (
        Vector(target) - camera.location
    ).to_track_quat("-Z", "Y").to_euler()


def make_pool_review_camera(scene, production_camera, pools, terrain):
    # If the production route never actually sees a detected pool, place a
    # dedicated inspection camera near the largest candidate. This remains an
    # image-only QA camera and never alters the production route.
    pool = max(pools, key=lambda item: item["area_m2"])
    target = Vector(pool["center"])
    best = None
    original = scene.frame_current
    for frame in range(1, 361):
        scene.frame_set(frame)
        distance_xy = math.hypot(
            production_camera.location.x - target.x,
            production_camera.location.y - target.y,
        )
        if best is None or distance_xy < best[0]:
            best = (distance_xy, frame, production_camera.location.copy())
    scene.frame_set(original)
    assert best is not None

    data = bpy.data.cameras.new("Semantic_Detail_Camera")
    camera = bpy.data.objects.new("Semantic_Detail_Camera", data)
    bpy.context.collection.objects.link(camera)

    source_location = best[2]
    horizontal = Vector(
        (
            source_location.x - target.x,
            source_location.y - target.y,
            0.0,
        )
    )
    if horizontal.length < 1.0:
        horizontal = Vector((-1.0, -1.0, 0.0))
    horizontal.normalize()

    camera.location = target + horizontal * 85.0 + Vector((0.0, 0.0, 52.0))
    data.lens = 58.0
    data.sensor_width = 36.0
    data.clip_start = 0.08
    data.clip_end = 1200.0
    data.dof.use_dof = True
    data.dof.aperture_fstop = 6.3
    focus = Vector((target.x, target.y, target.z + 1.0))
    point_at(camera, focus)
    data.dof.focus_distance = (focus - camera.location).length
    return camera, int(best[1])


def main():
    for required in (SOURCE, DETECTIONS, TERRAIN):
        if not required.is_file():
            raise SystemExit(f"Missing input: {required}")

    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    scene = bpy.context.scene
    production_camera = scene.camera
    if production_camera is None:
        raise RuntimeError("production camera missing")

    data = json.loads(DETECTIONS.read_text())
    terrain = hero.TerrainSampler(TERRAIN)

    removed = remove_old_tree_layer()
    tree_obj, trees = build_semantic_trees(data.get("trees") or [], terrain)
    mass_obj, masses = build_canopy_masses(data.get("canopy_masses") or [], terrain)
    under_obj, undergrowth = build_undergrowth(data.get("undergrowth") or [], terrain)
    pool_obj, pools = build_pools(data.get("pools") or [], terrain)

    if len(trees) < 250:
        raise RuntimeError(f"Semantic tree replacement too sparse: {len(trees)}")
    if len(masses) < 1000:
        raise RuntimeError(f"Semantic canopy mass layer too sparse: {len(masses)}")
    if len(undergrowth) < 1000:
        raise RuntimeError(f"Semantic undergrowth layer too sparse: {len(undergrowth)}")
    if len(pools) < 1:
        raise RuntimeError("No swimming-pool candidates survived semantic filtering")

    review = choose_review_frame(
        scene,
        production_camera,
        trees,
        masses,
        undergrowth,
        pools,
    )
    custom_camera = None
    scene.frame_set(review["frame"])
    scene.camera = production_camera
    camera_mode = "production-route-vegetation-rich"

    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.filepath = str(IMAGE)
    bpy.ops.render.render(write_still=True)

    internal = {
        "version": "coimbra-semantic-detail-render-v1",
        "source_scene": SOURCE.relative_to(ROOT).as_posix(),
        "image": IMAGE.relative_to(ROOT).as_posix(),
        "detected_trees": len(data.get("trees") or []),
        "placed_trees": len(trees),
        "detected_canopy_mass_points": len(data.get("canopy_masses") or []),
        "placed_canopy_mass_points": len(masses),
        "detected_undergrowth_points": len(data.get("undergrowth") or []),
        "placed_undergrowth_points": len(undergrowth),
        "detected_pools": len(data.get("pools") or []),
        "placed_pools": len(pools),
        "removed_old_tree_objects": removed,
        "review": review,
        "camera_mode": camera_mode,
        "tree_faces": len(tree_obj.data.polygons),
        "canopy_mass_faces": len(mass_obj.data.polygons),
        "undergrowth_faces": len(under_obj.data.polygons),
        "pool_faces": len(pool_obj.data.polygons),
    }
    INTERNAL.write_text(json.dumps(internal, indent=2) + "\n")
    print(json.dumps(internal, indent=2))


if __name__ == "__main__":
    main()
