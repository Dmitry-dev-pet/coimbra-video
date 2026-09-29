from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.geometry import tessellate_polygon


ROOT = Path(__file__).resolve().parents[1]
BLENDER_DIR = ROOT / "blender"
if str(BLENDER_DIR) not in sys.path:
    sys.path.insert(0, str(BLENDER_DIR))

import enhance_hero_buildings as hero  # type: ignore


OUT = ROOT / "bridge_output_013"
HERO = OUT / "hero-realism-48mm.png"
LOW = OUT / "hero-realism-low-55mm.png"
TELE = OUT / "hero-realism-65mm.png"
DETAIL = OUT / "hero-realism-detail.png"
MANIFEST = OUT / "hero-realism-manifest.json"

WINDOW_STATS = {
    "requested": 0,
    "emitted": 0,
    "skipped": 0,
    "mullions": 0,
    "shifted": 0,
}
ORIGINAL_ADD_WINDOW = hero.add_window


def window_token(center) -> str:
    c = Vector(center)
    return f"{c.x:.2f}:{c.y:.2f}:{c.z:.2f}"


def realistic_add_window(
    vertices,
    faces,
    indices,
    *,
    center,
    along,
    outward,
    width,
    height,
    frame_width,
    glass_material_index,
    frame_material_index,
    sill_material_index,
):
    WINDOW_STATS["requested"] += 1
    token = window_token(center)
    c = Vector(center)

    camera = bpy.context.scene.camera
    facing = 1.0
    if camera is not None:
        to_camera = camera.location - c
        to_camera.z = 0.0
        if to_camera.length > 1e-8:
            to_camera.normalize()
            facing = float(outward.dot(to_camera))

    # Do not force the same dense window grid onto side/rear walls.
    if facing < 0.0:
        skip_probability = 0.48
    elif facing < 0.28:
        skip_probability = 0.27
    else:
        skip_probability = 0.08

    if hero.stable_unit(token, 0) < skip_probability:
        WINDOW_STATS["skipped"] += 1
        return

    # Tiny deterministic size/position variation breaks the spreadsheet-grid
    # effect while preserving a coherent architectural rhythm.
    width_scale = 0.94 + hero.stable_unit(token, 1) * 0.12
    height_scale = 0.95 + hero.stable_unit(token, 2) * 0.10
    shift = (hero.stable_unit(token, 3) - 0.5) * 0.11
    varied_center = c + along.normalized() * shift
    if abs(shift) > 0.015:
        WINDOW_STATS["shifted"] += 1

    # Mix light and dark frames in a restrained way.
    chosen_frame = frame_material_index
    if hero.stable_unit(token, 4) < 0.14:
        chosen_frame = (
            sill_material_index
            if frame_material_index != sill_material_index
            else frame_material_index
        )

    ORIGINAL_ADD_WINDOW(
        vertices,
        faces,
        indices,
        center=varied_center,
        along=along,
        outward=outward,
        width=width * width_scale,
        height=height * height_scale,
        frame_width=frame_width,
        glass_material_index=glass_material_index,
        frame_material_index=chosen_frame,
        sill_material_index=sill_material_index,
    )
    WINDOW_STATS["emitted"] += 1

    # Many Portuguese urban windows read as two-leaf openings from this distance.
    # A narrow central mullion is enough to convey that without expensive
    # boolean/window-reveal geometry.
    if hero.stable_unit(token, 5) < 0.52:
        hero.add_oriented_box(
            vertices,
            faces,
            indices,
            center=varied_center + outward * 0.16,
            axis_x=along,
            axis_y=outward,
            sx=0.055,
            sy=0.05,
            sz=height * height_scale * 0.92,
            material_index=chosen_frame,
        )
        WINDOW_STATS["mullions"] += 1


def front_edge(item, camera):
    footprint = item["footprint"]
    signed = hero.polygon_signed_area(footprint)
    camera_xy = Vector((camera.location.x, camera.location.y, 0.0))
    center = Vector((item["center"][0], item["center"][1], 0.0))
    to_camera = camera_xy - center
    if to_camera.length > 1e-8:
        to_camera.normalize()

    best = None
    best_score = -1e9
    for edge_index, (p0, p1) in enumerate(
        zip(footprint, footprint[1:] + footprint[:1])
    ):
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        length = math.hypot(dx, dy)
        if length < 0.4:
            continue
        outward = hero.outward_for_edge(p0, p1, signed)
        score = outward.dot(to_camera)
        if score > best_score:
            best_score = score
            best = {
                "index": edge_index,
                "p0": p0,
                "p1": p1,
                "length": length,
                "along": Vector((dx / length, dy / length, 0.0)),
                "outward": outward,
                "facing": float(score),
            }
    return best


