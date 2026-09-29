from __future__ import annotations

import json
import sys
from pathlib import Path


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_urban_quality_manifest.py <manifest>")
    manifest = json.loads(Path(sys.argv[1]).read_text())

    if manifest.get("version") != "coimbra-urban-quality-v1":
        fail("wrong version")

    fixtures = manifest.get("fixture_counts") or {}
    minimums = {
        "street_lamps": 800,
        "benches": 50,
        "waste": 100,
        "bicycle_parking": 10,
        "traffic_signals": 20,
    }
    for key, minimum in minimums.items():
        if int(fixtures.get(key, 0)) < minimum:
            fail(f"{key} below sanity floor: {fixtures.get(key)} < {minimum}")

    if int(fixtures.get("stop_signs", 0)) + int(fixtures.get("give_way_signs", 0)) < 40:
        fail("too few stop/give-way signs")

    curbs = manifest.get("curbs") or {}
    markings = manifest.get("road_markings") or {}
    if int(curbs.get("segments", 0)) < 100:
        fail("curb generation is unexpectedly sparse")
    if int(markings.get("dashes", 0)) < 100:
        fail("road marking generation is unexpectedly sparse")

    production = manifest.get("production_previews") or []
    if len(production) != 3:
        fail("expected three production previews")

    street = manifest.get("street_previews") or []
    if len(street) != 3 or not all(item.get("rendered") for item in street):
        fail("expected three rendered street QA views")

    if manifest.get("protected_production_camera_unchanged") is not True:
        fail("production camera preservation flag missing")

    print(json.dumps({
        "ok": True,
        "fixtures": fixtures,
        "curb_segments": curbs.get("segments"),
        "marking_dashes": markings.get("dashes"),
        "street_views": [item.get("name") for item in street],
    }, indent=2))


if __name__ == "__main__":
    main()
