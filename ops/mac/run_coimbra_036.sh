#!/usr/bin/env bash
set -euo pipefail

: "${BLENDER_PATH:?BLENDER_PATH is required}"
: "${COIMBRA_SOURCE_SHA:?COIMBRA_SOURCE_SHA is required}"

OUT="artifacts/coimbra-036"
mkdir -p "$OUT"

progress_enabled=false
progress_comment_id=""
render_started_at="$(date +%s)"
# Historical Coimbra 035 quality64 checkpoints: ~8.6–8.9 s/frame on this Mac.
# Use 8.8 s/frame as the cold-start ETA until enough live frames exist.
historical_seconds_per_frame="8.8"
historical_render_seconds="12672"
historical_render_eta="~3h 31m"

if [[ -n "${GH_TOKEN:-}" && -n "${PROGRESS_REPO:-}" && -n "${PROGRESS_ISSUE:-}" ]] && command -v gh >/dev/null 2>&1; then
  progress_enabled=true
  initial_body="### Coimbra 036 worker progress

Status: preparing render
Frames: **0 / 1440** (0.0%)
Initial ETA: **$historical_render_eta** render time (from Coimbra 035 quality64 measurements)
ETA source: historical **$historical_seconds_per_frame s/frame**; switches to live rate after frames appear
Heartbeat: `$(date -u '+%Y-%m-%d %H:%M:%SZ')`"
  progress_comment_id="$(gh api     --method POST     "repos/$PROGRESS_REPO/issues/$PROGRESS_ISSUE/comments"     -f body="$initial_body"     --jq '.id')"
fi

update_progress() {
  local status="$1"
  local now elapsed frames percent rate eta body
  now="$(date +%s)"
  elapsed=$((now - render_started_at))
  frames="$(find "$OUT/frames" -type f -name 'frame_*.png' 2>/dev/null | wc -l | tr -d ' ')"
  if [[ -z "$frames" ]]; then frames=0; fi

  read -r percent rate eta < <(
    python3 - "$frames" "$elapsed" <<'PY'
import sys
frames = int(sys.argv[1])
elapsed = max(int(sys.argv[2]), 0)
total = 1440
percent = 100.0 * frames / total
rate = (frames / elapsed * 60.0) if elapsed > 0 else 0.0
eta = ((total - frames) / (frames / elapsed)) if frames > 0 and elapsed > 0 else -1
print(f"{percent:.1f}", f"{rate:.2f}", f"{eta:.0f}")
PY
  )

  if [[ "$eta" == "-1" ]]; then
    eta_text="$historical_render_eta (historical)"
  else
    eta_text="$((eta / 60))m $((eta % 60))s"
  fi

  body="### Coimbra 036 worker progress

Status: **$status**
Frames: **$frames / 1440** (**$percent%**)
Elapsed: **$((elapsed / 60))m $((elapsed % 60))s**
Speed: **$rate frames/min**
ETA: **$eta_text**
Heartbeat: `$(date -u '+%Y-%m-%d %H:%M:%SZ')`"

  if [[ "$progress_enabled" == true && -n "$progress_comment_id" ]]; then
    gh api       --method PATCH       "repos/$PROGRESS_REPO/issues/comments/$progress_comment_id"       -f body="$body" >/dev/null
  fi
  printf '%s\n' "$body"
}

"$BLENDER_PATH" \
  --background \
  --factory-startup \
  --python-exit-code 1 \
  --python coimbra/blender/render_production_look_slow60_quality64_metal.py -- \
  --blend "$PWD/source_030/coimbra-production-look.blend" \
  --review "$PWD/source_030/production-look-review.json" \
  --prepare "$PWD/source_026/prepare.json" \
  --out "$PWD/$OUT" &
render_pid=$!

(
  while kill -0 "$render_pid" 2>/dev/null; do
    update_progress "rendering"
    sleep 60
  done
) &
progress_pid=$!

set +e
wait "$render_pid"
render_rc=$?
set -e

kill "$progress_pid" 2>/dev/null || true
wait "$progress_pid" 2>/dev/null || true

if [[ "$render_rc" -ne 0 ]]; then
  update_progress "render failed"
  exit "$render_rc"
fi

update_progress "render complete; encoding and verification next"

test "$(find "$OUT/frames" -name 'frame_*.png' | wc -l | tr -d ' ')" = "1440"
test -s "$OUT/render-receipt.json"

command -v ffmpeg >/dev/null
command -v ffprobe >/dev/null
ffmpeg -hide_banner -encoders 2>/dev/null | grep -q 'libx264'
ffmpeg -hide_banner -filters 2>/dev/null | grep -q ' overlay '

printf '%s\n' \
  'Terrain / Ortho © DGT · Open data / CC BY 4.0 | Map data © OpenStreetMap contributors · ODbL' \
  > "$OUT/attribution.txt"

python3 -m venv .venv-coimbra-036-encode
.venv-coimbra-036-encode/bin/python -m pip install --quiet --upgrade pip
.venv-coimbra-036-encode/bin/python -m pip install --quiet "Pillow>=11,<13"

.venv-coimbra-036-encode/bin/python - <<'PY'
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

out = Path("artifacts/coimbra-036")
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
  "$OUT/coimbra-production-look-slow60-quality64-metal-24s.mp4"

ffprobe -v error \
  -count_frames \
  -select_streams v:0 \
  -show_entries stream=codec_name,pix_fmt,width,height,r_frame_rate,nb_read_frames:format=duration \
  -of json \
  "$OUT/coimbra-production-look-slow60-quality64-metal-24s.mp4" \
  > "$OUT/ffprobe.json"

mkdir -p "$OUT/review"
for pair in '0:0001' '360:0361' '720:0721' '1080:1081' '1439:1440'; do
  ffmpeg -y \
    -i "$OUT/coimbra-production-look-slow60-quality64-metal-24s.mp4" \
    -vf "select=eq(n\,${pair%%:*})" \
    -fps_mode vfr \
    -frames:v 1 \
    "$OUT/review/frame-${pair##*:}.png"
done

python3 coimbra/scripts/verify_production_look_slow60_quality64_metal.py "$OUT"
test -s "$OUT/verification.json"

rm -rf "$OUT/frames"
