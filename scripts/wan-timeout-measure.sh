#!/usr/bin/env bash
# Step 8 timeout gate (plan v1.3 C7) — LIVE measurement, Jose-authorized.
# Measures a mid-size landscape T2V job through the STILL-LIVE old WAN wrapper
# (3a4b80b code, :8765) at the 32-grid 1280x736 shape, then extrapolates to the
# HG-2 workload (97 frames x 50 steps @ generated 1280x736 — the engine's S4L
# params) and proposes WAN_JOB_TIMEOUT_SECONDS >= 2x the extrapolated time,
# rounded up to a 300 s boundary. The old wrapper's own timeout is 600 s; this
# job is sized to finish well under it (~220 s at the live calibration ratio).
# Usage (on the ROG): bash scripts/wan-timeout-measure.sh
# DRY_RUN=1 prints the request and exits WITHOUT generating.
set -euo pipefail

BASE="${WAN_MEASURE_URL:-http://localhost:8765}"
COMFY="${WAN_MEASURE_COMFY:-http://localhost:8188}"
RECEIPTS="${WAN_MEASURE_RECEIPTS:-$HOME/wan-timeout-receipts}"
FRAMES=33
STEPS=20
WIDTH=1280
HEIGHT=736
SEED=42
GUARD_SECONDS=660   # old wrapper timeout 600 s + polling margin

command -v curl >/dev/null || { echo "FAIL: curl missing"; exit 1; }
command -v python3 >/dev/null || { echo "FAIL: python3 missing"; exit 1; }

req=$(cat <<JSON
{"prompt":"A quiet suburban street at golden hour, parked cars, gentle handheld camera drift. No text or logos.","negative_prompt":"blurry, low quality, distorted","width":$WIDTH,"height":$HEIGHT,"num_frames":$FRAMES,"fps":24,"num_inference_steps":$STEPS,"guidance_scale":5.0,"seed":$SEED,"model_variant":"5b-gguf","output_format":"mp4"}
JSON
)

echo "== WAN timeout measurement: $BASE ${WIDTH}x${HEIGHT} ${FRAMES}f x ${STEPS} steps seed=$SEED =="
if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "DRY_RUN request:"
  echo "$req"
  echo "DRY_RUN: no generation submitted."
  exit 0
fi

# One generator at a time: the OLD wrapper has no interlock, so check ComfyUI directly.
q=$(curl -fsS -m 10 "$COMFY/queue")
busy=$(printf '%s' "$q" | python3 -c 'import json,sys; q=json.load(sys.stdin); print(len(q.get("queue_running",[]))+len(q.get("queue_pending",[])))')
[ "$busy" = "0" ] || { echo "FAIL: ComfyUI queue not empty ($busy entries) — wait for idle"; exit 1; }
curl -fsS -m 10 "$BASE/health" >/dev/null || { echo "FAIL: old WAN wrapper /health not 2xx"; exit 1; }

start=$(date +%s)
out=$(curl -sS -m 60 -X POST "$BASE/generate" -H 'Content-Type: application/json' -d "$req" -w '\n%{http_code}')
code="${out##*$'\n'}"
body="${out%$'\n'*}"
[ "$code" = "202" ] || { echo "FAIL: /generate answered $code: $body"; exit 1; }
job_id=$(printf '%s' "$body" | python3 -c 'import json,sys; print(json.load(sys.stdin)["job_id"])')
est=$(printf '%s' "$body" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("estimated_seconds","?"))')
echo "job: $job_id (wrapper estimate: ${est}s) — polling every 10 s (guard ${GUARD_SECONDS}s)"

end=$(( start + GUARD_SECONDS ))
while :; do
  st=$(curl -fsS -m 15 "$BASE/status/$job_id")
  status=$(printf '%s' "$st" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  case "$status" in
    completed) break ;;
    failed) echo "FAIL: job failed: $st"; exit 1 ;;
  esac
  [ "$(date +%s)" -lt "$end" ] || { echo "FAIL: measurement guard exceeded; job=$job_id last=$st"; exit 1; }
  sleep 10
done
elapsed=$(( $(date +%s) - start ))

ts=$(date +%Y%m%dT%H%M%S)
dir="$RECEIPTS/$ts"
mkdir -p "$dir"
python3 - "$elapsed" "$dir/receipt.txt" <<PY
import math, sys
elapsed = int(sys.argv[1])
units_meas = $FRAMES * $STEPS * $WIDTH * $HEIGHT
units_hg2 = 97 * 50 * 1280 * 736   # engine S4L params at the GENERATED shape
base = 20.0                        # wrapper ESTIMATE_BASE_SECONDS
r = max(elapsed - base, 1.0) / units_meas
hg2 = base + units_hg2 * r
proposed = int(math.ceil(2 * hg2 / 300.0) * 300)
lines = [
    "WAN timeout measurement receipt (plan v1.3 Step 8, C7)",
    "request: $req",
    "job_id: $job_id",
    "wrapper_estimate_seconds: $est",
    "measured_elapsed_seconds: $elapsed (wall clock, 10 s poll granularity — conservative)",
    "measured_units: %d" % units_meas,
    "derived_seconds_per_unit: %.6e" % r,
    "hg2_units: %d (97f x 50 steps @ 1280x736 generated)" % units_hg2,
    "hg2_extrapolated_seconds: %.0f" % hg2,
    "PROPOSED_WAN_JOB_TIMEOUT_SECONDS: %d (>= 2x extrapolated, 300 s boundary)" % proposed,
]
text = "\n".join(lines) + "\n"
open(sys.argv[2], "w").write(text)
print(text)
PY
echo "receipt: $dir/receipt.txt"