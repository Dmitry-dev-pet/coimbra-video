"""033: render a motion-only proxy with a smoothed camera over the accepted 030 look."""
from __future__ import annotations

import argparse
import bisect
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender"))

import render_cycles_full_route as full
import render_production_look_review as look030
import render_production_look_metal_full_route as lane031

OUTPUT_FRAMES = 1440
OUTPUT_FPS = 60
PROXY_RESOLUTION = [960, 600]
ANCHOR_SOURCE_FRAMES = [1, 61, 121, 181, 241, 301, 360]
SOURCE_START = 1.0
SOURCE_END = 360.0
LOOK_DISTANCE = 300.0
DENSE_PER_SEGMENT = 2000


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


def source_time(output_frame: int) -> float:
    require(1 <= output_frame <= OUTPUT_FRAMES, "output frame outside 1..1440")
    t = (output_frame - 1) / (OUTPUT_FRAMES - 1)
    return SOURCE_START + t * (SOURCE_END - SOURCE_START)


def set_source_frame(scene, source: float) -> None:
    base = int(math.floor(source + 1e-10))
    subframe = source - base
    if subframe >= 1.0 - 1e-9:
        base += 1
        subframe = 0.0
    scene.frame_set(base, subframe=subframe)
    bpy.context.view_layer.update()


def quaternion_list(camera) -> list[float]:
    q = camera.matrix_world.to_quaternion().normalized()
    return [float(q.w), float(q.x), float(q.y), float(q.z)]


def capture_current(scene, source: float) -> dict:
    set_source_frame(scene, source)
    camera = scene.camera
    require(camera is not None, "production camera missing")
    return {
        "source_frame": source,
        "location": [float(v) for v in camera.location],
        "quaternion": quaternion_list(camera),
        "lens": float(camera.data.lens),
        "focus_distance": float(camera.data.dof.focus_distance),
    }


def capture_anchor(scene, frame: int) -> dict:
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    camera = scene.camera
    require(camera is not None, "production camera missing")
    location = camera.location.copy()
    q = camera.matrix_world.to_quaternion().normalized()
    forward = q @ Vector((0.0, 0.0, -1.0))
    target = location + forward * LOOK_DISTANCE
    return {
        "source_frame": frame,
        "location": [float(v) for v in location],
        "target": [float(v) for v in target],
        "quaternion": [float(q.w), float(q.x), float(q.y), float(q.z)],
        "lens": float(camera.data.lens),
        "focus_distance": float(camera.data.dof.focus_distance),
    }


def endpoint_extended(points: list[Vector], index: int) -> Vector:
    if index < 0:
        return points[0] * 2.0 - points[1]
    if index >= len(points):
        return points[-1] * 2.0 - points[-2]
    return points[index]


def centripetal_vector(points: list[Vector], segment: int, u: float) -> Vector:
    p0 = endpoint_extended(points, segment - 1)
    p1 = endpoint_extended(points, segment)
    p2 = endpoint_extended(points, segment + 1)
    p3 = endpoint_extended(points, segment + 2)

    def advance(t: float, a: Vector, b: Vector) -> float:
        return t + max((b - a).length, 1e-9) ** 0.5

    t0 = 0.0
    t1 = advance(t0, p0, p1)
    t2 = advance(t1, p1, p2)
    t3 = advance(t2, p2, p3)
    t = t1 + max(0.0, min(1.0, u)) * (t2 - t1)

    def blend(a: Vector, b: Vector, ta: float, tb: float) -> Vector:
        if abs(tb - ta) < 1e-12:
            return a.copy()
        return ((tb - t) / (tb - ta)) * a + ((t - ta) / (tb - ta)) * b

    a1 = blend(p0, p1, t0, t1)
    a2 = blend(p1, p2, t1, t2)
    a3 = blend(p2, p3, t2, t3)

    def blend_at(a: Vector, b: Vector, ta: float, tb: float) -> Vector:
        if abs(tb - ta) < 1e-12:
            return a.copy()
        return ((tb - t) / (tb - ta)) * a + ((t - ta) / (tb - ta)) * b

    b1 = blend_at(a1, a2, t0, t2)
    b2 = blend_at(a2, a3, t1, t3)
    if abs(t2 - t1) < 1e-12:
        return b1
    return ((t2 - t) / (t2 - t1)) * b1 + ((t - t1) / (t2 - t1)) * b2


def cubic_scalar(values: list[float], segment: int, u: float) -> float:
    def at(index: int) -> float:
        if index < 0:
            return 2.0 * values[0] - values[1]
        if index >= len(values):
            return 2.0 * values[-1] - values[-2]
        return values[index]

    p0, p1, p2, p3 = (at(segment - 1), at(segment), at(segment + 1), at(segment + 2))
    m1 = 0.5 * (p2 - p0)
    m2 = 0.5 * (p3 - p1)
    u2 = u * u
    u3 = u2 * u
    return (
        (2 * u3 - 3 * u2 + 1) * p1
        + (u3 - 2 * u2 + u) * m1
        + (-2 * u3 + 3 * u2) * p2
        + (u3 - u2) * m2
    )


