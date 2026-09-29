from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
BLENDER_DIR = ROOT / "blender"
if str(BLENDER_DIR) not in sys.path:
    sys.path.insert(0, str(BLENDER_DIR))

import build_photo_patch as patch  # type: ignore
import enhance_hero_buildings as hero  # type: ignore
import enhance_hero_realism as realism  # type: ignore


SOURCE = ROOT / "bridge_output_010" / "coimbra-urban-quality.blend"
OSM_LOCAL = ROOT / "data" / "processed" / "bridge_osm_oss_local.json"
TERRAIN = ROOT / "bridge_output_008b" / "bridge_terrain_highres_2m.npz"
OUT = ROOT / "bridge_output_016b"
BLEND = OUT / "coimbra-full-render-new-geometry.blend"
MANIFEST = OUT / "full-render-new-geometry-manifest.json"

EXPECTED_HERO_IDS = {143294113, 143294117, 143294126, 379862984}
WIDTH = 1280
HEIGHT = 720
FPS = 30
FRAME_START = 1
FRAME_END = 360


def camera_signature(scene, camera):
    original = scene.frame_current
    checkpoints = []
    for frame in (1, 61, 121, 181, 241, 301, 360):
        scene.frame_set(frame)
        checkpoints.append(
            {
                "frame": frame,
                "location": [round(float(v), 6) for v in camera.location],
                "rotation": [round(float(v), 7) for v in camera.rotation_euler],
                "lens": round(float(camera.data.lens), 6),
                "fstop": round(float(camera.data.dof.aperture_fstop), 6),
                "focus_distance": round(float(camera.data.dof.focus_distance), 6),
            }
        )
    scene.frame_set(original)
    payload = json.dumps(checkpoints, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def reset_window_stats():
    for key in realism.WINDOW_STATS:
        realism.WINDOW_STATS[key] = 0


def main():
    for required in (SOURCE, OSM_LOCAL, TERRAIN):
        if not required.is_file():
            raise SystemExit(f"Missing input: {required}")

    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    scene = bpy.context.scene
    production_camera = scene.camera
    if production_camera is None or production_camera.type != "CAMERA":
        raise RuntimeError("production camera missing from Coimbra 010")

    camera_hash_before = camera_signature(scene, production_camera)

    source = json.loads(OSM_LOCAL.read_text())
    terrain = hero.TerrainSampler(TERRAIN)

    # Recreate the accepted 011 Polo II still camera only as a temporary
    # reference for deterministic hero-building selection, facade orientation,
    # window omission and balcony placement. It is deleted before save.
    reference_camera_info = patch.add_camera(
        scene,
        terrain,
        source["nodes"],
        source["ways"],
    )
    reference_camera = scene.camera
    if reference_camera is None:
        raise RuntimeError("temporary Polo II reference camera was not created")

    selected = hero.select_hero_buildings(scene, source, terrain)
    selected_ids = {int(item["way_id"]) for item in selected}
    if selected_ids != EXPECTED_HERO_IDS:
        raise RuntimeError(
            "Polo II hero selection drifted: "
            f"expected={sorted(EXPECTED_HERO_IDS)} actual={sorted(selected_ids)}"
        )

    removed_roofs = hero.delete_existing_roof_faces(selected)
    removed_details = hero.delete_existing_detail_faces(selected)

    reset_window_stats()
    hero.add_window = realism.realistic_add_window
    hero_obj, buildings = hero.build_hero_geometry(selected, scene)
    realism_obj, realism_stats = realism.build_realism_overlay(selected, scene)

    # The full render keeps the production 010 lighting/environment. Only the
    # localized 012b/013 building geometry is integrated.
    bpy.data.objects.remove(reference_camera, do_unlink=True)
    scene.camera = production_camera

    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.render.fps = FPS
    scene.render.fps_base = 1.0
    scene.render.resolution_x = WIDTH
    scene.render.resolution_y = HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"

    camera_hash_after = camera_signature(scene, production_camera)
    if camera_hash_after != camera_hash_before:
        raise RuntimeError(
            "production camera changed while integrating Polo II geometry"
        )

    tile_violations = [
        building["way_id"]
        for building in buildings
        if building["roof_built"] == "flat" and building["uses_tile_material"]
    ]
    if tile_violations:
        raise RuntimeError(f"flat hero roofs use tile: {tile_violations}")

    scene["full_render_version"] = "coimbra-full-render-new-geometry-v1"
    scene["polo2_hero_geometry_version"] = "012b+013"
    scene["polo2_hero_building_count"] = len(buildings)

    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))

    manifest = {
        "version": "coimbra-full-render-new-geometry-v1",
        "source_scene": SOURCE.relative_to(ROOT).as_posix(),
        "output_scene": BLEND.relative_to(ROOT).as_posix(),
        "resolution": [WIDTH, HEIGHT],
        "fps": FPS,
        "frame_start": FRAME_START,
        "frame_end": FRAME_END,
        "frame_count": FRAME_END - FRAME_START + 1,
        "duration_seconds": (FRAME_END - FRAME_START + 1) / FPS,
        "production_camera_hash_before": camera_hash_before,
        "production_camera_hash_after": camera_hash_after,
        "production_camera_unchanged": camera_hash_before == camera_hash_after,
        "reference_camera": reference_camera_info,
        "polo2_patch": {
            "hero_ids": sorted(selected_ids),
            "hero_buildings": buildings,
            "window_stats": dict(realism.WINDOW_STATS),
            "realism": realism_stats,
            "removed_old_roof_faces": removed_roofs,
            "removed_old_detail_faces": removed_details,
            "hero_geometry": {
                "vertices": len(hero_obj.data.vertices),
                "faces": len(hero_obj.data.polygons),
            },
            "realism_geometry": {
                "vertices": len(realism_obj.data.vertices),
                "faces": len(realism_obj.data.polygons),
            },
            "flat_tile_violations": tile_violations,
        },
        "scope": {
            "full_city_base": "Coimbra 010 Urban Quality",
            "localized_new_geometry": "Polo II 012b + 013 only",
            "photo_specific_014_lighting_not_applied": True,
            "photo_specific_015_grade_not_applied": True,
        },
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