def interior_point(footprint):
    signed = hero.polygon_signed_area(footprint)
    ordered = footprint if signed > 0 else list(reversed(footprint))
    loop = [Vector((x, y, 0.0)) for x, y in ordered]
    triangles = tessellate_polygon([loop])
    best = None
    best_area = -1.0
    for triangle in triangles:
        resolved = [
            loop[value] if isinstance(value, int) else value
            for value in triangle
        ]
        if len(resolved) != 3:
            continue
        a, b, c = resolved
        area = abs(
            (b.x - a.x) * (c.y - a.y)
            - (b.y - a.y) * (c.x - a.x)
        ) * 0.5
        if area > best_area:
            best_area = area
            best = (a + b + c) / 3.0
    if best is None:
        cx, cy = hero.polygon_centroid(footprint)
        return Vector((cx, cy, 0.0))
    return best


def realism_materials():
    return [
        hero.material("HeroR_Concrete", (0.42, 0.41, 0.38, 1.0), 0.78),
        hero.material("HeroR_RailMetal", (0.055, 0.060, 0.062, 1.0), 0.32, 0.35),
        hero.material("HeroR_Plinth", (0.20, 0.19, 0.18, 1.0), 0.83),
        hero.material("HeroR_Cornice", (0.70, 0.67, 0.60, 1.0), 0.70),
        hero.material("HeroR_RoofUnit", (0.48, 0.50, 0.48, 1.0), 0.62, 0.08),
        hero.material("HeroR_Downpipe", (0.15, 0.16, 0.16, 1.0), 0.45, 0.28),
    ]


def add_balcony(
    vertices,
    faces,
    indices,
    *,
    edge,
    base_z,
    floor_height,
    floor,
    building_token,
):
    length = edge["length"]
    if length < 5.2:
        return False

    along = edge["along"]
    outward = edge["outward"]
    p0 = Vector((edge["p0"][0], edge["p0"][1], 0.0))
    p1 = Vector((edge["p1"][0], edge["p1"][1], 0.0))
    midpoint = (p0 + p1) * 0.5

    width_fraction = 0.48 + hero.stable_unit(building_token, 31 + floor) * 0.24
    width = min(7.2, max(2.8, length * width_fraction))
    depth = 1.05 + hero.stable_unit(building_token, 41 + floor) * 0.28
    slab_z = base_z + floor_height * floor + 0.12

    slab_center = (
        midpoint
        + outward * (depth * 0.5 + 0.13)
        + Vector((0.0, 0.0, slab_z))
    )
    hero.add_oriented_box(
        vertices,
        faces,
        indices,
        center=slab_center,
        axis_x=along,
        axis_y=outward,
        sx=width,
        sy=depth,
        sz=0.16,
        material_index=0,
    )

    rail_z = slab_z + 0.72
    front = midpoint + outward * (depth + 0.10) + Vector((0.0, 0.0, rail_z))
    hero.add_oriented_box(
        vertices,
        faces,
        indices,
        center=front,
        axis_x=along,
        axis_y=outward,
        sx=width,
        sy=0.055,
        sz=0.06,
        material_index=1,
    )

    post_count = max(3, min(9, int(width / 0.9) + 1))
    for i in range(post_count):
        t = -0.5 + i / max(1, post_count - 1)
        post = (
            midpoint
            + along * (width * t)
            + outward * (depth + 0.10)
            + Vector((0.0, 0.0, slab_z + 0.42))
        )
        hero.add_oriented_box(
            vertices,
            faces,
            indices,
            center=post,
            axis_x=along,
            axis_y=outward,
            sx=0.045,
            sy=0.055,
            sz=0.76,
            material_index=1,
        )

    # Side rails keep balconies from reading as floating shelves.
    for sign in (-1.0, 1.0):
        side_center = (
            midpoint
            + along * (width * 0.5 * sign)
            + outward * (depth * 0.5 + 0.11)
            + Vector((0.0, 0.0, slab_z + 0.72))
        )
        hero.add_oriented_box(
            vertices,
            faces,
            indices,
            center=side_center,
            axis_x=outward,
            axis_y=along,
            sx=depth,
            sy=0.055,
            sz=0.06,
            material_index=1,
        )
    return True


