"""Summarize Coimbra 029 Mac device modes against accepted GitHub Actions CPU evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

START, END = 181, 210
COUNT = 30

# Accepted 026 evidence. Job 109671765388 rendered frames 181..210.
# Blender log: first render clock begins at 00:00 and frame 210 was saved at 24:22.663.
GHA = {
    "source": "accepted-coimbra-026",
    "run_id": 36646652931,
    "job_id": 109671765388,
    "frames": [START, END],
    "render_seconds": 1462.663,
    "seconds_per_frame": 1462.663 / COUNT,
    "full_workflow_seconds": 1748.0,
    "parallel_render_phase_seconds": 1545.0,
    "parallel_workers": 12,
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_receipt(path: Path, mode: str, start: int, end: int) -> dict:
    data = json.loads(path.read_text())
    require(data["version"] == "coimbra-029-device-benchmark-v1", f"{mode}: bad schema")
    require(data["device_mode"] == mode, f"{mode}: wrong mode")
    require(data["start"] == start and data["end"] == end, f"{mode}: wrong frame range")
    require(data["scene_unchanged"] is True and data["camera_unchanged"] is True, f"{mode}: invariant failed")
    expected = list(range(start, end + 1))
    require(sorted(map(int, data["timings_seconds"])) == expected, f"{mode}: incomplete timings")
    require(sorted(map(int, data["images"])) == expected, f"{mode}: incomplete images")
    require(data["total_seconds"] > 0, f"{mode}: non-positive total")
    return data


def metric(name: str, seconds: float) -> dict:
    return {
        "name": name,
        "frames": COUNT,
        "wall_seconds": seconds,
        "seconds_per_frame": seconds / COUNT,
        "frames_per_second": COUNT / seconds,
        "speedup_vs_gha_single_cpu": GHA["render_seconds"] / seconds,
    }


def summarize(root: Path) -> dict:
    cpu = load_receipt(root / "mac-cpu" / "receipt.json", "cpu", START, END)
    metal = load_receipt(root / "metal-1x" / "receipt.json", "metal", START, END)
    hybrid = load_receipt(root / "metal-cpu" / "receipt.json", "metal-cpu", START, END)
    dual_a = load_receipt(root / "metal-2x-a" / "receipt.json", "metal", START, 195)
    dual_b = load_receipt(root / "metal-2x-b" / "receipt.json", "metal", 196, END)
    dual = json.loads((root / "metal-2x-wall.json").read_text())

    require(dual["wall_seconds"] > 0, "dual: non-positive wall time")
    require(dual_a["end"] + 1 == dual_b["start"], "dual: ranges not contiguous")

    modes = {
        "github_actions_cpu_single": metric("GitHub Actions CPU single runner", GHA["render_seconds"]),
        "mac_cpu": metric("Mac M4 CPU", cpu["total_seconds"]),
        "mac_metal_1x": metric("Mac M4 Metal ×1", metal["total_seconds"]),
        "mac_metal_cpu": metric("Mac M4 Metal+CPU", hybrid["total_seconds"]),
        "mac_metal_2x": metric("Mac M4 Metal ×2 processes", dual["wall_seconds"]),
    }

    fastest_key = min(
        ("mac_cpu", "mac_metal_1x", "mac_metal_cpu", "mac_metal_2x"),
        key=lambda key: modes[key]["wall_seconds"],
    )

    result = {
        "version": "coimbra-029-render-benchmark-summary-v1",
        "frames": [START, END],
        "frame_count": COUNT,
        "github_actions_baseline": GHA,
        "modes": modes,
        "fastest_mac_mode": fastest_key,
        "fastest_mac_wall_seconds": modes[fastest_key]["wall_seconds"],
        "mac_speedup_vs_gha_single_cpu": modes[fastest_key]["speedup_vs_gha_single_cpu"],
        "metal_2x_speedup_vs_metal_1x": metal["total_seconds"] / dual["wall_seconds"],
        "metal_cpu_speedup_vs_metal_1x": metal["total_seconds"] / hybrid["total_seconds"],
        "mac_cpu_speedup_vs_gha_single_cpu": GHA["render_seconds"] / cpu["total_seconds"],
    }
    (root / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.root), indent=2))


if __name__ == "__main__":
    main()
