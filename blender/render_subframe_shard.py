from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy


SOURCE_START = 1.0
SOURCE_END = 360.0
OUTPUT_START = 1
OUTPUT_END = 1440
OUTPUT_FPS = 30


def source_time(output_frame: int) -> float:
    if not (OUTPUT_START <= output_frame <= OUTPUT_END):
        raise ValueError(output_frame)
    t = (output_frame - OUTPUT_START) / (OUTPUT_END - OUTPUT_START)
    return SOURCE_START + t * (SOURCE_END - SOURCE_START)


def main():
    args = sys.argv[sys.argv.index("--") + 1 :]
    if len(args) != 3:
        raise SystemExit(
            "usage: render_subframe_shard.py -- <start_output> <end_output> <out_dir>"
        )

    start = int(args[0])
    end = int(args[1])
    out_dir = Path(args[2]).resolve()
    if start < OUTPUT_START or end > OUTPUT_END or end < start:
        raise SystemExit(f"invalid output range: {start}..{end}")

    out_dir.mkdir(parents=True, exist_ok=True)

    scene = bpy.context.scene
    camera = scene.camera
    if camera is None or camera.type != "CAMERA":
        raise RuntimeError("production camera missing")

    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.fps = OUTPUT_FPS
    scene.render.fps_base = 1.0

    records = []
    for output_frame in range(start, end + 1):
        source = source_time(output_frame)
        base = int(math.floor(source + 1e-10))
        subframe = source - base
        if subframe >= 1.0 - 1e-9:
            base += 1
            subframe = 0.0

        scene.frame_set(base, subframe=subframe)
        path = out_dir / f"frame_{output_frame:04d}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)

        if output_frame in {start, end}:
            records.append(
                {
                    "output_frame": output_frame,
                    "source_frame": source,
                    "base_frame": base,
                    "subframe": subframe,
                    "camera_location": [float(v) for v in camera.location],
                    "camera_rotation": [float(v) for v in camera.rotation_euler],
                    "lens": float(camera.data.lens),
                    "focus_distance": float(camera.data.dof.focus_distance),
                }
            )

    manifest = {
        "version": "coimbra-smooth-subframe-shard-v1",
        "output_start": start,
        "output_end": end,
        "output_count": end - start + 1,
        "source_start": source_time(start),
        "source_end": source_time(end),
        "source_frame_step": (SOURCE_END - SOURCE_START)
        / (OUTPUT_END - OUTPUT_START),
        "sampling": "native Blender fractional-frame evaluation",
        "records": records,
    }
    (out_dir.parent / f"shard-{start:04d}-{end:04d}.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
