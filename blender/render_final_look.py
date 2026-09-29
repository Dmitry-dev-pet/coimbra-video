from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
BLENDER_DIR = ROOT / "blender"
if str(BLENDER_DIR) not in sys.path:
    sys.path.insert(0, str(BLENDER_DIR))

import enhance_environment_realism as environment  # type: ignore


OUT = ROOT / "bridge_output_015"
MASTER = OUT / "final-look-master-3200x2000.png"
MANIFEST = OUT / "final-look-render-manifest.json"


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    # Build 012b -> 013 -> 014 in memory, but suppress all intermediate review
    # renders. 015 changes no scene geometry; it only renders the chosen 55 mm
    # composition at 2x target resolution.
    environment.render = lambda *args, **kwargs: None
    environment.main()

    scene = bpy.context.scene
    source_camera = scene.camera
    if source_camera is None:
        raise RuntimeError("014 source camera missing")

    final_camera = environment.realism.clone_camera(
        source_camera,
        "FinalLook_55mm",
        lens=55.0,
        z_delta=-4.0,
        target_delta_z=-1.5,
    )

    scene.camera = final_camera
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 3200
    scene.render.resolution_y = 2000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.render.filepath = str(MASTER)

    # Keep Blender color management exactly as inherited from the accepted
    # scene. The three final grades are applied later to this single master.
    color_management = {
        "view_transform": scene.view_settings.view_transform,
        "look": scene.view_settings.look,
        "exposure": float(scene.view_settings.exposure),
        "gamma": float(scene.view_settings.gamma),
    }

    bpy.ops.render.render(write_still=True)

    camera_record = {
        "location": [float(value) for value in final_camera.location],
        "rotation_euler": [float(value) for value in final_camera.rotation_euler],
        "lens": float(final_camera.data.lens),
        "sensor_width": float(final_camera.data.sensor_width),
        "fstop": float(final_camera.data.dof.aperture_fstop),
        "focus_distance": float(final_camera.data.dof.focus_distance),
    }

    manifest = {
        "version": "coimbra-final-look-v1",
        "base_pass": "coimbra-environment-realism-v1",
        "master": MASTER.relative_to(ROOT).as_posix(),
        "master_resolution": [3200, 2000],
        "target_resolution": [1600, 1000],
        "oversample_factor": 2.0,
        "camera": camera_record,
        "color_management": color_management,
        "scene_changes": {
            "geometry": False,
            "materials": False,
            "lighting": False,
            "camera_only_for_render": True,
        },
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
