from __future__ import annotations

import json
from pathlib import Path

import bpy
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "bridge_output_008a" / "coimbra-car-reality-visual-dev.blend"
OLD_TERRAIN = ROOT / "data" / "processed" / "bridge_terrain_6m.npz"
NEW_TERRAIN = ROOT / "bridge_output_008b" / "bridge_terrain_highres_2m.npz"
HAG = ROOT / "bridge_output_008b" / "bridge_height_above_ground_1m.npz"
HIGHRES_META = ROOT / "bridge_output_008b" / "highres-geodata-manifest.json"

OUT_DIR = ROOT / "bridge_output_008c"
OUT_BLEND = OUT_DIR / "coimbra-highres-terrain-base.blend"
MANIFEST = OUT_DIR / "highres-terrain-manifest.json"

VERSION = "coimbra-highres-terrain-v1"
SHIFT_PREFIXES = (
    "City_Buildings",
    "City_Roads_",
    "Facade_",
    "Vegetation_",
    "Detail_",
)


class GridSampler:
    def __init__(self, path: Path, value_key: str):
        data = np.load(path)
        self.values = data[value_key].astype(np.float32)
        self.xs = data["xs"].astype(np.float32)
        self.ys = data["ys"].astype(np.float32)
        self.z0 = float(data["z0"]) if "z0" in data.files else 0.0

    def sample_absolute(self, x: float, y: float) -> float | None:
        if x < float(self.xs[0]) or x > float(self.xs[-1]):
            return None
        y_max = float(self.ys[0])
        y_min = float(self.ys[-1])
        if y > y_max or y < y_min:
            return None

        fx = (x - float(self.xs[0])) / (float(self.xs[-1]) - float(self.xs[0])) * (len(self.xs) - 1)
        fy = (y_max - y) / (y_max - y_min) * (len(self.ys) - 1)

        x0 = int(np.floor(fx))
        y0 = int(np.floor(fy))
        x1 = min(x0 + 1, len(self.xs) - 1)
        y1 = min(y0 + 1, len(self.ys) - 1)
        tx = fx - x0
        ty = fy - y0

        a = float(self.values[y0, x0])
        b = float(self.values[y0, x1])
        c = float(self.values[y1, x0])
        d = float(self.values[y1, x1])
        top = a * (1.0 - tx) + b * tx
        bottom = c * (1.0 - tx) + d * tx
        return top * (1.0 - ty) + bottom * ty

    def sample_local(self, x: float, y: float) -> float | None:
        value = self.sample_absolute(x, y)
        return None if value is None else value - self.z0


