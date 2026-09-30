"""030: paired production-look review over the accepted frozen 026 scene."""
from __future__ import annotations

from array import array
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))

import render_backend_comparison as backend  # type: ignore
import render_cycles_full_route as full  # type: ignore

REVIEW_FRAMES = [1, 181, 360]
EXPECTED_026_RUN = 36646652931
EXPECTED_BLEND_SHA256 = "5eed3da289693015ed6b491eb26f992f0c579a1625540f1f4acc13155860a590"
EXPECTED_PROTECTED_SHA256 = "98ee88d4c6e28dfccb010b7ad9faa89f88466768eed7ec440fb96d99b276450f"
EXPECTED_RESOLUTION = [1600, 1000]

PALETTE = {
    "Semantic_Leaves_A": ((0.030, 0.115, 0.034, 1.0), 0.90),
    "Semantic_Leaves_B": ((0.052, 0.172, 0.044, 1.0), 0.90),
    "Semantic_Leaves_C": ((0.100, 0.225, 0.058, 1.0), 0.89),
    "Semantic_Forest_Mass_A": ((0.024, 0.090, 0.026, 1.0), 0.95),
    "Semantic_Forest_Mass_B": ((0.045, 0.135, 0.034, 1.0), 0.95),
    "Semantic_Scrub_A": ((0.085, 0.145, 0.050, 1.0), 0.96),
    "Semantic_Scrub_B": ((0.125, 0.185, 0.067, 1.0), 0.96),
    "Semantic_Undergrowth_Green_A": ((0.075, 0.150, 0.047, 1.0), 0.97),
    "Semantic_Undergrowth_Green_B": ((0.115, 0.195, 0.060, 1.0), 0.97),
    "Semantic_Undergrowth_Dry_A": ((0.205, 0.190, 0.080, 1.0), 0.98),
    "Semantic_Undergrowth_Dry_B": ((0.255, 0.215, 0.095, 1.0), 0.98),
    "Semantic_Parking_Asphalt": ((0.105, 0.112, 0.118, 1.0), 0.90),
    "Semantic_Ground_Line": ((0.72, 0.70, 0.63, 1.0), 0.76),
}


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :]
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--prepare", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args(argv)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def structure_digest(scene) -> str:
    """Hash non-light scene structure, mesh data and material assignments, not shader values."""
    scene.frame_set(1)
    bpy.context.view_layer.update()
    h = hashlib.sha256()

    for obj in sorted(scene.objects, key=lambda o: o.name):
        if obj.type == "LIGHT":
            continue
        state = [
            obj.name,
            obj.type,
            [list(row) for row in obj.matrix_world],
            bool(obj.hide_render),
            [slot.material.name if slot.material else None for slot in obj.material_slots],
        ]
        h.update(canonical(state).encode())
        if obj.type != "MESH":
            continue
        mesh = obj.data
        for items, prop, count, kind in (
            (mesh.vertices, "co", 3, "f"),
            (mesh.edges, "vertices", 2, "i"),
            (mesh.loops, "vertex_index", 1, "i"),
            (mesh.polygons, "loop_start", 1, "i"),
            (mesh.polygons, "loop_total", 1, "i"),
            (mesh.polygons, "material_index", 1, "i"),
        ):
            values = array(kind, [0]) * (len(items) * count)
            items.foreach_get(prop, values)
            h.update(canonical([prop, len(items)]).encode())
            h.update(values.tobytes())
        for uv in mesh.uv_layers:
            values = array("f", [0]) * (len(uv.data) * 2)
            uv.data.foreach_get("uv", values)
            h.update(uv.name.encode())
            h.update(values.tobytes())
    return h.hexdigest()


def render_settings(scene) -> dict:
    return full.check_cycles(scene)


def render_review(scene, out: Path, label: str) -> dict:
    results = {}
    for frame in REVIEW_FRAMES:
        scene.frame_set(frame)
        path = out / f"frame-{frame:03d}-{label}.png"
        backend.render_png(scene, path)
        results[str(frame)] = {
            "path": path.name,
            "sha256": full.digest_file(path),
            "bytes": path.stat().st_size,
        }
    return results


def set_principled(mat, color, roughness) -> dict | None:
    if mat is None:
        return None
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat.node_tree else None
    if bsdf is None:
        return None

    changed = {"material": mat.name}
    base = bsdf.inputs.get("Base Color")
    if base is not None and not base.is_linked:
        base.default_value = color
        changed["base_color"] = list(color)
    else:
        changed["base_color"] = "linked-preserved"
    rough = bsdf.inputs.get("Roughness")
    if rough is not None and not rough.is_linked:
        rough.default_value = roughness
        changed["roughness"] = roughness
    else:
        changed["roughness"] = "linked-preserved"
    mat.diffuse_color = color
    return changed


