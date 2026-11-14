"""LTX wrapper configuration (plan v1.3 §3). One served-variant setting drives
schema default, validation and /health. Queue depth is 1: one ComfyUI, one slot."""
import os
from pathlib import Path

COMFYUI_URL = os.environ.get("LTX_COMFYUI_URL", "http://localhost:8188")
COMFYUI_INPUT_DIR = Path(os.environ.get("LTX_COMFYUI_INPUT_DIR", "/home/jarvis/ComfyUI/input"))
STILLS_ROOT = Path(os.environ.get("LTX_STILLS_ROOT", "/home/jarvis/ltx-stills"))
OUTPUT_DIR = Path(os.environ.get("LTX_OUTPUT_DIR", str(Path.home() / ".local" / "share" / "ltx2.5" / "outputs")))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PORT = int(os.environ.get("LTX_PORT", "8766"))
MAX_QUEUE_DEPTH = 1
JOB_TIMEOUT_SECONDS = float(os.environ.get("LTX_JOB_TIMEOUT_SECONDS", "900"))
SERVED_VARIANT = os.environ.get("LTX_SERVED_VARIANT", "ltx-2.5-q3")
POLL_INTERVAL_SECONDS = 5.0
