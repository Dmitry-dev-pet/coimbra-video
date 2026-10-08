#!/usr/bin/env bash
set -euo pipefail

: "${BLENDER_PATH:?BLENDER_PATH is required}"
: "${COIMBRA_SOURCE_SHA:?COIMBRA_SOURCE_SHA is required}"

OUT="artifacts/coimbra-033"
mkdir -p "$OUT"

"$BLENDER_PATH"   --background   --factory-startup   --python-exit-code 1   --python coimbra/blender/render_camera_motion_review.py --   --blend "$PWD/source_030/coimbra-production-look.blend"   --review "$PWD/source_030/production-look-review.json"   --prepare "$PWD/source_026/prepare.json"   --out "$PWD/$OUT"

test "$(find "$OUT/frames" -name 'frame_*.png' | wc -l | tr -d ' ')" = "1440"
test -s "$OUT/camera-motion-review.json"
test -s source_032/coimbra-production-look-slow60-metal-24s.mp4

command -v ffmpeg >/dev/null
command -v ffprobe >/dev/null
ffmpeg -hide_banner -encoders 2>/dev/null | grep -q 'libx264'
ffmpeg -hide_banner -filters 2>/dev/null | grep -q ' overlay '

FONT="/System/Library/Fonts/Supplemental/Arial.ttf"
test -f "$FONT"

printf '%s\n'   'Terrain / Ortho © DGT · Open data / CC BY 4.0 | Map data © OpenStreetMap contributors · ODbL'   > "$OUT/attribution.txt"

python3 -m venv .venv-coimbra-033-encode
.venv-coimbra-033-encode/bin/python -m pip install --quiet --upgrade pip
.venv-coimbra-033-encode/bin/python -m pip install --quiet "Pillow>=11,<13"

FONT="$FONT" .venv-coimbra-033-encode/bin/python - <<'PY'
from pathlib import Path
import os
from PIL import Image, ImageDraw, ImageFont

out = Path("artifacts/coimbra-033")
font_path = os.environ["FONT"]

def font(size: int):
    return ImageFont.truetype(font_path, size)

def box(draw, xy, text, font_obj):
    left, top = xy
    bbox = draw.textbbox((left, top), text, font=font_obj)
    pad_x, pad_y = 8, 5
    draw.rounded_rectangle(
        (
            bbox[0] - pad_x,
            bbox[1] - pad_y,
            bbox[2] + pad_x,
            bbox[3] + pad_y,
        ),
        radius=4,
        fill=(0, 0, 0, 110),
    )
    draw.text((left, top), text, font=font_obj, fill=(255, 255, 255, 255))

attribution = "Terrain / Ortho © DGT | Map data © OpenStreetMap contributors"

proxy = Image.new("RGBA", (960, 600), (0, 0, 0, 0))
draw = ImageDraw.Draw(proxy)
box(draw, (18, 16), "033 smooth camera proxy", font(18))
box(draw, (14, 567), attribution, font(13))
proxy.save(out / "proxy-overlay.png")

comparison = Image.new("RGBA", (1920, 600), (0, 0, 0, 0))
draw = ImageDraw.Draw(comparison)
box(draw, (18, 16), "032 accepted motion", font(20))
box(draw, (978, 16), "033 smoothed motion proxy", font(20))
box(draw, (14, 567), attribution, font(13))
comparison.save(out / "comparison-overlay.png")
PY

ffmpeg -y   -framerate 60   -start_number 1   -i "$OUT/frames/frame_%04d.png"   -loop 1   -i "$OUT/proxy-overlay.png"   -filter_complex "[0:v][1:v]overlay=0:0:shortest=1[out]"   -map "[out]"   -frames:v 1440   -c:v libx264   -pix_fmt yuv420p   -crf 18   -preset medium   -g 60   -keyint_min 60   -sc_threshold 0   -movflags +faststart   "$OUT/coimbra-033-smooth-camera-proxy-24s.mp4"

ffprobe -v error   -count_frames   -select_streams v:0   -show_entries stream=codec_name,pix_fmt,width,height,r_frame_rate,nb_read_frames:format=duration   -of json   "$OUT/coimbra-033-smooth-camera-proxy-24s.mp4"   > "$OUT/proxy-ffprobe.json"

ffmpeg -y   -i source_032/coimbra-production-look-slow60-metal-24s.mp4   -i "$OUT/coimbra-033-smooth-camera-proxy-24s.mp4"   -loop 1   -i "$OUT/comparison-overlay.png"   -filter_complex "[0:v]scale=960:600[left];[1:v]scale=960:600[right];[left][right]hstack=inputs=2[stack];[stack][2:v]overlay=0:0:shortest=1[out]"   -map "[out]"   -frames:v 1440   -r 60   -c:v libx264   -pix_fmt yuv420p   -crf 18   -preset medium   -movflags +faststart   "$OUT/coimbra-033-vs-032-side-by-side.mp4"

ffprobe -v error   -count_frames   -select_streams v:0   -show_entries stream=codec_name,pix_fmt,width,height,r_frame_rate,nb_read_frames:format=duration   -of json   "$OUT/coimbra-033-vs-032-side-by-side.mp4"   > "$OUT/comparison-ffprobe.json"

mkdir -p "$OUT/review"
for pair in '0:0001' '360:0361' '720:0721' '1080:1081' '1439:1440'; do
  ffmpeg -y     -i "$OUT/coimbra-033-vs-032-side-by-side.mp4"     -vf "select=eq(n\,${pair%%:*})"     -fps_mode vfr     -frames:v 1     "$OUT/review/frame-${pair##*:}.png"
done

python3 coimbra/scripts/verify_camera_motion_review.py "$OUT"
test -s "$OUT/verification.json"

rm -rf "$OUT/frames"
