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
            "usage: verify_semantic_details.py <detections-json> <render-json>"
        )

    detections = json.loads(Path(sys.argv[1]).read_text())
    render = json.loads(Path(sys.argv[2]).read_text())

    if detections.get("version") != "coimbra-semantic-details-v1":
        fail("wrong detection version")
    if detections.get("semantic_model", {}).get("model") != "FasterSeg":
        fail("wrong semantic model")

    counts = detections.get("counts") or {}
    if int(counts.get("trees", 0)) < 250:
        fail("semantic tree detection unexpectedly sparse")
    if int(counts.get("pools", 0)) < 1:
        fail("no pool candidates survived filtering")

    if render.get("version") != "coimbra-semantic-detail-render-v1":
        fail("wrong render version")
    if int(render.get("placed_trees", 0)) < 250:
        fail("too few semantic trees placed")
    if int(render.get("placed_pools", 0)) < 1:
        fail("no pools placed")

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
        "trees": counts.get("trees"),
        "pools": counts.get("pools"),
        "placed_trees": render.get("placed_trees"),
        "placed_pools": render.get("placed_pools"),
        "camera_mode": render.get("camera_mode"),
    }, indent=2))


if __name__ == "__main__":
    main()
