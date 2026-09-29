from __future__ import annotations

import json
import sys
from pathlib import Path


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: verify_full_route_pitched_roofs.py <roof-manifest> <video-manifest>"
        )

    roofs = json.loads(Path(sys.argv[1]).read_text())
    video = json.loads(Path(sys.argv[2]).read_text())

    if roofs.get("version") != "coimbra-route-pitched-roofs-v1":
        fail("wrong roof manifest version")

    stats = roofs.get("stats") or {}
    if int(stats.get("buildings_converted", 0)) < 40:
        fail("too few buildings received real pitched geometry")
    if int(stats.get("new_roof_faces", 0)) <= 0:
        fail("pitched-roof overlay is empty")
    if int(stats.get("remaining_horizontal_tile_faces", -1)) != 0:
        fail("horizontal tile faces remain in camera corridor")
    if roofs.get("camera_unchanged") is not True:
        fail("production camera changed")

    rules = roofs.get("rules") or {}
    if rules.get("flat_never_tile") is not True:
        fail("flat-never-tile invariant missing")
    if rules.get("tile_requires_real_slope_geometry") is not True:
        fail("tile/slope invariant missing")
    if rules.get("unknown_tile_color_requires_lidar_relief") is not True:
        fail("LiDAR confirmation invariant missing")
    if rules.get("dgt_ortho_used") is not True:
        fail("DGT ortho evidence missing")
    if rules.get("dgt_lidar_hag_used") is not True:
        fail("DGT LiDAR HAG evidence missing")

    if video.get("version") != "coimbra-route-pitched-roofs-video-v1":
        fail("wrong video manifest version")
    if int(video.get("frame_count", 0)) != 360:
        fail("expected 360 QA frames")
    if video.get("resolution") != [1280, 720]:
        fail("unexpected QA resolution")
    if int(video.get("fps", 0)) != 30:
        fail("unexpected QA fps")
    duration = float(video.get("duration_seconds", 0.0))
    if not (11.8 <= duration <= 12.2):
        fail(f"unexpected QA duration: {duration}")
    if video.get("codec") != "h264":
        fail("unexpected codec")

    print(json.dumps({
        "ok": True,
        "buildings_converted": stats.get("buildings_converted"),
        "new_roof_faces": stats.get("new_roof_faces"),
        "complex_non_tile_fallback": stats.get("complex_non_tile_fallback"),
        "late_flat_material_fixes": stats.get("late_flat_material_fixes"),
        "remaining_horizontal_tile_faces": stats.get("remaining_horizontal_tile_faces"),
        "review_frames": roofs.get("review_frames"),
        "video_frames": video.get("frame_count"),
        "duration_seconds": duration,
    }, indent=2))


if __name__ == "__main__":
    main()