def build_realism_overlay(selected, scene):
    materials = realism_materials()
    vertices = []
    faces = []
    indices = []
    building_stats = []
    camera = scene.camera
    if camera is None:
        raise RuntimeError("hero camera missing after 012 pass")

    balcony_count = 0
    roof_units = 0
    trims = 0
    downpipes = 0

    for rank, item in enumerate(selected):
        edge = front_edge(item, camera)
        if edge is None:
            continue

        base_z = item["ground"]
        top_z = base_z + item["height"]
        floor_height = item["height"] / max(1, item["levels"])
        along = edge["along"]
        outward = edge["outward"]
        p0 = Vector((edge["p0"][0], edge["p0"][1], 0.0))
        p1 = Vector((edge["p1"][0], edge["p1"][1], 0.0))
        midpoint = (p0 + p1) * 0.5
        token = f"building:{item['way_id']}"

        # Darker plinth and a small cornice give the facade a readable base/top.
        plinth = midpoint + outward * 0.16 + Vector((0.0, 0.0, base_z + 0.33))
        hero.add_oriented_box(
            vertices,
            faces,
            indices,
            center=plinth,
            axis_x=along,
            axis_y=outward,
            sx=edge["length"],
            sy=0.09,
            sz=0.62,
            material_index=2,
        )
        cornice = midpoint + outward * 0.17 + Vector((0.0, 0.0, top_z - 0.10))
        hero.add_oriented_box(
            vertices,
            faces,
            indices,
            center=cornice,
            axis_x=along,
            axis_y=outward,
            sx=edge["length"] + 0.18,
            sy=0.18,
            sz=0.20,
            material_index=3,
        )
        trims += 2

        # One downpipe near a facade corner, enough to break the perfect box.
        pipe_point = p0 * 0.88 + p1 * 0.12
        pipe = (
            pipe_point
            + outward * 0.20
            + Vector((0.0, 0.0, base_z + item["height"] * 0.50))
        )
        hero.add_oriented_box(
            vertices,
            faces,
            indices,
            center=pipe,
            axis_x=along,
            axis_y=outward,
            sx=0.10,
            sy=0.10,
            sz=item["height"] * 0.94,
            material_index=5,
        )
        downpipes += 1

        floors = []
        if rank < 2 and item["levels"] >= 2 and edge["facing"] > 0.2:
            floors.append(1)
            if item["levels"] >= 4 and hero.stable_unit(token, 70) < 0.72:
                floors.append(2)

        for floor in floors:
            if add_balcony(
                vertices,
                faces,
                indices,
                edge=edge,
                base_z=base_z,
                floor_height=floor_height,
                floor=floor,
                building_token=token,
            ):
                balcony_count += 1

        # Flat roofs get restrained technical clutter, placed at a guaranteed
        # interior point so nothing floats outside an L-shaped footprint.
        unit_count = 0
        if item["roof"] == "flat":
            inside = interior_point(item["footprint"])
            for unit_index in range(1 + (rank == 0)):
                angle = hero.stable_unit(token, 80 + unit_index) * math.tau
                radial = 0.6 + unit_index * 0.75
                cx = inside.x + math.cos(angle) * radial
                cy = inside.y + math.sin(angle) * radial
                hero.add_oriented_box(
                    vertices,
                    faces,
                    indices,
                    center=(cx, cy, top_z + 0.48),
                    axis_x=Vector((math.cos(angle), math.sin(angle), 0.0)),
                    axis_y=Vector((-math.sin(angle), math.cos(angle), 0.0)),
                    sx=1.25 + 0.25 * unit_index,
                    sy=0.90,
                    sz=0.78,
                    material_index=4,
                )
                unit_count += 1
                roof_units += 1

        building_stats.append(
            {
                "way_id": item["way_id"],
                "front_edge": edge["index"],
                "front_facing": edge["facing"],
                "balcony_floors": floors,
                "roof_units": unit_count,
            }
        )

    mesh = bpy.data.meshes.new("Hero_Realism_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Hero_Realism", mesh)
    bpy.context.collection.objects.link(obj)
    for mat in materials:
        mesh.materials.append(mat)
    for polygon, index in zip(mesh.polygons, indices):
        polygon.material_index = index
    obj["version"] = "coimbra-hero-realism-v1"

    return obj, {
        "buildings": building_stats,
        "balconies": balcony_count,
        "roof_units": roof_units,
        "trim_pieces": trims,
        "downpipes": downpipes,
    }


