#!/usr/bin/env bash
set -euo pipefail

: "${BLENDER_PATH:?BLENDER_PATH is required}"
: "${COIMBRA_SOURCE_SHA:?COIMBRA_SOURCE_SHA is required}"

OUT="artifacts/coimbra-032"
mkdir -p "$OUT"

"$BLENDER_PATH" \
  --background \
  --factory-startup \
  --python-exit-code 1 \
  --python coimbra/blender/render_production_look_slow60_metal.py -- \
  --blend "$PWD/source_030/coimbra-production-look.blend" \
  --review "$PWD/source_030/production-look-review.json" \
  --prepare "$PWD/source_026/prepare.json" \
  --out "$PWD/$OUT"

test "$(find "$OUT/frames" -name 'frame_*.png' | wc -l | tr -d ' ')" = "1440"
test -s "$OUT/render-receipt.json"

command -v ffmpeg >/dev/null
command -v ffprobe >/dev/null
ffmpeg -hide_banner -encoders 2>/dev/null | grep -q 'libx264'
ffmpeg -hide_banner -filters 2>/dev/null | grep -q ' overlay '

printf '%s\n' \
  'Terrain / Ortho © DGT · Open data / CC BY 4.0 | Map data © OpenStreetMap contributors · ODbL' \
  > "$OUT/attribution.txt"

python3 -m venv .venv-coimbra-032-encode
.venv-coimbra-032-encode/bin/python -m pip install --quiet --upgrade pip
.venv-coimbra-032-encode/bin/python -m pip install --quiet "Pillow>=11,<13"

.venv-coimbra-032-encode/bin/python - <<'PY'
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

out = Path("artifacts/coimbra-032")
text = (out / "attribution.txt").read_text().strip()
font_path = None
for candidate in (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Helvetica.ttf",
):
    if Path(candidate).is_file():
        font_path = candidate
        break
if font_path is None:
    raise SystemExit("No approved macOS attribution font found")

font = ImageFont.truetype(font_path, 18)
bar = Image.new("RGBA", (1600, 44), (0, 0, 0, 100))
draw = ImageDraw.Draw(bar)
draw.text((14, 10), text, font=font, fill=(255, 255, 255, 255))
bar.save(out / "attribution-overlay.png")
PY

ffmpeg -y \
  -framerate 60 \
  -start_number 1 \
  -i "$OUT/frames/frame_%04d.png" \
  -loop 1 \
  -i "$OUT/attribution-overlay.png" \
  -filter_complex "[0:v][1:v]overlay=0:H-h:shortest=1" \
  -frames:v 1440 \
  -c:v libx264 \
  -pix_fmt yuv420p \
  -crf 18 \
  -preset medium \
  -g 60 \
  -keyint_min 60 \
  -sc_threshold 0 \
  -movflags +faststart \
  "$OUT/coimbra-production-look-slow60-metal-24s.mp4"

ffprobe -v error \
  -count_frames \
  -select_streams v:0 \
  -show_entries stream=codec_name,pix_fmt,width,height,r_frame_rate,nb_read_frames:format=duration \
  -of json \
  "$OUT/coimbra-production-look-slow60-metal-24s.mp4" \
  > "$OUT/ffprobe.json"

mkdir -p "$OUT/review"
for pair in '0:0001' '360:0361' '720:0721' '1080:1081' '1439:1440'; do
  ffmpeg -y \
    -i "$OUT/coimbra-production-look-slow60-metal-24s.mp4" \
    -vf "select=eq(n\,${pair%%:*})" \
    -fps_mode vfr \
    -frames:v 1 \
    "$OUT/review/frame-${pair##*:}.png"
done

python3 coimbra/scripts/verify_production_look_slow60_metal.py "$OUT"
test -s "$OUT/verification.json"

rm -rf "$OUT/frames"
