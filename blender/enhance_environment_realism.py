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

import enhance_hero_realism as realism  # type: ignore


OUT = ROOT / "bridge_output_014"
IMG_48 = OUT / "environment-realism-48mm.png"
IMG_55 = OUT / "environment-realism-55mm.png"
IMG_65 = OUT / "environment-realism-65mm.png"
MANIFEST = OUT / "environment-realism-manifest.json"

PATCH_CENTER = (-168.37, -748.07)
PATCH_HALF = 110.0
MAX_SHRUBS = 90
MAX_GRASS = 240


def point_in_patch(x: float, y: float) -> bool:
    cx, cy = PATCH_CENTER
    return abs(x - cx) <= PATCH_HALF and abs(y - cy) <= PATCH_HALF


def line_for_way(way, nodes):
    result = []
    for node_id in way.get("nodes") or []:
        node = nodes.get(str(node_id))
        if node is None:
            continue
        x, y = node["xy"]
        result.append((float(x), float(y)))
    if len(result) >= 4 and result[0] == result[-1]:
        result = result[:-1]
    return result


def clip_polygon_axis(points, axis, value, keep_greater):
    if not points:
        return []

    def inside(point):
        coord = point[axis]
        return coord >= value if keep_greater else coord <= value

    def intersection(a, b):
        da = b[axis] - a[axis]
        if abs(da) < 1e-12:
            return a
        t = (value - a[axis]) / da
        return (
            a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
        )

    output = []
    previous = points[-1]
    previous_inside = inside(previous)
    for current in points:
        current_inside = inside(current)
        if current_inside:
            if not previous_inside:
                output.append(intersection(previous, current))
            output.append(current)
        elif previous_inside:
            output.append(intersection(previous, current))
        previous = current
        previous_inside = current_inside
    return output


def clip_to_patch(points):
    cx, cy = PATCH_CENTER
    h = PATCH_HALF
    clipped = list(points)
    clipped = clip_polygon_axis(clipped, 0, cx - h, True)
    clipped = clip_polygon_axis(clipped, 0, cx + h, False)
    clipped = clip_polygon_axis(clipped, 1, cy - h, True)
    clipped = clip_polygon_axis(clipped, 1, cy + h, False)
    if len(clipped) < 3:
        return []
    return clipped


def green_area_ways(source):
    accepted = []
    for way in source["ways"]:
        tags = way.get("tags") or {}
        landuse = str(tags.get("landuse") or "").lower()
        leisure = str(tags.get("leisure") or "").lower()
        natural = str(tags.get("natural") or "").lower()

        is_green = (
            landuse in {"grass", "meadow", "forest", "recreation_ground", "village_green"}
            or leisure in {"park", "garden", "pitch", "golf_course"}
            or natural in {"wood", "grassland", "scrub", "heath"}
        )
        if not is_green:
            continue

        polygon = line_for_way(way, source["nodes"])
        if len(polygon) < 3:
            continue
        clipped = clip_to_patch(polygon)
        if len(clipped) < 3 or realism.hero.polygon_area(clipped) < 4.0:
            continue
        accepted.append(
            {
                "way_id": int(way["id"]),
                "tags": tags,
                "polygon": clipped,
            }
        )
    return accepted


def building_polygons(source):
    polygons = []
    for way in source["ways"]:
        tags = way.get("tags") or {}
        if "building" not in tags:
            continue
        polygon = line_for_way(way, source["nodes"])
        if len(polygon) < 3:
            continue
        if not any(point_in_patch(x, y) for x, y in polygon):
            center = realism.hero.polygon_centroid(polygon)
            if not point_in_patch(*center):
                continue
        polygons.append(polygon)
    return polygons


