#!/usr/bin/env bash
# WAN I2V live smoke — plan v1.3 Step 8, AFTER the Jose-confirmed restart onto
# the upgraded code. Jose-authorized generation. 17 frames, 10 steps, request
# 1280x720 (wrapper generates 1280x736 and center-crops 8 px/side to exact).
# Checks: /health interlock, 202, terminal status, ffprobe (h264, exact
# 1280x720; WAN's graph has no audio), sha256 recorded in a receipt.
# Usage (on the ROG): bash scripts/wan-i2v-smoke.sh [still-name]
#   still-name is relative to WAN_STILLS_ROOT (default /home/jarvis/wan-stills)
# DRY_RUN=1 prints the request and exits WITHOUT generating.
set -euo pipefail

BASE="${WAN_SMOKE_URL:-http://localhost:8765}"
STILLS_ROOT="${WAN_STILLS_ROOT:-/home/jarvis/wan-stills}"
STILL="${1:-locksmith-van-front.png}"
SEED="${WAN_SMOKE_SEED:-42}"
RECEIPTS="${WAN_SMOKE_RECEIPTS:-$HOME/wan-smoke-receipts}"
POLL_SECONDS="${WAN_SMOKE_TIMEOUT:-1200}"

command -v curl >/dev/null || { echo "FAIL: curl missing"; exit 1; }
command -v ffprobe >/dev/null || { echo "FAIL: ffprobe missing"; exit 1; }
command -v sha256sum >/dev/null || { echo "FAIL: sha256sum missing"; exit 1; }
command -v python3 >/dev/null || { echo "FAIL: python3 missing"; exit 1; }

still_file="$STILLS_ROOT/$STILL"
[ -f "$still_file" ] || { echo "FAIL: still not found: $still_file"; exit 1; }
sha=$(sha256sum "$still_file" | cut -d' ' -f1)

req=$(cat <<JSON
{"prompt":"The white van parked in the sunny lot, subtle natural motion, gentle stationary handheld camera. No text or logos.","negative_prompt":"blurry, low quality, distorted","image_path":"$STILL","image_sha256":"$sha","width":1280,"height":720,"num_frames":17,"fps":24,"num_inference_steps":10,"guidance_scale":5.0,"seed":$SEED,"model_variant":"5b-gguf","output_format":"mp4"}
JSON
)

echo "== WAN I2V smoke: $BASE still=$STILL seed=$SEED =="
echo "still sha256: $sha"
if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "DRY_RUN request:"
  echo "$req"
  echo "DRY_RUN: no generation submitted."
  exit 0
fi

health=$(curl -fsS -m 10 "$BASE/health") || { echo "FAIL: /health not 2xx — is the upgraded WAN wrapper running and ComfyUI idle?"; exit 1; }
echo "health: $health"

out=$(curl -sS -m 60 -X POST "$BASE/generate" -H 'Content-Type: application/json' -d "$req" -w '\n%{http_code}')
code="${out##*$'\n'}"
body="${out%$'\n'*}"
[ "$code" = "202" ] || { echo "FAIL: /generate answered $code: $body"; exit 1; }
job_id=$(printf '%s' "$body" | python3 -c 'import json,sys; print(json.load(sys.stdin)["job_id"])')
echo "job: $job_id — polling every 10 s (timeout ${POLL_SECONDS}s)"

end=$(( $(date +%s) + POLL_SECONDS ))
while :; do
  st=$(curl -fsS -m 15 "$BASE/status/$job_id")
  status=$(printf '%s' "$st" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  case "$status" in
    completed) break ;;
    failed) echo "FAIL: job failed: $st"; exit 1 ;;
  esac
  [ "$(date +%s)" -lt "$end" ] || { echo "FAIL: smoke timeout; job=$job_id last=$st"; exit 1; }
  sleep 10
done

ts=$(date +%Y%m%dT%H%M%S)
dir="$RECEIPTS/$ts"
mkdir -p "$dir"
curl -fsS -m 120 "$BASE/output/$job_id" -o "$dir/clip.mp4"
ffprobe -v error -show_entries stream=codec_name,codec_type,width,height -of json "$dir/clip.mp4" > "$dir/ffprobe.json"
clip_sha=$(sha256sum "$dir/clip.mp4" | cut -d' ' -f1)

python3 - "$dir/ffprobe.json" <<'PY'
import json, sys
streams = json.load(open(sys.argv[1]))["streams"]
v = [x for x in streams if x["codec_type"] == "video"]
assert v and v[0]["codec_name"] == "h264", f"video codec: {v}"
assert (v[0]["width"], v[0]["height"]) == (1280, 720), f"dims: {v}"
print("ffprobe OK: h264 exact 1280x720 (WAN graph carries no audio)")
PY

{
  echo "WAN I2V smoke receipt (plan v1.3 Step 8) — $(date -Is)"
  echo "base: $BASE"
  echo "still: $STILL sha256=$sha"
  echo "request: $req"
  echo "job_id: $job_id"
  echo "final status: $st"
  echo "clip sha256: $clip_sha"
  echo "ffprobe: $(cat "$dir/ffprobe.json")"
} > "$dir/receipt.txt"

echo "PASS — clip: $dir/clip.mp4"
echo "clip sha256: $clip_sha"
echo "receipt: $dir/receipt.txt"