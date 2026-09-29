"""026: render the frozen 025 scene at native frames, without scene edits."""
from __future__ import annotations

import argparse
from array import array
import hashlib
import json
import math
import os
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))
import render_backend_comparison as backend
import render_cycles_route_baseline as baseline

OUT = ROOT / "bridge_output_026"
SOURCE_COMMIT = "d178382d10eef41ec00da3fe562fcc445438f8da"
FPS, FRAMES = 30, 360


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest_file(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def node_state(tree):
    if tree is None:
        return None
    nodes = []
    for node in sorted(tree.nodes, key=lambda n: n.name):
        settings = {}
        for prop in node.bl_rna.properties:
            key = prop.identifier
            if prop.type not in {"BOOLEAN", "INT", "FLOAT", "STRING", "ENUM"}:
                continue
            if key in {"select", "dimensions", "width", "width_hidden", "height", "location"}:
                continue
            value = getattr(node, key)
            settings[key] = (list(value) if getattr(prop, "is_array", False) else
                             sorted(value) if isinstance(value, set) else value)
        inputs = []
        for socket in node.inputs:
            if hasattr(socket, "default_value"):
                value = socket.default_value
                if isinstance(value, bpy.types.ID):
                    value = value.name
                elif value is not None and not isinstance(value, (int, float, bool, str)):
                    value = list(value)
                inputs.append([socket.identifier, value])
        image = getattr(node, "image", None)
        group = getattr(node, "node_tree", None)
        nodes.append([node.name, node.bl_idname, settings, inputs,
                      image.name if image else None, group.name if group else None])
    links = sorted([link.from_node.name, link.from_socket.identifier,
                    link.to_node.name, link.to_socket.identifier] for link in tree.links)
    return {"nodes": nodes, "links": links}


def protected_digest(scene):
    """Independent render guard: geometry, material graphs, world, lights, poses."""
    scene.frame_set(1)
    bpy.context.view_layer.update()
    h = hashlib.sha256()
    for obj in sorted(scene.objects, key=lambda o: o.name):
        state = [obj.name, obj.type, [list(row) for row in obj.matrix_world],
                 obj.hide_render, [slot.material.name if slot.material else None
                                   for slot in obj.material_slots]]
        h.update(canonical(state).encode())
        if obj.type == "MESH":
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
        elif obj.type == "LIGHT":
            h.update(canonical([obj.data.type, list(obj.data.color), obj.data.energy]).encode())
    for mat in sorted(bpy.data.materials, key=lambda m: m.name):
        h.update(canonical([mat.name, list(mat.diffuse_color), mat.roughness,
                            mat.metallic, mat.use_nodes, node_state(mat.node_tree)]).encode())
    for tree in sorted(bpy.data.node_groups, key=lambda t: t.name):
        h.update(canonical([tree.name, node_state(tree)]).encode())
    world = scene.world
    h.update(canonical([world.name, list(world.color), node_state(world.node_tree)]
                       if world else None).encode())
    return h.hexdigest()


def camera_records(scene):
    if scene.camera is None:
        raise RuntimeError("Missing production camera")
    records = []
    for frame in range(1, FRAMES + 1):
        scene.frame_set(frame)
        record = baseline.camera_record(scene.camera, frame)
        record["matrix_world"] = [list(row) for row in scene.camera.matrix_world]
        records.append(record)
    scene.frame_set(1)
    return records


def check_cycles(scene):
    _, settings = baseline.configure_cycles(scene)
    expected = {"device": "CPU", "samples": 16, "use_denoising": True,
                "use_adaptive_sampling": True, "adaptive_threshold": 0.08,
                "max_bounces": 6, "diffuse_bounces": 3,
                "glossy_bounces": 3, "transmission_bounces": 2}
    for key, value in expected.items():
        actual = settings.get(key)
        if isinstance(value, float):
            valid = isinstance(actual, (float, int)) and math.isclose(actual, value, abs_tol=1e-6)
        else:
            valid = actual == value
        if not valid:
            raise RuntimeError(f"Cycles setting not applied: {key}: {actual!r}")
    return settings


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    accepted = json.loads((ROOT / "baseline_025/cycles-route-baseline.json").read_text())
    scene, geometry = backend.build_scene()
    if canonical(geometry) != canonical(accepted["geometry"]):
        raise RuntimeError("Rebuilt semantic geometry differs from the accepted 025 manifest")
    cameras = camera_records(scene)
    for pair in accepted["renders"]:
        actual = cameras[pair["frame"] - 1]
        for key, expected in pair["camera"].items():
            values = zip(actual[key], expected) if isinstance(expected, list) else [(actual[key], expected)]
            if any(not math.isclose(a, b, abs_tol=1e-5) for a, b in values):
                raise RuntimeError(f"025 camera mismatch: frame {pair['frame']} / {key}")
    before = protected_digest(scene)
    settings = check_cycles(scene)
    scene.render.resolution_x, scene.render.resolution_y = accepted["resolution"]
    scene.render.resolution_percentage = 100
    if [scene.render.resolution_x, scene.render.resolution_y] != [backend.WIDTH, backend.HEIGHT]:
        raise RuntimeError("025 resolution contract mismatch")
    if scene.render.fps / scene.render.fps_base != FPS or scene.frame_start != 1 or scene.frame_end != FRAMES:
        raise RuntimeError("Inherited scene is not the native 360-frame, 30-fps route")
    if protected_digest(scene) != before or camera_records(scene) != cameras:
        raise RuntimeError("Render configuration changed protected scene/camera state")
    scene.frame_set(1)
    blend = OUT / "coimbra-cycles-full-route.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    manifest = {
        "version": "coimbra-cycles-full-route-prepare-v1",
        "source_025_commit": SOURCE_COMMIT, "source_025_run": 36644592881,
        "source_commit": os.environ.get("GITHUB_SHA", "local"),
        "geometry": geometry, "geometry_matches_025": True,
        "protected_sha256": before, "cameras": cameras,
        "blend_sha256": digest_file(blend), "cycles": settings,
        "frame_count": FRAMES, "fps": FPS, "duration_seconds": FRAMES / FPS,
        "resolution": accepted["resolution"], "sampling": "native integer frames 1..360",
        "input_sha256": {str(p.relative_to(ROOT)): digest_file(p)
                         for p in [backend.SOURCE, backend.SEMANTIC, backend.OBJECTS, backend.TERRAIN]},
    }
    write_json(OUT / "prepare.json", manifest)
    print("026 frozen scene verified against 025; 360 native frames at 30 fps")


