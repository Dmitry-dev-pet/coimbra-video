#!/usr/bin/env bash
set -euo pipefail

: "${BLENDER_PATH:?BLENDER_PATH is required}"
: "${COIMBRA_SOURCE_SHA:?COIMBRA_SOURCE_SHA is required}"

OUT="artifacts/coimbra-036-preview"
rm -rf "$OUT/frames"
mkdir -p "$OUT/frames"
rm -f   "$OUT/coimbra-036-preview-640x480-60fps-smoothcam-24s.mp4"   "$OUT/render-receipt.json"   "$OUT/ffprobe.json"   "$OUT/verification.json"

started="$(date +%s)"
progress_comment_id=""

if [[ -n "${GH_TOKEN:-}" && -n "${PROGRESS_REPO:-}" && -n "${PROGRESS_ISSUE:-}" ]] && command -v gh >/dev/null 2>&1; then
  body="### Coimbra 036 smooth-camera preview progress

Resolution: **640×480**
Camera: **033 smooth Catmull–Rom + global arc-length**
Frames: **0 / 1440**
FPS: **60**
Samples: **4**
Heartbeat: $(date -u '+%Y-%m-%d %H:%M:%SZ')"
  progress_comment_id="$(gh api --method POST "repos/$PROGRESS_REPO/issues/$PROGRESS_ISSUE/comments" -f body="$body" --jq '.id')"
fi

update_progress() {
  local now elapsed frames percent rate eta eta_text body
  now="$(date +%s)"
  elapsed=$((now-started))
  frames="$(find "$OUT/frames" -type f -name 'frame_*.png' 2>/dev/null | wc -l | tr -d ' ')"
  [[ -n "$frames" ]] || frames=0

  read -r percent rate eta < <(python3 - "$frames" "$elapsed" <<'PY'
import sys
f = int(sys.argv[1])
e = max(int(sys.argv[2]), 0)
total = 1440
print(
    f"{100*f/total:.1f}",
    f"{(f/e*60 if e else 0):.2f}",
    f"{((total-f)/(f/e) if f and e else -1):.0f}",
)
PY
)

  if [[ "$eta" == "-1" ]]; then
    eta_text="pending"
  else
    eta_text="$((eta/60))m $((eta%60))s"
  fi

  body="### Coimbra 036 preview progress

Resolution: **640×480**
Camera: **033 smooth Catmull–Rom + global arc-length**
Frames: **$frames / 1440** (**$percent%**)
FPS: **60**
Samples: **4**
Elapsed: **$((elapsed/60))m $((elapsed%60))s**
Speed: **$rate frames/min**
ETA: **$eta_text**
Heartbeat: $(date -u '+%Y-%m-%d %H:%M:%SZ')"

  if [[ -n "$progress_comment_id" ]]; then
    gh api --method PATCH "repos/$PROGRESS_REPO/issues/comments/$progress_comment_id" -f body="$body" >/dev/null
  fi
}

"$BLENDER_PATH"   --background   --factory-startup   --python-exit-code 1   --python scripts/render_coimbra_036_preview.py --   --blend "$PWD/source_030/coimbra-production-look.blend"   --review "$PWD/source_030/production-look-review.json"   --prepare "$PWD/source_026/prepare.json"   --out "$PWD/$OUT" &
pid=$!

(
  while kill -0 "$pid" 2>/dev/null; do
    update_progress
    sleep 60
  done
) &
ppid=$!

set +e
wait "$pid"
rc=$?
set -e
kill "$ppid" 2>/dev/null || true
wait "$ppid" 2>/dev/null || true
[[ "$rc" -eq 0 ]] || exit "$rc"
update_progress

python3 - <<'PY'
import struct
from pathlib import Path

frame = Path("artifacts/coimbra-036-preview/frames/frame_0001.png")
data = frame.read_bytes()
assert data[:8] == b"\x89PNG\r\n\x1a\n"
width, height = struct.unpack(">II", data[16:24])
assert [width, height] == [640, 480], (width, height)
print(f"verified first PNG: {width}x{height}")
PY

ffmpeg -y   -framerate 60   -start_number 1   -i "$OUT/frames/frame_%04d.png"   -frames:v 1440   -c:v libx264   -pix_fmt yuv420p   -crf 18   -preset medium   -movflags +faststart   "$OUT/coimbra-036-preview-640x480-60fps-smoothcam-24s.mp4"

ffprobe -v error   -count_frames   -select_streams v:0   -show_entries stream=codec_name,pix_fmt,width,height,r_frame_rate,nb_read_frames:format=duration   -of json   "$OUT/coimbra-036-preview-640x480-60fps-smoothcam-24s.mp4"   > "$OUT/ffprobe.json"

python3 - <<'PY'
import hashlib
import json
from pathlib import Path

root = Path("artifacts/coimbra-036-preview")
r = json.loads((root / "render-receipt.json").read_text())
p = json.loads((root / "ffprobe.json").read_text())
s = p["streams"][0]

assert [int(s["width"]), int(s["height"])] == [640, 480]
assert s["r_frame_rate"] == "60/1"
assert int(s["nb_read_frames"]) == 1440
assert r["camera_motion_model"] == "coimbra-033-smooth-camera-motion-review-v2"
assert r["anchor_source_frames"] == [1, 61, 121, 181, 241, 301, 360]
assert r["motion_metrics"]["candidate_033_smoothed"]["linear_step"]["cv"] < 0.01
assert r["motion_metrics"]["candidate_033_smoothed"]["linear_step"]["cv"] < r["motion_metrics"]["current_032_sampling"]["linear_step"]["cv"]

duration = float(p["format"]["duration"])
assert abs(duration - 24.0) < 0.1

video = root / "coimbra-036-preview-640x480-60fps-smoothcam-24s.mp4"
v = {
    "verified": True,
    "preview_only": True,
    "frame_count": 1440,
    "render_frame_count": 1440,
    "fps": 60,
    "duration_seconds": 24.0,
    "speed_ratio_vs_031": 0.5,
    "source_frame_step": r["source_frame_step"],
    "sampling": r["sampling"],
    "camera_motion_model": r["camera_motion_model"],
    "anchor_source_frames": r["anchor_source_frames"],
    "current_linear_cv": r["motion_metrics"]["current_032_sampling"]["linear_step"]["cv"],
    "smooth_linear_cv": r["motion_metrics"]["candidate_033_smoothed"]["linear_step"]["cv"],
    "current_angular_change_p95": r["motion_metrics"]["current_032_sampling"]["angular_step_change_radians"]["p95"],
    "smooth_angular_change_p95": r["motion_metrics"]["candidate_033_smoothed"]["angular_step_change_radians"]["p95"],
    "samples": 4,
    "adaptive_threshold": 0.15,
    "source_035_review_run": 36892916114,
    "quality64_promoted": False,
    "repeated_frames": False,
    "repeat_factor": 1,
    "resolution": [640, 480],
    "metal_total_seconds": r["total_seconds"],
    "metal_devices": r["metal_devices"],
    "video_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
    "source_030_blend_sha256": r["source_030_blend_sha256"],
    "source_030_structure_sha256": None,
    "source_030_protected_sha256": None,
}
(root / "verification.json").write_text(json.dumps(v, indent=2) + "\n")
PY

update_progress
rm -rf "$OUT/frames"
