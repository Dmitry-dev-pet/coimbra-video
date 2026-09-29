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
            "usage: verify_route_roof_audit.py <roof-manifest> <video-manifest>"
        )

    roof = json.loads(Path(sys.argv[1]).read_text())
    video = json.loads(Path(sys.argv[2]).read_text())

    if roof.get("version") != "coimbra-route-roof-audit-v1":
        fail("wrong roof audit version")
    if roof.get("camera_unchanged") is not True:
        fail("production camera changed")

    stats = roof.get("stats") or {}
    matched = int(stats.get("matched", 0))
    removed = int(stats.get("tile_removed", 0))
    flat = int(stats.get("flat_non_tile", 0))
    pitched_tile = int(stats.get("pitched_tile", 0))
    sampled = int(stats.get("ortho_sampled", 0))

    if matched < 50:
        fail("too few route roofs matched")
    if removed < 20:
        fail("too few tile roof faces were corrected")
    if flat <= 0:
        fail("no flat non-tile roofs produced")
    if pitched_tile <= 0:
        fail("classifier removed all tile roofs")
    if sampled < 40:
        fail("DGT ortho sampling unexpectedly sparse")

    sources = roof.get("classification_sources") or {}
    if int(sources.get("ortho-color", 0)) <= 0:
        fail("orthophoto color was not used for uncertain roofs")

    frames = roof.get("review_frames") or []
    if len(frames) != 5 or len(set(frames)) != 5:
        fail("expected five unique route review frames")
    if any(int(frame) < 1 or int(frame) > 360 for frame in frames):
        fail("review frame outside production route")

    rules = roof.get("rules") or {}
    for key in (
        "explicit_roof_shape_wins",
        "flat_roof_never_tile",
        "unknown_uses_dgt_ortho_color",
        "google_not_bulk_scraped",
        "full_route_scene",
    ):
        if rules.get(key) is not True:
            fail(f"missing invariant: {key}")

    if video.get("version") != "coimbra-route-roof-audit-video-v1":
        fail("wrong video manifest version")
    if int(video.get("frame_count", 0)) != 360:
        fail("expected 360 rendered frames")
    if video.get("resolution") != [1280, 720]:
        fail("unexpected video resolution")
    if int(video.get("fps", 0)) != 30:
        fail("unexpected fps")
    if video.get("codec") != "h264":
        fail("unexpected codec")
    duration = float(video.get("duration_seconds", 0.0))
    if not (11.8 <= duration <= 12.2):
        fail(f"unexpected duration: {duration}")

    print(json.dumps({
        "ok": True,
        "matched_roofs": matched,
        "tile_removed": removed,
        "flat_non_tile": flat,
        "pitched_tile": pitched_tile,
        "ortho_sampled": sampled,
        "review_frames": frames,
        "duration_seconds": duration,
    }, indent=2))


if __name__ == "__main__":
    main()
