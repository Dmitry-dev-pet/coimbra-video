from __future__ import annotations

import json
import sys
from pathlib import Path


def fail(message: str):
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main():
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: verify_full_render_new_geometry.py <prepare-manifest> <final-manifest>"
        )

    prepare = json.loads(Path(sys.argv[1]).read_text())
    final = json.loads(Path(sys.argv[2]).read_text())

    if prepare.get("version") != "coimbra-full-render-new-geometry-v1":
        fail("wrong prepare version")
    if prepare.get("resolution") != [1280, 720]:
        fail("unexpected resolution")
    if int(prepare.get("fps", 0)) != 30:
        fail("unexpected fps")
    if int(prepare.get("frame_count", 0)) != 360:
        fail("expected 360 frames")
    if prepare.get("production_camera_unchanged") is not True:
        fail("production camera changed")

    patch = prepare.get("polo2_patch") or {}
    expected = {143294113, 143294117, 143294126, 379862984}
    if set(patch.get("hero_ids") or []) != expected:
        fail("unexpected Polo II hero building ids")
    if patch.get("flat_tile_violations"):
        fail("flat hero roof tile invariant failed")

    windows = patch.get("window_stats") or {}
    if int(windows.get("emitted", 0)) < 250:
        fail("new window geometry unexpectedly sparse")
    if int(windows.get("skipped", 0)) <= 0:
        fail("013 facade variation did not activate")

    realism_stats = patch.get("realism") or {}
    if int(realism_stats.get("roof_units", 0)) < 1:
        fail("013 rooftop detail missing")
    if int(realism_stats.get("trim_pieces", 0)) != 8:
        fail("013 facade trims missing")

    groundcover = patch.get("groundcover") or {}
    if int(groundcover.get("green_ways", 0)) <= 0:
        fail("014 green-area geometry missing")
    if int(groundcover.get("shrubs", 0)) < 6:
        fail("014 shrubs missing")
    if int(groundcover.get("grass_tufts", 0)) < 20:
        fail("014 grass geometry missing")

    if int(final.get("frame_count", 0)) != 360:
        fail("final frame count mismatch")
    if final.get("resolution") != [1280, 720]:
        fail("final resolution mismatch")
    if int(final.get("fps", 0)) != 30:
        fail("final fps mismatch")
    if final.get("codec") != "h264":
        fail("unexpected codec")
    duration = float(final.get("duration_seconds", 0.0))
    if not (11.8 <= duration <= 12.2):
        fail(f"unexpected duration: {duration}")

    print(json.dumps({
        "ok": True,
        "frames": final.get("frame_count"),
        "resolution": final.get("resolution"),
        "fps": final.get("fps"),
        "duration_seconds": final.get("duration_seconds"),
        "hero_ids": sorted(expected),
        "windows_emitted": windows.get("emitted"),
        "roof_units": realism_stats.get("roof_units"),
        "shrubs": groundcover.get("shrubs"),
        "grass_tufts": groundcover.get("grass_tufts"),
    }, indent=2))


if __name__ == "__main__":
    main()