def point_segment_distance(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx = bx - ax
    dy = by - ay
    length2 = dx * dx + dy * dy
    if length2 <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / length2
    t = max(0.0, min(1.0, t))
    qx = ax + t * dx
    qy = ay + t * dy
    return math.hypot(px - qx, py - qy)


def road_segments(source):
    segments = []
    widths = {
        "motorway": 10.0,
        "trunk": 9.0,
        "primary": 8.0,
        "secondary": 7.0,
        "tertiary": 6.0,
        "residential": 5.0,
        "living_street": 4.5,
        "service": 4.0,
        "unclassified": 4.5,
        "footway": 2.0,
        "path": 2.0,
        "cycleway": 2.2,
    }
    for way in source["ways"]:
        tags = way.get("tags") or {}
        highway = str(tags.get("highway") or "").lower()
        if not highway:
            continue
        line = line_for_way(way, source["nodes"])
        if len(line) < 2:
            continue
        width = widths.get(highway, 4.5)
        for a, b in zip(line[:-1], line[1:]):
            segments.append((a, b, width))
    return segments


def blocked_point(x, y, buildings, roads):
    if any(realism.hero.point_in_polygon(x, y, polygon) for polygon in buildings):
        return True
    for a, b, width in roads:
        if point_segment_distance(x, y, a, b) < width * 0.5 + 1.25:
            return True
    return False


def create_noisy_material(name, low, high, *, scale, rough_low, rough_high, bump_scale, bump_strength):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    texcoord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 3.0
    noise.inputs["Roughness"].default_value = 0.62

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.28
    ramp.color_ramp.elements[0].color = low
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = high

    rough = nodes.new("ShaderNodeMapRange")
    rough.inputs["From Min"].default_value = 0.0
    rough.inputs["From Max"].default_value = 1.0
    rough.inputs["To Min"].default_value = rough_low
    rough.inputs["To Max"].default_value = rough_high

    micro = nodes.new("ShaderNodeTexNoise")
    micro.inputs["Scale"].default_value = bump_scale
    micro.inputs["Detail"].default_value = 2.0
    micro.inputs["Roughness"].default_value = 0.72
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = 0.055

    links.new(texcoord.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(noise.outputs["Fac"], rough.inputs["Value"])
    links.new(texcoord.outputs["Generated"], micro.inputs["Vector"])
    links.new(micro.outputs["Fac"], bump.inputs["Height"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    mat.diffuse_color = high
    return mat


def improve_surface_materials():
    stats = {"sidewalk_slots": 0, "curb_slots": 0}

    sidewalk = bpy.data.objects.get("Urban_Sidewalks")
    if sidewalk is not None and sidewalk.type == "MESH":
        new_mat = create_noisy_material(
            "EnvR_Sidewalk_Concrete",
            (0.27, 0.255, 0.235, 1.0),
            (0.43, 0.405, 0.365, 1.0),
            scale=5.5,
            rough_low=0.76,
            rough_high=0.92,
            bump_scale=44.0,
            bump_strength=0.16,
        )
        for index in range(len(sidewalk.data.materials)):
            sidewalk.data.materials[index] = new_mat
            stats["sidewalk_slots"] += 1

    curbs = bpy.data.objects.get("Urban_Curbs")
    if curbs is not None and curbs.type == "MESH":
        new_mat = create_noisy_material(
            "EnvR_Curb_Concrete",
            (0.34, 0.335, 0.32, 1.0),
            (0.54, 0.525, 0.49, 1.0),
            scale=7.0,
            rough_low=0.78,
            rough_high=0.94,
            bump_scale=55.0,
            bump_strength=0.13,
        )
        for index in range(len(curbs.data.materials)):
            curbs.data.materials[index] = new_mat
            stats["curb_slots"] += 1

    if stats["sidewalk_slots"] <= 0:
        raise RuntimeError("Urban_Sidewalks material slots not found")
    if stats["curb_slots"] <= 0:
        raise RuntimeError("Urban_Curbs material slots not found")
    return stats


def add_ground_polygon(vertices, faces, indices, polygon, terrain, material_index):
    signed = realism.hero.polygon_signed_area(polygon)
    ordered = polygon if signed > 0 else list(reversed(polygon))
    loop = []
    for x, y in ordered:
        z = terrain.sample(float(x), float(y))
        if z is None:
            return 0
        loop.append(Vector((x, y, z + 0.035)))

    triangles = tessellate_polygon([loop])
    added = 0
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
        added += 1
    return added


def add_shrub(vertices, faces, indices, x, y, z, token, material_index):
    radius = 0.38 + realism.hero.stable_unit(token, 1) * 0.48
    height = 0.42 + realism.hero.stable_unit(token, 2) * 0.72
    sides = 7
    rotation = realism.hero.stable_unit(token, 3) * math.tau
    base = len(vertices)

    vertices.append((x, y, z + 0.02))
    for frac, scale in ((0.30, 1.0), (0.70, 0.82)):
        ring_z = z + height * frac
        for i in range(sides):
            angle = rotation + math.tau * i / sides
            vertices.append(
                (
                    x + math.cos(angle) * radius * scale,
                    y + math.sin(angle) * radius * scale,
                    ring_z,
                )
            )
    top = len(vertices)
    vertices.append((x, y, z + height))

    ring1 = base + 1
    ring2 = ring1 + sides
    for i in range(sides):
        j = (i + 1) % sides
        faces.append((base, ring1 + j, ring1 + i))
        indices.append(material_index)
        faces.append((ring1 + i, ring1 + j, ring2 + j, ring2 + i))
        indices.append(material_index)
        faces.append((ring2 + i, ring2 + j, top))
        indices.append(material_index)


def add_grass_tuft(vertices, faces, indices, x, y, z, token, material_index):
    height = 0.22 + realism.hero.stable_unit(token, 10) * 0.32
    width = 0.16 + realism.hero.stable_unit(token, 11) * 0.12
    rotation = realism.hero.stable_unit(token, 12) * math.tau
    for offset in (0.0, math.pi / 3.0, 2.0 * math.pi / 3.0):
        angle = rotation + offset
        dx = math.cos(angle) * width
        dy = math.sin(angle) * width
        start = len(vertices)
        vertices.extend(
            [
                (x - dx, y - dy, z + 0.025),
                (x + dx, y + dy, z + 0.025),
                (x + dx * 0.22, y + dy * 0.22, z + height),
                (x - dx * 0.22, y - dy * 0.22, z + height),
            ]
        )
        faces.append((start, start + 1, start + 2, start + 3))
        indices.append(material_index)


def build_green_environment(source, terrain):
    greens = green_area_ways(source)
    buildings = building_polygons(source)
    roads = road_segments(source)

    ground_vertices = []
    ground_faces = []
    ground_indices = []
    ground_material = create_noisy_material(
        "EnvR_GreenGround",
        (0.055, 0.105, 0.035, 1.0),
        (0.16, 0.22, 0.075, 1.0),
        scale=3.2,
        rough_low=0.86,
        rough_high=0.98,
        bump_scale=28.0,
        bump_strength=0.10,
    )

    green_triangles = 0
    for area in greens:
        green_triangles += add_ground_polygon(
            ground_vertices,
            ground_faces,
            ground_indices,
            area["polygon"],
            terrain,
            0,
        )

    ground_obj = None
    if ground_faces:
        mesh = bpy.data.meshes.new("Hero_GreenGround_Mesh")
        mesh.from_pydata(ground_vertices, [], ground_faces)
        mesh.update()
        ground_obj = bpy.data.objects.new("Hero_GreenGround", mesh)
        bpy.context.collection.objects.link(ground_obj)
        mesh.materials.append(ground_material)

    veg_vertices = []
    veg_faces = []
    veg_indices = []
    veg_materials = [
        realism.hero.material("EnvR_Shrub_A", (0.045, 0.14, 0.035, 1.0), 0.94),
        realism.hero.material("EnvR_Shrub_B", (0.085, 0.20, 0.045, 1.0), 0.94),
        realism.hero.material("EnvR_Grass", (0.13, 0.20, 0.055, 1.0), 0.96),
    ]

    shrubs = 0
    grass = 0
    for area in greens:
        polygon = area["polygon"]
        xs = [point[0] for point in polygon]
        ys = [point[1] for point in polygon]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)

        step = 5.5
        row = 0
        y = miny + 1.8
        while y <= maxy - 1.2:
            x = minx + 1.8 + (row % 2) * (step * 0.42)
            while x <= maxx - 1.2:
                token = f"green:{area['way_id']}:{x:.2f}:{y:.2f}"
                jx = (realism.hero.stable_unit(token, 20) - 0.5) * 2.4
                jy = (realism.hero.stable_unit(token, 21) - 0.5) * 2.4
                px = x + jx
                py = y + jy
                if (
                    realism.hero.point_in_polygon(px, py, polygon)
                    and not blocked_point(px, py, buildings, roads)
                ):
                    z = terrain.sample(px, py)
                    if z is not None:
                        if shrubs < MAX_SHRUBS and realism.hero.stable_unit(token, 22) < 0.33:
                            mat_index = 0 if realism.hero.stable_unit(token, 23) < 0.56 else 1
                            add_shrub(
                                veg_vertices, veg_faces, veg_indices,
                                px, py, z, token, mat_index,
                            )
                            shrubs += 1
                        elif grass < MAX_GRASS:
                            add_grass_tuft(
                                veg_vertices, veg_faces, veg_indices,
                                px, py, z, token, 2,
                            )
                            grass += 1
                x += step
            y += step
            row += 1

    veg_obj = None
    if veg_faces:
        mesh = bpy.data.meshes.new("Hero_Groundcover_Mesh")
        mesh.from_pydata(veg_vertices, [], veg_faces)
        mesh.update()
        veg_obj = bpy.data.objects.new("Hero_Groundcover", mesh)
        bpy.context.collection.objects.link(veg_obj)
        for mat in veg_materials:
            mesh.materials.append(mat)
        for polygon, index in zip(mesh.polygons, veg_indices):
            polygon.material_index = index

    if not greens:
        raise RuntimeError("No OSM green areas intersect the Polo II patch")
    if shrubs < 6 or grass < 20:
        raise RuntimeError(
            f"Groundcover unexpectedly sparse: shrubs={shrubs} grass={grass}"
        )

    return {
        "green_ways": len(greens),
        "green_ground_triangles": green_triangles,
        "shrubs": shrubs,
        "grass_tufts": grass,
        "ground_faces": len(ground_faces),
        "groundcover_faces": len(veg_faces),
    }


def improve_lighting(scene):
    sun = bpy.data.objects.get("PhotoPatch_Sun")
    fill = bpy.data.objects.get("PhotoPatch_Fill")
    if sun is None or sun.type != "LIGHT":
        raise RuntimeError("PhotoPatch_Sun missing")
    if fill is None or fill.type != "LIGHT":
        raise RuntimeError("PhotoPatch_Fill missing")

    before = {
        "sun_energy": float(sun.data.energy),
        "sun_angle": float(sun.data.angle),
        "fill_energy": float(fill.data.energy),
        "fill_size": float(fill.data.size),
    }

    sun.data.energy = 1.55
    sun.data.angle = math.radians(16.0)
    sun.data.color = (1.0, 0.88, 0.74)
    fill.data.energy = 760.0
    fill.data.size = 92.0
    fill.data.color = (0.66, 0.76, 1.0)

    world_strength = None
    if scene.world is not None and scene.world.use_nodes:
        background = scene.world.node_tree.nodes.get("Background")
        if background is not None:
            background.inputs["Strength"].default_value = 0.46
            background.inputs["Color"].default_value = (0.065, 0.085, 0.12, 1.0)
            world_strength = 0.46

    return {
        "before": before,
        "after": {
            "sun_energy": float(sun.data.energy),
            "sun_angle_deg": math.degrees(float(sun.data.angle)),
            "fill_energy": float(fill.data.energy),
            "fill_size": float(fill.data.size),
            "world_strength": world_strength,
        },
    }


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

    # Build corrected 012b + 013 geometry in-memory without spending time on
    # intermediate review renders.
    realism.hero.render = lambda *args, **kwargs: None
    realism.render = lambda *args, **kwargs: None
    realism.main()

    scene = bpy.context.scene
    source_camera = scene.camera
    if source_camera is None:
        raise RuntimeError("013 hero camera missing")

    source = json.loads(realism.hero.OSM_LOCAL.read_text())
    terrain = realism.hero.TerrainSampler(realism.hero.TERRAIN)

    surfaces = improve_surface_materials()
    environment = build_green_environment(source, terrain)
    lighting = improve_lighting(scene)

    scene["environment_realism_version"] = "coimbra-environment-realism-v1"
    scene["environment_realism_green_ways"] = int(environment["green_ways"])
    scene["environment_realism_groundcover"] = int(
        environment["shrubs"] + environment["grass_tufts"]
    )

    render(scene, source_camera, IMG_48)

    low = realism.clone_camera(
        source_camera,
        "Environment_Low_55",
        lens=55.0,
        z_delta=-4.0,
        target_delta_z=-1.5,
    )
    tele = realism.clone_camera(
        source_camera,
        "Environment_Tele_65",
        lens=65.0,
        z_delta=0.0,
        target_delta_z=0.8,
    )
    render(scene, low, IMG_55)
    render(scene, tele, IMG_65)

    for camera in (low, tele):
        bpy.data.objects.remove(camera, do_unlink=True)
    scene.camera = source_camera

    manifest = {
        "version": "coimbra-environment-realism-v1",
        "base_pass": "coimbra-hero-realism-v1",
        "surfaces": surfaces,
        "environment": environment,
        "lighting": lighting,
        "images": [
            IMG_48.relative_to(ROOT).as_posix(),
            IMG_55.relative_to(ROOT).as_posix(),
            IMG_65.relative_to(ROOT).as_posix(),
        ],
        "rules": {
            "photo_patch_only": True,
            "hero_buildings_unchanged": True,
            "greenery_from_osm_green_areas_only": True,
            "no_blender_artifact": True,
        },
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