def build_dense_path(anchors: list[dict]) -> tuple[list[dict], list[float]]:
    positions = [Vector(a["location"]) for a in anchors]
    targets = [Vector(a["target"]) for a in anchors]
    lenses = [float(a["lens"]) for a in anchors]
    focuses = [float(a["focus_distance"]) for a in anchors]

    states: list[dict] = []
    cumulative: list[float] = []
    total = 0.0
    previous: Vector | None = None

    for segment in range(len(anchors) - 1):
        start = 0 if segment == 0 else 1
        for step in range(start, DENSE_PER_SEGMENT + 1):
            u = step / DENSE_PER_SEGMENT
            position = centripetal_vector(positions, segment, u)
            target = centripetal_vector(targets, segment, u)
            if previous is not None:
                total += (position - previous).length
            states.append({
                "segment": segment,
                "u": u,
                "location": position,
                "target": target,
                "lens": cubic_scalar(lenses, segment, u),
                "focus_distance": max(1.0, cubic_scalar(focuses, segment, u)),
            })
            cumulative.append(total)
            previous = position

    require(total > 0.0, "smoothed camera path has zero length")
    return states, cumulative


def interpolate_state(a: dict, b: dict, alpha: float) -> dict:
    alpha = max(0.0, min(1.0, alpha))
    return {
        "location": a["location"].lerp(b["location"], alpha),
        "target": a["target"].lerp(b["target"], alpha),
        "lens": (1.0 - alpha) * a["lens"] + alpha * b["lens"],
        "focus_distance": (1.0 - alpha) * a["focus_distance"] + alpha * b["focus_distance"],
    }


def state_at_distance(states: list[dict], cumulative: list[float], distance: float) -> dict:
    if distance <= 0.0:
        return states[0]
    if distance >= cumulative[-1]:
        return states[-1]
    hi = bisect.bisect_left(cumulative, distance)
    lo = max(0, hi - 1)
    span = cumulative[hi] - cumulative[lo]
    if span <= 1e-12:
        return states[hi]
    alpha = (distance - cumulative[lo]) / span
    return interpolate_state(states[lo], states[hi], alpha)


def smooth_records(anchors: list[dict]) -> tuple[list[dict], dict]:
    dense, cumulative = build_dense_path(anchors)
    total_length = cumulative[-1]
    records: list[dict] = []

    for output_frame in range(1, OUTPUT_FRAMES + 1):
        t = (output_frame - 1) / (OUTPUT_FRAMES - 1)
        state = state_at_distance(dense, cumulative, t * total_length)
        location: Vector = state["location"]
        target: Vector = state["target"]
        q = (target - location).to_track_quat("-Z", "Y").normalized()
        records.append({
            "output_frame": output_frame,
            "route_fraction": t,
            "location": [float(v) for v in location],
            "target": [float(v) for v in target],
            "quaternion": [float(q.w), float(q.x), float(q.y), float(q.z)],
            "lens": float(state["lens"]),
            "focus_distance": float(state["focus_distance"]),
        })

    segment_lengths: list[float] = []
    positions = [Vector(a["location"]) for a in anchors]
    for segment in range(len(anchors) - 1):
        sample = [
            centripetal_vector(positions, segment, step / 500.0)
            for step in range(501)
        ]
        length = sum((b - a).length for a, b in zip(sample, sample[1:]))
        segment_lengths.append(length)

    return records, {
        "path_length": total_length,
        "segment_lengths": segment_lengths,
        "segment_time_seconds": [
            (length / total_length) * (OUTPUT_FRAMES / OUTPUT_FPS)
            for length in segment_lengths
        ],
    }


def percentile(values: list[float], q: float) -> float:
    require(values, "metric list is empty")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lo = int(math.floor(position))
    hi = int(math.ceil(position))
    if lo == hi:
        return ordered[lo]
    alpha = position - lo
    return (1.0 - alpha) * ordered[lo] + alpha * ordered[hi]


def quat_angle(a: list[float], b: list[float]) -> float:
    dot = abs(sum(x * y for x, y in zip(a, b)))
    dot = max(-1.0, min(1.0, dot))
    return 2.0 * math.acos(dot)


def summarize(values: list[float]) -> dict:
    mean = statistics.fmean(values)
    std = statistics.pstdev(values) if len(values) > 1 else 0.0
    return {
        "mean": mean,
        "std": std,
        "cv": std / mean if mean > 1e-12 else 0.0,
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "max": max(values),
    }


def motion_metrics(records: list[dict]) -> dict:
    linear_steps = [
        (Vector(b["location"]) - Vector(a["location"])).length
        for a, b in zip(records, records[1:])
    ]
    angular_steps = [
        quat_angle(a["quaternion"], b["quaternion"])
        for a, b in zip(records, records[1:])
    ]
    linear_accel = [abs(b - a) for a, b in zip(linear_steps, linear_steps[1:])]
    angular_accel = [abs(b - a) for a, b in zip(angular_steps, angular_steps[1:])]
    return {
        "linear_step": summarize(linear_steps),
        "angular_step_radians": summarize(angular_steps),
        "linear_step_change": summarize(linear_accel),
        "angular_step_change_radians": summarize(angular_accel),
    }


