from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: verify_final_look.py <render-manifest> <grade-manifest>"
        )

    render_manifest = json.loads(Path(sys.argv[1]).read_text())
    grade_manifest = json.loads(Path(sys.argv[2]).read_text())

    if render_manifest.get("version") != "coimbra-final-look-v1":
        fail("wrong render manifest version")
    if grade_manifest.get("version") != "coimbra-final-look-grade-v1":
        fail("wrong grade manifest version")

    if render_manifest.get("master_resolution") != [3200, 2000]:
        fail("master is not 2x target resolution")
    if render_manifest.get("target_resolution") != [1600, 1000]:
        fail("unexpected delivery resolution")
    if float(render_manifest.get("oversample_factor", 0.0)) != 2.0:
        fail("unexpected oversample factor")

    scene_changes = render_manifest.get("scene_changes") or {}
    for key in ("geometry", "materials", "lighting"):
        if scene_changes.get(key) is not False:
            fail(f"015 changed scene {key}")

    profiles = grade_manifest.get("profiles") or {}
    expected = {"neutral", "warm", "soft-cinematic"}
    if set(profiles) != expected:
        fail(f"unexpected grade set: {sorted(profiles)}")

    sizes = {}
    for name, relative in profiles.items():
        path = ROOT / relative
        if not path.is_file():
            fail(f"missing grade image: {path}")
        with Image.open(path) as image:
            sizes[name] = list(image.size)
            if image.size != (1600, 1000):
                fail(f"{name} has wrong resolution: {image.size}")

    rules = grade_manifest.get("rules") or {}
    for key in (
        "no_geometry_changes",
        "no_scene_material_changes",
        "same_camera_for_all_grades",
        "grade_only_after_render",
    ):
        if rules.get(key) is not True:
            fail(f"missing grade invariant: {key}")

    print(json.dumps({
        "ok": True,
        "profiles": sorted(profiles),
        "sizes": sizes,
        "oversample_factor": render_manifest.get("oversample_factor"),
        "camera_lens": (render_manifest.get("camera") or {}).get("lens"),
    }, indent=2))


if __name__ == "__main__":
    main()
