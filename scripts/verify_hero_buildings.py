from __future__ import annotations

import json
import sys
from pathlib import Path


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_hero_buildings.py <manifest>")

    manifest = json.loads(Path(sys.argv[1]).read_text())
    if manifest.get("version") != "coimbra-hero-buildings-v1":
        fail("wrong version")
    if int(manifest.get("hero_count", 0)) != 5:
        fail("expected exactly five hero buildings")

    selection = manifest.get("selection") or []
    if len(selection) != 5:
        fail("selection length mismatch")

    violations = (
        (manifest.get("roof_rule") or {}).get("flat_tile_violations") or []
    )
    if violations:
        fail(f"flat roofs use tile: {violations}")

    total_windows = 0
    flat_count = 0
    sloped_count = 0
    ids = set()
    for building in selection:
        way_id = building.get("way_id")
        if way_id in ids:
            fail("duplicate building way id")
        ids.add(way_id)
        roof = building.get("roof_built")
        if roof == "flat":
            flat_count += 1
            if building.get("uses_tile_material") is not False:
                fail(f"flat building {way_id} is marked as tile")
        else:
            sloped_count += 1
        total_windows += sum(
            int(wall.get("windows", 0))
            for wall in building.get("walls") or []
        )

    if total_windows < 10:
        fail("window generation is unexpectedly sparse")

    images = manifest.get("images") or []
    if len(images) != 3:
        fail("expected hero plus two close-up images")

    geometry = manifest.get("geometry") or {}
    if int(geometry.get("faces", 0)) <= 0:
        fail("hero geometry is empty")

    print(json.dumps({
        "ok": True,
        "hero_buildings": len(selection),
        "flat_roofs": flat_count,
        "sloped_roofs": sloped_count,
        "windows": total_windows,
        "faces": geometry.get("faces"),
    }, indent=2))


if __name__ == "__main__":
    main()
