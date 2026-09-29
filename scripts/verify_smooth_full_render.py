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
            "usage: verify_smooth_full_render.py <prepare-manifest> <final-manifest>"
        )

    prepare = json.loads(Path(sys.argv[1]).read_text())
    final = json.loads(Path(sys.argv[2]).read_text())

    if prepare.get("version") != "coimbra-smooth-full-render-v1":
        fail("wrong prepare version")
    if prepare.get("sampling") != "native Blender fractional-frame evaluation":
        fail("wrong sampling method")
    if int(prepare.get("output_frames", 0)) != 1440:
        fail("expected 1440 real output frames")
    if int(prepare.get("source_frames", 0)) != 360:
        fail("expected 360-frame source route")
    step = float(prepare.get("source_frame_step", 999.0))
    if not (0.249 <= step <= 0.251):
        fail(f"unexpected source frame step: {step}")
    if float(prepare.get("first_source_frame", -1)) != 1.0:
        fail("first source frame mismatch")
    if float(prepare.get("last_source_frame", -1)) != 360.0:
        fail("last source frame mismatch")

    if final.get("version") != "coimbra-smooth-full-render-final-v1":
        fail("wrong final version")
    if int(final.get("frame_count", 0)) != 1440:
        fail("final frame count mismatch")
    if final.get("resolution") != [1280, 720]:
        fail("final resolution mismatch")
    if int(final.get("fps", 0)) != 30:
        fail("final fps mismatch")
    duration = float(final.get("duration_seconds", 0.0))
    if not (47.8 <= duration <= 48.2):
        fail(f"unexpected duration: {duration}")
    if final.get("codec") != "h264":
        fail("unexpected codec")
    if final.get("interpolation") != "Blender subframe render":
        fail("final render is not native subframe sampling")

    print(json.dumps({
        "ok": True,
        "frames": final.get("frame_count"),
        "fps": final.get("fps"),
        "duration_seconds": duration,
        "resolution": final.get("resolution"),
        "source_frame_step": step,
        "interpolation": final.get("interpolation"),
    }, indent=2))


if __name__ == "__main__":
    main()
