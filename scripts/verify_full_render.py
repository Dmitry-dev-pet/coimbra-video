from __future__ import annotations

import json
import sys
from pathlib import Path


def fail(message: str):
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify_full_render.py <prepare-manifest> <final-manifest>")

    prepare = json.loads(Path(sys.argv[1]).read_text())
    final = json.loads(Path(sys.argv[2]).read_text())

    if prepare.get("version") != "coimbra-full-render-v1":
        fail("wrong prepare version")
    if prepare.get("resolution") != [1280, 720]:
        fail("unexpected render resolution")
    if int(prepare.get("fps", 0)) != 30:
        fail("unexpected fps")
    if int(prepare.get("frame_count", 0)) != 360:
        fail("expected 360 frames")
    if prepare.get("camera_unchanged") is not True:
        fail("production camera changed")
    if prepare.get("camera_hash_before") != prepare.get("camera_hash_after"):
        fail("camera signature mismatch")

    changes = prepare.get("scene_changes") or {}
    for key in ("geometry", "materials", "lighting", "camera_animation"):
        if changes.get(key) is not False:
            fail(f"unexpected scene mutation: {key}")

    if int(final.get("frame_count", 0)) != 360:
        fail("final frame count mismatch")
    if final.get("resolution") != [1280, 720]:
        fail("final resolution mismatch")
    if int(final.get("fps", 0)) != 30:
        fail("final fps mismatch")
    duration = float(final.get("duration_seconds", 0.0))
    if not (11.8 <= duration <= 12.2):
        fail(f"unexpected video duration: {duration}")
    if final.get("codec") != "h264":
        fail("unexpected codec")

    print(json.dumps({
        "ok": True,
        "frames": final.get("frame_count"),
        "resolution": final.get("resolution"),
        "fps": final.get("fps"),
        "duration_seconds": final.get("duration_seconds"),
        "codec": final.get("codec"),
    }, indent=2))


if __name__ == "__main__":
    main()
