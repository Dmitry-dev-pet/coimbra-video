from __future__ import annotations

import json
import sys
from pathlib import Path
from PIL import Image


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: verify_semantic_objects.py <objects-json> <render-json>"
        )

    objects = json.loads(Path(sys.argv[1]).read_text())
    render = json.loads(Path(sys.argv[2]).read_text())

    if objects.get("version") != "coimbra-semantic-objects-v1":
        fail("wrong semantic objects version")
    counts = objects.get("counts") or {}
    if int(counts.get("parking", 0)) + int(counts.get("pitches", 0)) < 1:
        fail("no OSM parking or sports areas found in review crop")

    if render.get("version") != "coimbra-semantic-objects-render-v1":
        fail("wrong render version")
    if int(render.get("placed_undergrowth_points", 0)) < 1000:
        fail("022 undergrowth layer was not preserved")
    if int(render.get("parking_areas", 0)) + int(render.get("sports_areas", 0)) < 1:
        fail("no semantic ground objects placed")

    image_path = Path(render["image"])
    if not image_path.is_absolute():
        image_path = Path.cwd() / image_path
    if not image_path.is_file():
        fail("review image missing")
    with Image.open(image_path) as image:
        if image.size != (1600, 1000):
            fail(f"unexpected image size: {image.size}")

    print(json.dumps({
        "ok": True,
        "solar_detected": counts.get("solar_detections"),
        "solar_placed": render.get("solar_arrays"),
        "parking": render.get("parking_areas"),
        "sports": render.get("sports_areas"),
        "review": render.get("review"),
    }, indent=2))


if __name__ == "__main__":
    main()