def point_at(obj, target) -> None:
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def apply_look(scene) -> dict:
    changes = {"materials": [], "world": {}, "lights": [], "view": {}}

    for name, (color, roughness) in PALETTE.items():
        changed = set_principled(bpy.data.materials.get(name), color, roughness)
        if changed is not None:
            changes["materials"].append(changed)

    world = scene.world or bpy.data.worlds.new("Coimbra030_World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    require(bg is not None, "World Background node missing")
    bg.inputs["Color"].default_value = (0.075, 0.095, 0.13, 1.0)
    bg.inputs["Strength"].default_value = 0.55
    changes["world"] = {
        "background": [0.075, 0.095, 0.13, 1.0],
        "strength": 0.55,
    }

    for obj in scene.objects:
        if obj.type == "LIGHT" and obj.data.type == "SUN":
            changes["lights"].append({
                "name": obj.name,
                "action": "disabled-legacy-sun",
                "old_energy": float(obj.data.energy),
            })
            obj.data.energy = 0.0

    sun_data = bpy.data.lights.new("Coimbra030_Sun", "SUN")
    sun_data.energy = 2.0
    sun_data.angle = math.radians(8.0)
    sun_data.color = (1.0, 0.82, 0.64)
    sun = bpy.data.objects.new("Coimbra030_Sun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (
        math.radians(42.0),
        math.radians(-16.0),
        math.radians(-38.0),
    )
    changes["lights"].append({
        "name": sun.name,
        "action": "added",
        "type": "SUN",
        "energy": 2.0,
        "angle_deg": 8.0,
        "color": [1.0, 0.82, 0.64],
    })

    fill_data = bpy.data.lights.new("Coimbra030_Fill", "AREA")
    fill_data.energy = 900.0
    fill_data.shape = "DISK"
    fill_data.size = 85.0
    fill_data.color = (0.58, 0.72, 1.0)
    fill = bpy.data.objects.new("Coimbra030_Fill", fill_data)
    bpy.context.collection.objects.link(fill)

    camera = scene.camera
    require(camera is not None, "Production camera missing")
    scene.frame_set(181)
    target = camera.location + (camera.matrix_world.to_quaternion() @ Vector((0.0, 0.0, -1.0))) * 120.0
    fill.location = camera.location + Vector((-55.0, -25.0, 85.0))
    point_at(fill, target)
    changes["lights"].append({
        "name": fill.name,
        "action": "added",
        "type": "AREA",
        "energy": 900.0,
        "size": 85.0,
        "color": [0.58, 0.72, 1.0],
        "anchored_from_frame": 181,
    })

    view = scene.view_settings
    try:
        view.view_transform = "AgX"
    except (TypeError, ValueError):
        pass
    for look in ("AgX - Medium High Contrast", "Medium High Contrast"):
        try:
            view.look = look
            break
        except (TypeError, ValueError):
            continue
    view.exposure = 0.10
    changes["view"] = {
        "view_transform": str(view.view_transform),
        "look": str(view.look),
        "exposure": float(view.exposure),
    }
    scene.frame_set(1)
    return changes


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    prepare = json.loads(args.prepare.read_text())
    require(prepare.get("source_025_run") == 36644592881, "Unexpected 026 source baseline")
    require(full.digest_file(args.blend) == EXPECTED_BLEND_SHA256, "Accepted 026 blend checksum mismatch")

    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene = bpy.context.scene

    require(full.protected_digest(scene) == EXPECTED_PROTECTED_SHA256, "Accepted 026 protected state mismatch")
    require([scene.render.resolution_x, scene.render.resolution_y] == EXPECTED_RESOLUTION, "Resolution mismatch")

    before_structure = structure_digest(scene)
    before_cameras = full.camera_records(scene)
    source_protected = full.protected_digest(scene)

    settings = render_settings(scene)
    baseline = render_review(scene, args.out, "baseline")

    changes = apply_look(scene)
    after_structure = structure_digest(scene)
    after_cameras = full.camera_records(scene)

    require(after_structure == before_structure, "030 changed non-light structure or material assignment")
    require(after_cameras == before_cameras, "030 changed production camera path")
    require(full.protected_digest(scene) != source_protected, "030 did not change visual protected state")
    require(changes["materials"], "030 material palette matched no scene materials")
    require(len(changes["lights"]) >= 2, "030 lighting changes were not applied")

    candidate = render_review(scene, args.out, "candidate")
    for frame in map(str, REVIEW_FRAMES):
        require(
            baseline[frame]["sha256"] != candidate[frame]["sha256"],
            f"030 produced no visible image change at frame {frame}",
        )

    scene.frame_set(1)
    candidate_blend = args.out / "coimbra-production-look.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(candidate_blend))

    manifest = {
        "version": "coimbra-030-production-look-review-v1",
        "source_026_run": EXPECTED_026_RUN,
        "source_blend_sha256": EXPECTED_BLEND_SHA256,
        "source_protected_sha256": EXPECTED_PROTECTED_SHA256,
        "resolution": EXPECTED_RESOLUTION,
        "review_frames": REVIEW_FRAMES,
        "cycles": settings,
        "structure_unchanged": after_structure == before_structure,
        "camera_unchanged": after_cameras == before_cameras,
        "structure_sha256": after_structure,
        "changes": changes,
        "baseline": baseline,
        "candidate": candidate,
        "candidate_blend": {
            "path": candidate_blend.name,
            "sha256": full.digest_file(candidate_blend),
            "bytes": candidate_blend.stat().st_size,
        },
        "promotion": "review-required",
    }
    (args.out / "production-look-review.json").write_text(json.dumps(manifest, indent=2) + "
")
    print(json.dumps({
        "version": manifest["version"],
        "review_frames": REVIEW_FRAMES,
        "structure_unchanged": manifest["structure_unchanged"],
        "camera_unchanged": manifest["camera_unchanged"],
        "candidate_blend_sha256": manifest["candidate_blend"]["sha256"],
    }, indent=2))


if __name__ == "__main__":
    main()
