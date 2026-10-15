#!/usr/bin/env python3
"""Check that all three Coimbra 039 browser screenshots exist and have scene detail.

This is not a perceptual-quality judgment: human review remains mandatory.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parents[1] / "web" / "street-qa-evidence"
SPOTS = ("sanches-brasil", "polo-ii", "portela")


def main() -> None:
    report = json.loads((ROOT / "coimbra-039-browser-report.json").read_text())
    captures = report.get("captures") or []
    if [c.get("spot") for c in captures] != list(SPOTS):
        raise SystemExit("All three street-specific browser captures required")
    results = []
    for spot in SPOTS:
        p = ROOT / f"coimbra-039-{spot}.png"
        with Image.open(p) as image:
            image.load()
            if image.format != "PNG" or image.width < 900 or image.height < 500:
                raise SystemExit(f"{spot}: invalid screenshot format/resolution")
            # Avoid HUD (upper left) and credits (lower right). A uniformly
            # black canvas with only text overlay must not be accepted.
            inner = image.convert("RGB").crop((
                int(image.width * 0.48), int(image.height * 0.24),
                int(image.width * 0.88), int(image.height * 0.80),
            ))
            rgb_stddev = ImageStat.Stat(inner).stddev
            minimum = max(rgb_stddev)
            if minimum < 2.0:
                raise SystemExit(f"{spot}: likely blank scene (RGB stddev={rgb_stddev})")
            results.append({"spot": spot, "pixel_size": image.size, "rgb_stddev": rgb_stddev,
                            "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    (ROOT / "coimbra-039-image-verification.json").write_text(
        json.dumps({"lane":"coimbra-039-street-qa", "images":results,
                    "is_human_approved":False}, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