def camera_forward(camera):
    return camera.matrix_world.to_quaternion() @ Vector((0.0, 0.0, -1.0))


def clone_camera(source, name, *, lens, z_delta=0.0, target_delta_z=0.0):
    data = bpy.data.cameras.new(name)
    camera = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(camera)
    camera.location = source.location.copy()
    camera.location.z += z_delta
    data.lens = lens
    data.sensor_width = source.data.sensor_width
    data.clip_start = 0.08
    data.clip_end = 800.0
    data.dof.use_dof = True
    data.dof.aperture_fstop = 4.8

    forward = camera_forward(source)
    target = source.location + forward * 85.0
    target.z += target_delta_z
    hero.point_at(camera, target)
    data.dof.focus_distance = (target - camera.location).length
    return camera


def render(scene, camera, path, resolution=(1600, 1000)):
    scene.camera = camera
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = int(resolution[0])
    scene.render.resolution_y = int(resolution[1])
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    # Reuse the verified 012 geometry construction in the same Blender process,
    # but replace only the window emitter with the less-regular 013 version.
    hero.add_window = realistic_add_window
    hero.main()

    scene = bpy.context.scene
    source_camera = scene.camera
    if source_camera is None:
        raise RuntimeError("012 hero camera missing")

    source = json.loads(hero.OSM_LOCAL.read_text())
    terrain = hero.TerrainSampler(hero.TERRAIN)
    selected = hero.select_hero_buildings(scene, source, terrain)
    overlay, realism = build_realism_overlay(selected, scene)

    scene["hero_realism_version"] = "coimbra-hero-realism-v1"
    scene["hero_realism_balconies"] = int(realism["balconies"])
    scene["hero_realism_windows_emitted"] = int(WINDOW_STATS["emitted"])

    render(scene, source_camera, HERO)

    low = clone_camera(
        source_camera,
        "Hero_Realism_Low",
        lens=55.0,
        z_delta=-4.0,
        target_delta_z=-1.5,
    )
    tele = clone_camera(
        source_camera,
        "Hero_Realism_Tele",
        lens=65.0,
        z_delta=0.0,
        target_delta_z=0.8,
    )
    render(scene, low, LOW)
    render(scene, tele, TELE)

    # A telephoto inspection of the best-ranked facade from the safe hero
    # position: no close-up camera is allowed to fly into geometry.
    best = selected[0]
    detail_data = bpy.data.cameras.new("Hero_Realism_Detail")
    detail_camera = bpy.data.objects.new("Hero_Realism_Detail", detail_data)
    bpy.context.collection.objects.link(detail_camera)
    detail_camera.location = source_camera.location.copy()
    detail_data.lens = 105.0
    detail_data.sensor_width = 36.0
    detail_data.clip_start = 0.08
    detail_data.clip_end = 800.0
    detail_data.dof.use_dof = True
    detail_data.dof.aperture_fstop = 5.6
    detail_target = Vector(
        (
            best["center"][0],
            best["center"][1],
            best["ground"] + best["height"] * 0.58,
        )
    )
    hero.point_at(detail_camera, detail_target)
    detail_data.dof.focus_distance = (
        detail_target - detail_camera.location
    ).length
    render(scene, detail_camera, DETAIL, (1400, 1000))

    for camera in (low, tele, detail_camera):
        bpy.data.objects.remove(camera, do_unlink=True)
    scene.camera = source_camera

    manifest = {
        "version": "coimbra-hero-realism-v1",
        "base_pass": "coimbra-hero-buildings-v1",
        "hero_buildings": [item["way_id"] for item in selected],
        "window_stats": WINDOW_STATS,
        "realism": realism,
        "overlay_geometry": {
            "vertices": len(overlay.data.vertices),
            "faces": len(overlay.data.polygons),
        },
        "images": [
            HERO.relative_to(ROOT).as_posix(),
            LOW.relative_to(ROOT).as_posix(),
            TELE.relative_to(ROOT).as_posix(),
            DETAIL.relative_to(ROOT).as_posix(),
        ],
        "rules": {
            "full_city_unchanged": True,
            "photo_patch_only": True,
            "balconies_top_two_facades_only": True,
            "closeups_from_safe_hero_position": True,
        },
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