def render(start, end):
    if not 1 <= start <= end <= FRAMES:
        raise ValueError(f"Invalid shard range: {start}..{end}")
    manifest = json.loads((OUT / "prepare.json").read_text())
    blend = OUT / "coimbra-cycles-full-route.blend"
    if digest_file(blend) != manifest["blend_sha256"]:
        raise RuntimeError("Prepared Blender artifact checksum mismatch")
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    scene = bpy.context.scene
    if protected_digest(scene) != manifest["protected_sha256"] or camera_records(scene) != manifest["cameras"]:
        raise RuntimeError("Loaded scene/camera differs from the frozen baseline")
    settings = check_cycles(scene)
    frames = OUT / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for frame in range(start, end + 1):
        scene.frame_set(frame)
        path = frames / f"frame_{frame:04d}.png"
        backend.render_png(scene, path)
        hashes[str(frame)] = digest_file(path)
    if protected_digest(scene) != manifest["protected_sha256"] or camera_records(scene) != manifest["cameras"]:
        raise RuntimeError("Rendering mutated protected scene/camera state")
    write_json(OUT / f"shard-{start:04d}-{end:04d}.json", {
        "start": start, "end": end, "frames": hashes,
        "protected_sha256": manifest["protected_sha256"],
        "blend_sha256": manifest["blend_sha256"], "cycles": settings,
        "camera_unchanged": True, "geometry_material_world_unchanged": True,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["prepare", "render"])
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=FRAMES)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    prepare() if args.mode == "prepare" else render(args.start, args.end)
