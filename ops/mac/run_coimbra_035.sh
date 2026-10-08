#!/usr/bin/env bash
set -euo pipefail

: "${BLENDER_PATH:?BLENDER_PATH is required}"
: "${COIMBRA_SOURCE_SHA:?COIMBRA_SOURCE_SHA is required}"

OUT="artifacts/coimbra-035"
mkdir -p "$OUT"

"$BLENDER_PATH"   --background   --factory-startup   --python-exit-code 1   --python coimbra/blender/render_visual_polish_review.py --   --blend "$PWD/source_030/coimbra-production-look.blend"   --review "$PWD/source_030/production-look-review.json"   --prepare "$PWD/source_026/prepare.json"   --out "$PWD/$OUT"

test -s "$OUT/visual-polish-review.json"
test "$(find "$OUT" -type f -name 'output-*.png' | wc -l | tr -d ' ')" = "20"

python3 coimbra/scripts/verify_visual_polish_review.py   "$OUT/visual-polish-review.json"   --out "$OUT/verification.json"
test -s "$OUT/verification.json"

FONT="/System/Library/Fonts/Supplemental/Arial.ttf"
test -f "$FONT"

python3 -m venv .venv-coimbra-035-review
.venv-coimbra-035-review/bin/python -m pip install --quiet --upgrade pip
.venv-coimbra-035-review/bin/python -m pip install --quiet "Pillow>=11,<13"

FONT="$FONT" .venv-coimbra-035-review/bin/python - <<'PY'
from __future__ import annotations

import json
import math
import os
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

root = Path("artifacts/coimbra-035")
review = json.loads((root / "visual-polish-review.json").read_text())
font_path = os.environ["FONT"]

variants = ["baseline", "motion_blur", "atmosphere_light", "quality64"]
variant_labels = {
    "baseline": "Baseline 032",
    "motion_blur": "Motion blur · 180°",
    "atmosphere_light": "Atmosphere + light",
    "quality64": "64 samples",
}
checkpoints = review["checkpoint_output_frames"]

tile_w, tile_h = 480, 300
header_h = 46
row_label_w = 110
sheet_w = row_label_w + tile_w * len(variants)
sheet_h = header_h + tile_h * len(checkpoints)
sheet = Image.new("RGB", (sheet_w, sheet_h), (24, 24, 24))
draw = ImageDraw.Draw(sheet)
header_font = ImageFont.truetype(font_path, 24)
row_font = ImageFont.truetype(font_path, 22)
small_font = ImageFont.truetype(font_path, 18)

for col, variant in enumerate(variants):
    x = row_label_w + col * tile_w + 12
    draw.text((x, 9), variant_labels[variant], font=header_font, fill=(240, 240, 240))

metrics = {}
for row, output_frame in enumerate(checkpoints):
    y = header_h + row * tile_h
    draw.text((10, y + 12), f"{output_frame}", font=row_font, fill=(240, 240, 240))
    source = review["checkpoint_evidence"][str(output_frame)]["source_frame"]
    draw.text((10, y + 44), f"src {source:.2f}", font=small_font, fill=(185, 185, 185))

    baseline_path = root / review["variants"]["baseline"]["images"][str(output_frame)]["path"]
    baseline = Image.open(baseline_path).convert("RGB")
    baseline_rgb = baseline.resize((tile_w, tile_h), Image.Resampling.LANCZOS)

    metrics[str(output_frame)] = {}
    for col, variant in enumerate(variants):
        path = root / review["variants"][variant]["images"][str(output_frame)]["path"]
        image = Image.open(path).convert("RGB")
        shown = image.resize((tile_w, tile_h), Image.Resampling.LANCZOS)
        sheet.paste(shown, (row_label_w + col * tile_w, y))

        diff = ImageChops.difference(image, baseline)
        stat = ImageStat.Stat(diff)
        mean = [float(x) for x in stat.mean[:3]]
        rms = [float(x) for x in stat.rms[:3]]
        metrics[str(output_frame)][variant] = {
            "mean_abs_rgb_255": mean,
            "mean_abs_rgb_average_255": sum(mean) / 3.0,
            "rms_rgb_255": rms,
            "rms_rgb_average_255": sum(rms) / 3.0,
        }

sheet.save(root / "visual-polish-contact-sheet.png", quality=95)
(root / "image-difference-metrics.json").write_text(
    json.dumps(
        {
            "version": "coimbra-035-image-difference-metrics-v1",
            "reference": "baseline",
            "checkpoints": checkpoints,
            "variants": variants,
            "metrics": metrics,
            "interpretation": (
                "Pixel difference is diagnostic only and is not a visual-quality score; "
                "human review decides whether a treatment is preferable."
            ),
        },
        indent=2,
    )
    + "\n"
)
PY

test -s "$OUT/visual-polish-contact-sheet.png"
test -s "$OUT/image-difference-metrics.json"
