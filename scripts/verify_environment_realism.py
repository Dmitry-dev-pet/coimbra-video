from __future__ import annotations

import json
import sys
from pathlib import Path


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_environment_realism.py <manifest>")

    manifest = json.loads(Path(sys.argv[1]).read_text())
    if manifest.get("version") != "coimbra-environment-realism-v1":
        fail("wrong version")

    surfaces = manifest.get("surfaces") or {}
    if int(surfaces.get("sidewalk_slots", 0)) <= 0:
        fail("sidewalk material was not replaced")
    if int(surfaces.get("curb_slots", 0)) <= 0:
        fail("curb material was not replaced")

    environment = manifest.get("environment") or {}
    if int(environment.get("green_ways", 0)) <= 0:
        fail("no OSM green areas were used")
    if int(environment.get("green_ground_triangles", 0)) <= 0:
        fail("green ground overlay is empty")
    if int(environment.get("shrubs", 0)) < 6:
        fail("too few shrubs")
    if int(environment.get("grass_tufts", 0)) < 20:
        fail("too few grass tufts")
    if int(environment.get("groundcover_faces", 0)) <= 0:
        fail("groundcover mesh is empty")

    lighting = manifest.get("lighting") or {}
    before = lighting.get("before") or {}
    after = lighting.get("after") or {}
    if float(after.get("sun_angle_deg", 0.0)) < 12.0:
        fail("sun remains too sharp")
    if float(after.get("fill_energy", 1e9)) >= float(before.get("fill_energy", 0.0)):
        fail("cool fill was not reduced")
    if float(after.get("sun_energy", 1e9)) >= float(before.get("sun_energy", 0.0)):
        fail("sun energy was not softened")

    images = manifest.get("images") or []
    if len(images) != 3:
        fail("expected exactly three review photos")

    rules = manifest.get("rules") or {}
    for key in (
        "photo_patch_only",
        "hero_buildings_unchanged",
        "greenery_from_osm_green_areas_only",
        "no_blender_artifact",
    ):
        if rules.get(key) is not True:
            fail(f"missing invariant: {key}")

    print(json.dumps({
        "ok": True,
        "green_ways": environment.get("green_ways"),
        "shrubs": environment.get("shrubs"),
        "grass_tufts": environment.get("grass_tufts"),
        "sidewalk_slots": surfaces.get("sidewalk_slots"),
        "curb_slots": surfaces.get("curb_slots"),
        "sun_angle_deg": after.get("sun_angle_deg"),
        "fill_energy": after.get("fill_energy"),
    }, indent=2))


if __name__ == "__main__":
    main()
