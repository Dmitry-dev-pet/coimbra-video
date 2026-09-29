from __future__ import annotations

import json
import sys
from pathlib import Path


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_photo_patch.py <manifest>")

    manifest = json.loads(Path(sys.argv[1]).read_text())
    if manifest.get("version") != "coimbra-polo2-photo-patch-v1":
        fail("wrong patch version")
    if float(manifest.get("patch_size_m", 0.0)) != 220.0:
        fail("unexpected patch size")

    before = manifest.get("before") or {}
    after = manifest.get("after") or {}
    if int(after.get("faces", 0)) <= 0:
        fail("cropped scene has no faces")
    if int(after.get("faces", 0)) >= int(before.get("faces", 0)):
        fail("scene was not reduced")

    reduction = manifest.get("reduction") or {}
    if float(reduction.get("faces_fraction", 1.0)) > 0.45:
        fail("photo patch is still too large")

    camera = manifest.get("camera") or {}
    if camera.get("highway") not in {
        "primary", "secondary", "tertiary", "residential"
    }:
        fail("photo camera is not anchored to a normal urban road")

    print(json.dumps({
        "ok": True,
        "before_faces": before.get("faces"),
        "after_faces": after.get("faces"),
        "faces_fraction": reduction.get("faces_fraction"),
        "camera_highway": camera.get("highway"),
        "road_way_id": camera.get("road_way_id"),
    }, indent=2))


if __name__ == "__main__":
    main()