def build_highres_terrain(obj, new_data):
    z = new_data["z"].astype(np.float32)
    xs = new_data["xs"].astype(np.float32)
    ys = new_data["ys"].astype(np.float32)
    z0 = float(new_data["z0"])
    rows, cols = z.shape

    vertices = [
        (float(xs[c]), float(ys[r]), float(z[r, c] - z0))
        for r in range(rows)
        for c in range(cols)
    ]
    faces = [
        (
            r * cols + c,
            (r + 1) * cols + c,
            (r + 1) * cols + c + 1,
            r * cols + c + 1,
        )
        for r in range(rows - 1)
        for c in range(cols - 1)
    ]

    old_mesh = obj.data
    materials = list(old_mesh.materials)

    mesh = bpy.data.meshes.new("City_Terrain_Highres_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()

    uv = mesh.uv_layers.new(name="UVMap")
    loop_vertex_indices = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", loop_vertex_indices)
    rr = loop_vertex_indices // cols
    cc = loop_vertex_indices % cols
    uvs = np.empty((len(mesh.loops), 2), dtype=np.float32)
    uvs[:, 0] = cc / float(cols - 1)
    uvs[:, 1] = 1.0 - rr / float(rows - 1)
    uv.data.foreach_set("uv", uvs.reshape(-1))

    obj.data = mesh
    for material in materials:
        obj.data.materials.append(material)

    obj["source"] = "DGT MDT-50cm (2m render grid)"
    obj["terrain_source_resolution_m"] = 0.5
    obj["terrain_resolution_m"] = 2.0
    obj["terrain_vertex_count"] = len(vertices)
    obj["terrain_face_count"] = len(faces)

    if old_mesh.users == 0:
        bpy.data.meshes.remove(old_mesh)

    return {
        "shape": [rows, cols],
        "vertices": len(vertices),
        "faces": len(faces),
        "z0": z0,
    }


def should_shift(obj) -> bool:
    if obj.name == "City_Terrain":
        return False
    return any(
        obj.name == prefix or obj.name.startswith(prefix)
        for prefix in SHIFT_PREFIXES
    )


def shift_scene_geometry(old_sampler: GridSampler, new_sampler: GridSampler):
    stats = {}
    global_deltas = []

    for obj in bpy.data.objects:
        if not should_shift(obj) or obj.type != "MESH":
            continue

        mesh = obj.data
        deltas = []
        skipped = 0

        # Generated Coimbra scene objects use identity transforms, but compute
        # in object-local XY only after explicitly checking that assumption.
        if (
            abs(obj.location.x) > 1e-6
            or abs(obj.location.y) > 1e-6
            or abs(obj.location.z) > 1e-6
            or any(abs(value) > 1e-6 for value in obj.rotation_euler)
            or any(abs(value - 1.0) > 1e-6 for value in obj.scale)
        ):
            raise RuntimeError(f"Expected identity transform for shiftable object: {obj.name}")

        for vertex in mesh.vertices:
            old_z = old_sampler.sample_local(float(vertex.co.x), float(vertex.co.y))
            new_z = new_sampler.sample_local(float(vertex.co.x), float(vertex.co.y))
            if old_z is None or new_z is None:
                skipped += 1
                continue

            delta = float(new_z - old_z)
            # Same bare-earth source family should stay close. Large values
            # usually indicate an edge/nodata mismatch and must not move assets.
            if abs(delta) > 5.0:
                skipped += 1
                continue

            vertex.co.z += delta
            deltas.append(delta)
            global_deltas.append(delta)

        mesh.update()
        if deltas:
            stats[obj.name] = {
                "vertices_shifted": len(deltas),
                "vertices_skipped": skipped,
                "delta_min_m": min(deltas),
                "delta_max_m": max(deltas),
                "delta_mean_m": sum(deltas) / len(deltas),
            }
        else:
            stats[obj.name] = {
                "vertices_shifted": 0,
                "vertices_skipped": skipped,
            }

    if not global_deltas:
        raise RuntimeError("No scene geometry was shifted to high-resolution terrain")

    return stats, {
        "count": len(global_deltas),
        "min_m": min(global_deltas),
        "max_m": max(global_deltas),
        "mean_m": sum(global_deltas) / len(global_deltas),
    }


def hag_summary(path: Path):
    data = np.load(path)
    height = data["height"].astype(np.float32)
    positive = height[height > 0.5]
    return {
        "shape": list(height.shape),
        "resolution_m": float(data["height_resolution"]),
        "max_m": float(np.max(height)),
        "positive_fraction": float(np.mean(height > 0.5)),
        "positive_p50_m": float(np.percentile(positive, 50)) if positive.size else 0.0,
        "positive_p90_m": float(np.percentile(positive, 90)) if positive.size else 0.0,
        "positive_p99_m": float(np.percentile(positive, 99)) if positive.size else 0.0,
    }


def main() -> None:
    for required in (BASE, OLD_TERRAIN, NEW_TERRAIN, HAG, HIGHRES_META):
        if not required.is_file():
            raise SystemExit(f"Missing input: {required}")

    bpy.ops.wm.open_mainfile(filepath=str(BASE))

    old_sampler = GridSampler(OLD_TERRAIN, "z")
    new_sampler = GridSampler(NEW_TERRAIN, "z")
    new_data = np.load(NEW_TERRAIN)

    terrain_obj = bpy.data.objects.get("City_Terrain")
    if terrain_obj is None or terrain_obj.type != "MESH":
        raise RuntimeError("City_Terrain mesh not found")

    shift_stats, global_delta = shift_scene_geometry(old_sampler, new_sampler)
    terrain_stats = build_highres_terrain(terrain_obj, new_data)
    hag_stats = hag_summary(HAG)
    highres_meta = json.loads(HIGHRES_META.read_text())

    scene = bpy.context.scene
    scene["city_terrain_source"] = "DGT MDT-50cm"
    scene["city_geometry_version"] = "osm-dgt-mdt50cm-terrain-v1"
    scene["city_highres_source_resolution_m"] = 0.5
    scene["city_highres_render_resolution_m"] = 2.0
    scene["city_height_above_ground_resolution_m"] = 1.0
    scene["city_highres_version"] = VERSION

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))

    result = {
        "version": VERSION,
        "output_scene": OUT_BLEND.relative_to(ROOT).as_posix(),
        "source": {
            "collections": highres_meta["collections"],
            "source_resolution_m": highres_meta["source_resolution_m"],
            "terrain_resolution_m": highres_meta["render_terrain_resolution_m"],
            "height_above_ground_resolution_m": highres_meta["height_above_ground_resolution_m"],
        },
        "terrain": terrain_stats,
        "vertical_reprojection": {
            "global": global_delta,
            "objects": shift_stats,
        },
        "height_above_ground": hag_stats,
    }
    MANIFEST.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