def render_proxy(scene, records: list[dict], out: Path) -> dict:
    frames = out / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    camera = scene.camera
    require(camera is not None, "production camera missing")

    engine = None
    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = candidate
            engine = candidate
            break
        except (TypeError, ValueError):
            pass
    require(engine is not None, "No supported EEVEE engine")

    scene.render.resolution_x = PROXY_RESOLUTION[0]
    scene.render.resolution_y = PROXY_RESOLUTION[1]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.fps = OUTPUT_FPS
    scene.render.fps_base = 1.0

    hashes: dict[str, dict] = {}
    started_total = time.perf_counter()
    scene.frame_set(1)

    for record in records:
        frame = int(record["output_frame"])
        camera.location = Vector(record["location"])
        camera.rotation_euler = (
            Vector(record["target"]) - camera.location
        ).to_track_quat("-Z", "Y").to_euler()
        camera.data.lens = float(record["lens"])
        camera.data.dof.focus_distance = float(record["focus_distance"])
        bpy.context.view_layer.update()

        path = frames / f"frame_{frame:04d}.png"
        scene.render.filepath = str(path)
        started = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        elapsed = time.perf_counter() - started
        require(path.is_file() and path.stat().st_size > 0, f"missing proxy frame {frame}")
        hashes[str(frame)] = {
            "sha256": full.digest_file(path),
            "bytes": path.stat().st_size,
            "seconds": elapsed,
        }
        print(f"033 smooth-camera proxy frame {frame}: {elapsed:.3f}s")

    return {
        "engine": engine,
        "resolution": PROXY_RESOLUTION,
        "fps": OUTPUT_FPS,
        "frame_count": OUTPUT_FRAMES,
        "total_seconds": time.perf_counter() - started_total,
        "frames": hashes,
    }


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    review = json.loads(args.review.read_text())
    prepare = json.loads(args.prepare.read_text())

    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene = bpy.context.scene
    lane031.verify_source(scene, args.blend, review, prepare)

    before_structure = look030.structure_digest(scene)
    before_cameras = full.camera_records(scene)

    anchors = [capture_anchor(scene, frame) for frame in ANCHOR_SOURCE_FRAMES]
    current = [capture_current(scene, source_time(frame)) for frame in range(1, OUTPUT_FRAMES + 1)]
    smooth, path_info = smooth_records(anchors)

    current_metrics = motion_metrics(current)
    smooth_metrics = motion_metrics(smooth)

    proxy = render_proxy(scene, smooth, args.out)

    scene.frame_set(1)
    bpy.context.view_layer.update()
    require(look030.structure_digest(scene) == before_structure, "033 proxy changed accepted scene structure")
    require(full.camera_records(scene) == before_cameras, "033 proxy changed native camera animation")

    receipt = {
        "version": "coimbra-033-smooth-camera-motion-review-v1",
        "source_030_run": lane031.EXPECTED_030_RUN,
        "source_030_revision": lane031.EXPECTED_030_REVISION,
        "source_030_blend_sha256": lane031.EXPECTED_BLEND_SHA256,
        "source_030_structure_sha256": lane031.EXPECTED_STRUCTURE_SHA256,
        "source_026_run": 36646652931,
        "source_code_commit": os.environ.get("COIMBRA_SOURCE_SHA", "local"),
        "anchor_source_frames": ANCHOR_SOURCE_FRAMES,
        "anchors": anchors,
        "route_model": {
            "position": "centripetal Catmull-Rom through accepted anchor locations",
            "target": "centripetal Catmull-Rom through anchor forward targets",
            "speed": "global arc-length parameterization",
            "rotation": "look-at quaternion derived from smoothed target and position",
            "lens_focus": "cubic interpolation through accepted anchor values",
            "look_distance": LOOK_DISTANCE,
            "dense_samples_per_segment": DENSE_PER_SEGMENT,
            **path_info,
        },
        "delivery": {
            "frame_count": OUTPUT_FRAMES,
            "fps": OUTPUT_FPS,
            "duration_seconds": OUTPUT_FRAMES / OUTPUT_FPS,
            "resolution": PROXY_RESOLUTION,
            "purpose": "motion-only proxy review; not a production-look acceptance render",
            "motion_blur": False,
        },
        "motion_metrics": {
            "current_032_sampling": current_metrics,
            "candidate_033_smoothed": smooth_metrics,
        },
        "scene_structure_unchanged": True,
        "native_camera_animation_unchanged": True,
        "proxy": proxy,
        "smooth_records": smooth,
    }

    (args.out / "camera-motion-review.json").write_text(
        json.dumps(receipt, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "path_length": path_info["path_length"],
        "current_linear_cv": current_metrics["linear_step"]["cv"],
        "smooth_linear_cv": smooth_metrics["linear_step"]["cv"],
        "current_angular_change_p95": current_metrics["angular_step_change_radians"]["p95"],
        "smooth_angular_change_p95": smooth_metrics["angular_step_change_radians"]["p95"],
        "proxy_seconds": proxy["total_seconds"],
    }, indent=2))


if __name__ == "__main__":
    main()
