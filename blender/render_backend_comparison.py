from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
BLENDER_DIR = ROOT / "blender"
if str(BLENDER_DIR) not in sys.path:
    sys.path.insert(0, str(BLENDER_DIR))

import build_semantic_objects as semantic  # type: ignore
import build_semantic_details as details  # type: ignore
import enhance_hero_buildings as hero  # type: ignore

SOURCE = ROOT / "bridge_output_019" / "coimbra-full-route-pitched-roofs.blend"
SEMANTIC = ROOT / "data" / "processed" / "bridge_semantic_details_2025.json"
OBJECTS = ROOT / "data" / "processed" / "bridge_semantic_objects_2025.json"
TERRAIN = ROOT / "bridge_output_008b" / "bridge_terrain_highres_2m.npz"
OUT = ROOT / "bridge_output_024"
MANIFEST = OUT / "render-backend-comparison.json"

WIDTH = 1600
HEIGHT = 1000


def set_engine(scene, candidates):
    errors = []
    for candidate in candidates:
        try:
            scene.render.engine = candidate
            return candidate
        except (TypeError, ValueError) as exc:
            errors.append(f"{candidate}: {exc}")
    raise RuntimeError("No supported render engine: " + " | ".join(errors))


def set_if_attr(obj, name, value):
    if obj is None or not hasattr(obj, name):
        return None
    setattr(obj, name, value)
    return getattr(obj, name)


def scene_eevee(scene):
    return getattr(scene, "eevee", None)


def render_png(scene, path):
    scene.render.resolution_x = WIDTH
    scene.render.resolution_y = HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    if not path.is_file():
        raise RuntimeError(f"Render missing: {path}")


def build_scene():
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
    semantic_data = json.loads(SEMANTIC.read_text())
    object_data = json.loads(OBJECTS.read_text())

    semantic.remove_old_solar()

    hardscape = list(object_data.get("parking") or []) + list(object_data.get("pitches") or [])
    filtered_trees = [
        item for item in (semantic_data.get("trees") or [])
        if not semantic.point_in_any(item["x"], item["y"], hardscape)
    ]
    filtered_masses = [
        item for item in (semantic_data.get("canopy_masses") or [])
        if not semantic.point_in_any(item["x"], item["y"], hardscape)
    ]
    filtered_under = [
        item for item in (semantic_data.get("undergrowth") or [])
        if not semantic.point_in_any(item["x"], item["y"], hardscape)
    ]

    _ground_obj, parking, pitches = semantic.build_ground_objects(
        object_data.get("parking") or [],
        object_data.get("pitches") or [],
        terrain,
    )
    _solar_obj, solar, solar_rejections = semantic.build_solar(
        scene,
        object_data.get("solar") or [],
        object_data.get("osm_solar") or [],
    )

    details.remove_old_tree_layer()
    _tree_obj, trees = details.build_semantic_trees(filtered_trees, terrain)
    _mass_obj, masses = details.build_canopy_masses(filtered_masses, terrain)
    _under_obj, undergrowth = details.build_undergrowth(filtered_under, terrain)
    _pool_obj, pools = details.build_pools(semantic_data.get("pools") or [], terrain)

    review = semantic.choose_frame(scene, camera, solar, parking, pitches, undergrowth)
    scene.frame_set(review["frame"])
    scene.camera = camera

    return scene, {
        "review": review,
        "trees": len(trees),
        "canopy_masses": len(masses),
        "undergrowth": len(undergrowth),
        "pools": len(pools),
        "solar_arrays": len(solar),
        "solar_rejections": solar_rejections,
        "parking": len(parking),
        "sports": len(pitches),
    }


def main():
    scene, geometry = build_scene()
    results = {
        "version": "coimbra-render-backend-comparison-v1",
        "source_branch": "feature/coimbra-023-semantic-objects",
        "geometry": geometry,
        "renders": {},
    }

    # A: exact current 023 render path. Do not tune the inherited EEVEE state.
    engine_a = set_engine(scene, ["BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"])
    current_path = OUT / "A-eevee-current.png"
    render_png(scene, current_path)
    results["renders"]["A"] = {
        "label": "EEVEE current 023",
        "engine": engine_a,
        "path": current_path.relative_to(ROOT).as_posix(),
    }

    # B: same geometry/frame, but raise final-render sampling and shadow quality.
    engine_b = set_engine(scene, ["BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"])
    eevee = scene_eevee(scene)
    tuned = {}
    for key, value in (
        ("taa_render_samples", 256),
        ("shadow_ray_count", 4),
        ("shadow_step_count", 16),
        ("shadow_resolution_scale", 1.0),
        ("use_overscan", True),
    ):
        applied = set_if_attr(eevee, key, value)
        if applied is not None:
            tuned[key] = applied

    tuned_path = OUT / "B-eevee-quality.png"
    render_png(scene, tuned_path)
    results["renders"]["B"] = {
        "label": "EEVEE quality",
        "engine": engine_b,
        "settings": tuned,
        "path": tuned_path.relative_to(ROOT).as_posix(),
    }

    # C: same geometry/frame through Cycles CPU with low samples + denoise.
    # This is diagnostic, not a final production-quality Cycles target.
    engine_c = set_engine(scene, ["CYCLES", "BLENDER_CYCLES"])
    cycles = getattr(scene, "cycles", None)
    cycle_settings = {}
    for key, value in (
        ("device", "CPU"),
        ("samples", 16),
        ("use_denoising", True),
        ("use_adaptive_sampling", True),
        ("adaptive_threshold", 0.08),
        ("max_bounces", 6),
        ("diffuse_bounces", 3),
        ("glossy_bounces", 3),
        ("transmission_bounces", 2),
    ):
        try:
            applied = set_if_attr(cycles, key, value)
        except (TypeError, ValueError):
            applied = None
        if applied is not None:
            cycle_settings[key] = applied

    cycles_path = OUT / "C-cycles-denoised.png"
    render_png(scene, cycles_path)
    results["renders"]["C"] = {
        "label": "Cycles 16 samples + denoise",
        "engine": engine_c,
        "settings": cycle_settings,
        "path": cycles_path.relative_to(ROOT).as_posix(),
    }

    MANIFEST.write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
