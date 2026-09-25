from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OBJ = ROOT / "data" / "processed" / "coimbra.obj"
OUT = ROOT / "output" / "coimbra_3d_preview.mp4"

if not OBJ.exists():
    raise SystemExit(f"Missing {OBJ}. Build the mesh first.")

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

try:
    bpy.ops.wm.obj_import(filepath=str(OBJ))
except Exception:
    bpy.ops.import_scene.obj(filepath=str(OBJ))

mesh_obj = bpy.context.selected_objects[0]
mesh_obj.name = "Coimbra"

cam_data = bpy.data.cameras.new("Camera")
cam = bpy.data.objects.new("Camera", cam_data)
bpy.context.collection.objects.link(cam)
bpy.context.scene.camera = cam
cam_data.lens = 62
cam_data.sensor_width = 36

# Camera crosses the scene while continuously looking toward the old centre.
start = Vector((-900.0, -1900.0, 1250.0))
end = Vector((700.0, -1200.0, 980.0))
target_start = Vector((-120.0, 160.0, 90.0))
target_end = Vector((180.0, 260.0, 85.0))

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE_NEXT" if bpy.app.version >= (4, 0, 0) else "BLENDER_EEVEE"
scene.frame_start = 1
scene.frame_end = 96
scene.render.fps = 16
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.film_transparent = False

world = scene.world
world.color = (0.10, 0.10, 0.10)

sun_data = bpy.data.lights.new(name="Sun", type="SUN")
sun_data.energy = 2.2
sun_data.angle = math.radians(4.0)
sun = bpy.data.objects.new(name="Sun", object_data=sun_data)
bpy.context.collection.objects.link(sun)
sun.rotation_euler = (math.radians(30), math.radians(-18), math.radians(-35))

# Use real camera DOF for the moving preview. The final version can replace this
# with a custom tilted focal-plane compositor/shader.
focus_data = bpy.data.objects.new("Focus", None)
bpy.context.collection.objects.link(focus_data)
cam_data.dof.use_dof = True
cam_data.dof.focus_object = focus_data
cam_data.dof.aperture_fstop = 1.2

for frame in range(scene.frame_start, scene.frame_end + 1):
    t = (frame - scene.frame_start) / (scene.frame_end - scene.frame_start)
    s = t * t * (3.0 - 2.0 * t)
    cam.location = start.lerp(end, s)
    target = target_start.lerp(target_end, s)
    focus_data.location = target
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()

    cam.keyframe_insert(data_path="location", frame=frame)
    cam.keyframe_insert(data_path="rotation_euler", frame=frame)
    focus_data.keyframe_insert(data_path="location", frame=frame)

OUT.parent.mkdir(parents=True, exist_ok=True)
scene.render.image_settings.file_format = "FFMPEG"
scene.render.ffmpeg.format = "MPEG4"
scene.render.ffmpeg.codec = "H264"
scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
scene.render.ffmpeg.ffmpeg_preset = "GOOD"
scene.render.filepath = str(OUT)
scene.view_settings.look = (
    "AgX - Medium High Contrast"
    if bpy.app.version >= (4, 0, 0)
    else "Medium High Contrast"
)

bpy.ops.render.render(animation=True)
print(f"Wrote {OUT}")
