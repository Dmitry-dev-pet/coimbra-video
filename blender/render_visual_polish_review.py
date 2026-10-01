"""035: isolated visual-polish A/B review over the accepted Coimbra 032 camera/timing."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
import time

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))

import render_backend_comparison as backend
import render_cycles_full_route as full
import render_cycles_metal_checkpoints as metal027
import render_production_look_review as look030
import render_production_look_slow60_metal as lane032

CHECKPOINT_OUTPUT_FRAMES = [121, 421, 721, 1021, 1321]
VARIANTS = ["baseline", "motion_blur", "atmosphere_light", "quality64"]
EXPECTED_RESOLUTION = [1600, 1000]
EXPECTED_030_RUN = 36720891074
EXPECTED_026_RUN = 36646652931
EXPECTED_030_BLEND_SHA256 = "5fe8ca9e8605c6ea1908d8a814f9ad5209248c606b34ebbbb3dd47607edff881"
EXPECTED_030_STRUCTURE_SHA256 = "c3e599c7d27547527c6d6b430b7aaed8c8103c297d93c68fc66eef0c194d02da"

# 032 moves 359 native source-frame units across 1439 output intervals.
SOURCE_FRAME_STEP = (lane032.SOURCE_END - lane032.SOURCE_START) / (lane032.OUTPUT_FRAMES - 1)
# 180-degree shutter = half one 60-fps output interval in source-frame units.
MOTION_BLUR_SHUTTER = SOURCE_FRAME_STEP * 0.5

ATMOSPHERE_DENSITY = 0.00015
ATMOSPHERE_ANISOTROPY = 0.18
ATMOSPHERE_BACKGROUND_STRENGTH = 0.68
ATMOSPHERE_SUN_ENERGY = 1.65
ATMOSPHERE_SUN_ANGLE_DEG = 10.0
ATMOSPHERE_FILL_ENERGY = 900.0

QUALITY_SAMPLES = 64
QUALITY_ADAPTIVE_THRESHOLD = 0.03


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :]
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--prepare", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args(argv)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def camera_state(camera) -> dict:
    q = camera.matrix_world.to_quaternion().normalized()
    return {
        "location": [float(v) for v in camera.location],
        "quaternion": [float(q.w), float(q.x), float(q.y), float(q.z)],
        "lens": float(camera.data.lens),
        "focus_distance": float(camera.data.dof.focus_distance),
    }


def set_output_checkpoint(scene, output_frame: int) -> dict:
    source, base, subframe = lane032.source_sample(output_frame)
    scene.frame_set(base, subframe=subframe)
    bpy.context.view_layer.update()
    camera = scene.camera
    require(camera is not None, "Production camera missing")
    return {
        "output_frame": output_frame,
        "source_frame": source,
        "base_frame": base,
        "subframe": subframe,
        "camera": camera_state(camera),
    }


def world_nodes(scene):
    world = scene.world
    require(world is not None and world.use_nodes and world.node_tree is not None, "World nodes unavailable")
    output = next((n for n in world.node_tree.nodes if n.bl_idname == "ShaderNodeOutputWorld"), None)
    background = world.node_tree.nodes.get("Background")
    require(output is not None and background is not None, "World output/background missing")
    return world, output, background


def named_light(scene, name: str):
    obj = scene.objects.get(name)
    require(obj is not None and obj.type == "LIGHT", f"Missing accepted light: {name}")
    return obj


def snapshot_settings(scene) -> dict:
    world, output, background = world_nodes(scene)
    volume_socket = output.inputs.get("Volume")
    require(volume_socket is not None, "World output volume socket unavailable")
    require(not volume_socket.is_linked, "Accepted 030 world volume is already linked")

    sun = named_light(scene, "Coimbra030_Sun")
    fill = named_light(scene, "Coimbra030_Fill")
    return {
        "render_use_motion_blur": bool(scene.render.use_motion_blur),
        "render_motion_blur_shutter": float(scene.render.motion_blur_shutter),
        "render_motion_blur_position": str(scene.render.motion_blur_position),
        "samples": int(scene.cycles.samples),
        "adaptive_threshold": float(scene.cycles.adaptive_threshold),
        "use_denoising": bool(scene.cycles.use_denoising),
        "use_adaptive_sampling": bool(scene.cycles.use_adaptive_sampling),
        "background_color": list(background.inputs["Color"].default_value),
        "background_strength": float(background.inputs["Strength"].default_value),
        "sun_energy": float(sun.data.energy),
        "sun_angle": float(sun.data.angle),
        "fill_energy": float(fill.data.energy),
        "world_name": world.name,
    }


def restore_settings(scene, state: dict) -> None:
    world, output, background = world_nodes(scene)
    for node in list(world.node_tree.nodes):
        if node.name == "Coimbra035_VolumeScatter":
            world.node_tree.nodes.remove(node)

    scene.render.use_motion_blur = state["render_use_motion_blur"]
    scene.render.motion_blur_shutter = state["render_motion_blur_shutter"]
    scene.render.motion_blur_position = state["render_motion_blur_position"]

    scene.cycles.samples = state["samples"]
    scene.cycles.adaptive_threshold = state["adaptive_threshold"]
    scene.cycles.use_denoising = state["use_denoising"]
    scene.cycles.use_adaptive_sampling = state["use_adaptive_sampling"]

    background.inputs["Color"].default_value = state["background_color"]
    background.inputs["Strength"].default_value = state["background_strength"]

    sun = named_light(scene, "Coimbra030_Sun")
    fill = named_light(scene, "Coimbra030_Fill")
    sun.data.energy = state["sun_energy"]
    sun.data.angle = state["sun_angle"]
    fill.data.energy = state["fill_energy"]

    bpy.context.view_layer.update()


def apply_variant(scene, variant: str, baseline: dict) -> dict:
    restore_settings(scene, baseline)

    info = {
        "name": variant,
        "samples": int(scene.cycles.samples),
        "adaptive_threshold": float(scene.cycles.adaptive_threshold),
        "motion_blur": bool(scene.render.use_motion_blur),
        "motion_blur_shutter_source_frames": float(scene.render.motion_blur_shutter),
        "atmosphere_density": 0.0,
    }

    if variant == "baseline":
        pass
    elif variant == "motion_blur":
        scene.render.use_motion_blur = True
        scene.render.motion_blur_position = "CENTER"
        scene.render.motion_blur_shutter = MOTION_BLUR_SHUTTER
        info.update({
            "motion_blur": True,
            "motion_blur_position": "CENTER",
            "motion_blur_shutter_source_frames": MOTION_BLUR_SHUTTER,
            "motion_blur_shutter_output_frames": 0.5,
            "motion_blur_angle_degrees": 180.0,
        })
    elif variant == "atmosphere_light":
        world, output, background = world_nodes(scene)
        nodes = world.node_tree.nodes
        links = world.node_tree.links
        volume = nodes.new("ShaderNodeVolumeScatter")
        volume.name = "Coimbra035_VolumeScatter"
        volume.label = "Coimbra035 subtle aerial haze"
        volume.inputs["Density"].default_value = ATMOSPHERE_DENSITY
        volume.inputs["Anisotropy"].default_value = ATMOSPHERE_ANISOTROPY
        links.new(volume.outputs["Volume"], output.inputs["Volume"])

        background.inputs["Strength"].default_value = ATMOSPHERE_BACKGROUND_STRENGTH
        sun = named_light(scene, "Coimbra030_Sun")
        fill = named_light(scene, "Coimbra030_Fill")
        sun.data.energy = ATMOSPHERE_SUN_ENERGY
        sun.data.angle = math.radians(ATMOSPHERE_SUN_ANGLE_DEG)
        fill.data.energy = ATMOSPHERE_FILL_ENERGY
        info.update({
            "atmosphere_density": ATMOSPHERE_DENSITY,
            "atmosphere_anisotropy": ATMOSPHERE_ANISOTROPY,
            "background_strength": ATMOSPHERE_BACKGROUND_STRENGTH,
            "sun_energy": ATMOSPHERE_SUN_ENERGY,
            "sun_angle_deg": ATMOSPHERE_SUN_ANGLE_DEG,
            "fill_energy": ATMOSPHERE_FILL_ENERGY,
        })
    elif variant == "quality64":
        scene.cycles.samples = QUALITY_SAMPLES
        scene.cycles.adaptive_threshold = QUALITY_ADAPTIVE_THRESHOLD
        info.update({
            "samples": QUALITY_SAMPLES,
            "adaptive_threshold": QUALITY_ADAPTIVE_THRESHOLD,
        })
    else:
        raise ValueError(f"Unknown variant: {variant}")

    bpy.context.view_layer.update()
    return info


def render_variant(scene, variant: str, baseline: dict, out: Path) -> dict:
    variant_dir = out / variant
    variant_dir.mkdir(parents=True, exist_ok=True)
    variant_info = apply_variant(scene, variant, baseline)
    images = {}
    total = 0.0

    for output_frame in CHECKPOINT_OUTPUT_FRAMES:
        checkpoint = set_output_checkpoint(scene, output_frame)
        camera_before = checkpoint["camera"]
        path = variant_dir / f"output-{output_frame:04d}.png"
        started = time.perf_counter()
        backend.render_png(scene, path)
        elapsed = time.perf_counter() - started
        total += elapsed
        require(path.is_file() and path.stat().st_size > 0, f"Missing 035 {variant} frame {output_frame}")

        # Still rendering must not rewrite the camera's evaluated state.
        camera_after = camera_state(scene.camera)
        require(camera_before == camera_after, f"035 {variant} render changed camera state at {output_frame}")

        images[str(output_frame)] = {
            **checkpoint,
            "path": str(path.relative_to(out)),
            "sha256": full.digest_file(path),
            "bytes": path.stat().st_size,
            "seconds": elapsed,
        }
        print(f"035 {variant} output {output_frame}: {elapsed:.3f}s")

    return {
        "settings": variant_info,
        "total_seconds": total,
        "images": images,
    }


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    review = json.loads(args.review.read_text())
    prepare = json.loads(args.prepare.read_text())

    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene = bpy.context.scene
    lane032.verify_source(scene, args.blend, review, prepare)

    before_protected = full.protected_digest(scene)
    before_structure = look030.structure_digest(scene)
    before_cameras = full.camera_records(scene)

    cpu_settings = metal027.accepted_cpu_settings(scene)
    metal_settings = metal027.configure_metal(scene, cpu_settings)
    require(metal_settings["metal_devices"], "035 requires Apple Metal")

    scene.render.resolution_x = EXPECTED_RESOLUTION[0]
    scene.render.resolution_y = EXPECTED_RESOLUTION[1]
    scene.render.resolution_percentage = 100

    baseline_settings = snapshot_settings(scene)
    require(baseline_settings["samples"] == 16, "035 baseline samples changed")
    require(math.isclose(baseline_settings["adaptive_threshold"], 0.08, abs_tol=1e-6), "035 baseline adaptive threshold changed")
    require(baseline_settings["render_use_motion_blur"] is False, "035 accepted baseline unexpectedly has motion blur")

    checkpoint_evidence = {
        str(output_frame): set_output_checkpoint(scene, output_frame)
        for output_frame in CHECKPOINT_OUTPUT_FRAMES
    }

    variants = {}
    try:
        for variant in VARIANTS:
            variants[variant] = render_variant(scene, variant, baseline_settings, args.out)
    finally:
        restore_settings(scene, baseline_settings)

    scene.frame_set(1)
    bpy.context.view_layer.update()
    require(full.protected_digest(scene) == before_protected, "035 review failed to restore accepted visual state")
    require(look030.structure_digest(scene) == before_structure, "035 review changed scene structure")
    require(full.camera_records(scene) == before_cameras, "035 review changed accepted camera path")

    baseline_images = variants["baseline"]["images"]
    for variant in ("motion_blur", "atmosphere_light", "quality64"):
        changed = sum(
            variants[variant]["images"][key]["sha256"] != baseline_images[key]["sha256"]
            for key in baseline_images
        )
        require(changed >= 4, f"035 {variant} produced too few visible image changes: {changed}/5")

    receipt = {
        "version": "coimbra-035-visual-polish-review-v1",
        "source_030_run": EXPECTED_030_RUN,
        "source_026_run": EXPECTED_026_RUN,
        "source_030_blend_sha256": EXPECTED_030_BLEND_SHA256,
        "source_030_structure_sha256": EXPECTED_030_STRUCTURE_SHA256,
        "source_code_commit": os.environ.get("COIMBRA_SOURCE_SHA", "local"),
        "accepted_lane": "Coimbra 032",
        "camera_timing_policy": "unchanged accepted 032 fractional-frame route",
        "output_fps_reference": lane032.OUTPUT_FPS,
        "output_duration_reference_seconds": lane032.OUTPUT_FRAMES / lane032.OUTPUT_FPS,
        "checkpoint_output_frames": CHECKPOINT_OUTPUT_FRAMES,
        "checkpoint_evidence": checkpoint_evidence,
        "resolution": EXPECTED_RESOLUTION,
        "baseline_cycles": cpu_settings,
        "metal": metal_settings,
        "baseline_settings": baseline_settings,
        "motion_blur_mapping": {
            "source_frame_step": SOURCE_FRAME_STEP,
            "shutter_source_frames": MOTION_BLUR_SHUTTER,
            "shutter_output_frames": 0.5,
            "shutter_angle_degrees": 180.0,
        },
        "variants": variants,
        "scene_restored": True,
        "structure_unchanged": True,
        "camera_unchanged": True,
        "promotion": "human-review-required",
    }
    (args.out / "visual-polish-review.json").write_text(
        json.dumps(receipt, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps({
        "checkpoints": CHECKPOINT_OUTPUT_FRAMES,
        "variants": {
            name: {
                "total_seconds": data["total_seconds"],
                "settings": data["settings"],
            }
            for name, data in variants.items()
        },
        "motion_blur_shutter_source_frames": MOTION_BLUR_SHUTTER,
        "scene_restored": True,
    }, indent=2))


if __name__ == "__main__":
    main()
