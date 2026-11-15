#!/usr/bin/env bash
# Step 7 install (plan v1.3). Port deviation 8766 -> 8767 ruled by Jose
# 2026-11-14: 8766 is held by command-post's API on this host.
# Installs and STARTS ltx.service only. Does NOT enable it (enable happens
# only after the live smoke passes). Never touches wan2.2.service or
# comfyui.service. Run on the ROG: bash scripts/install-ltx-service.sh
set -euo pipefail
cd "$(dirname "$0")/.."
unit=systemd/ltx.service
[ -f "$unit" ] || { echo "FAIL: $unit missing"; exit 1; }
grep -q -- '--port 8767' "$unit" || { echo "FAIL: unit is not on the ruled port 8767"; exit 1; }
[ -x /home/jarvis/.venv/wan2.2/bin/python3 ] || { echo "FAIL: shared-runtime python missing"; exit 1; }

# Refuse to displace anything already on 8767.
if ss -tln | grep -q ':8767 '; then
  echo "FAIL: port 8767 already in use:"
  ss -tlnp | grep ':8767 '
  exit 1
fi

sudo cp "$unit" /etc/systemd/system/ltx.service
sudo systemctl daemon-reload
sudo systemctl start ltx.service
sleep 3
systemctl is-active ltx.service
curl -fsS -m 10 http://localhost:8767/health
echo
echo "--- network policy (bind alone is not proof) ---"
ss -tlnp | grep ':8767 '
sudo ufw status verbose | head -n 15
echo "INSTALL OK — ltx.service active on 8767 (NOT enabled). Live smoke is Jose's: bash scripts/ltx-smoke.sh"