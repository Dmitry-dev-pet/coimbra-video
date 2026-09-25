from __future__ import annotations

import math
import os
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OBJ = ROOT / "data" / "processed" / "coimbra.obj"
OUT = ROOT / "output" / "coimbra_sharp.png"

if not OBJ.exists():
    raise SystemExit(f"Missing {OBJ}. Build the mesh first.")

# Clean scene.
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

# Import OBJ (Blender 4.x has wm.obj_import; older versions use import_scene.obj).
try:
    bpy.ops.wm.obj_import(filepath=str(OBJ))
except Exception:
    bpy.ops.import_scene.obj(filepath=str(OBJ))

mesh_obj = bpy.context.selected_objects[0]
mesh_obj.name = "Coimbra"

# Camera.
cam_data = bpy.data.cameras.new("Camera")
cam = bpy.data.objects.new("Camera", cam_data)
bpy.context.collection.objects.link(cam)
bpy.context.scene.camera = cam

# Looking roughly from south-west toward the University / old centre.
cam.location = Vector((-650.0, -1850.0, 1450.0))
target = Vector((0.0, 100.0, 90.0))
direction = target - cam.location
cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
cam_data.lens = 70
cam_data.sensor_width = 36

# First pass is kept sharp; miniature blur is applied afterwards.
cam_data.dof.use_dof = False

# Lighting.
world = bpy.context.scene.world
world.color = (0.10, 0.10, 0.10)

sun_data = bpy.data.lights.new(name="Sun", type="SUN")
sun_data.energy = 2.3
sun_data.angle = math.radians(4.0)
sun = bpy.data.objects.new(name="Sun", object_data=sun_data)
bpy.context.collection.objects.link(sun)
sun.rotation_euler = (math.radians(28), math.radians(-20), math.radians(-32))

# Render.
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(OUT)
scene.render.film_transparent = False

# Mildly photographic view transform.
scene.view_settings.look = "AgX - Medium High Contrast"

OUT.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.render.render(write_still=True)
print(f"Wrote {OUT}")
