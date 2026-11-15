"""Configuration from environment variables (plan v1.3 §3). One served-variant
setting drives schema default, validation and /health. Queue depth is 1: one
ComfyUI, one slot."""
import os
from pathlib import Path

HOST = os.getenv("WAN_SERVICE_HOST", "0.0.0.0")
PORT = int(os.getenv("WAN_SERVICE_PORT", "8765"))
SERVED_VARIANT = os.getenv("WAN_SERVED_VARIANT", "5b-gguf")
MODEL_PATH = Path(os.getenv("WAN_MODEL_PATH", str(Path.home() / "models" / "Wan2.2-TI2V-5B")))
T5_DEVICE = os.getenv("WAN_T5_DEVICE", "cpu")
COMFYUI_URL = os.getenv("WAN_COMFYUI_URL", "http://localhost:8188")
COMFYUI_INPUT_DIR = Path(os.getenv("WAN_COMFYUI_INPUT_DIR", "/home/jarvis/ComfyUI/input"))
STILLS_ROOT = Path(os.getenv("WAN_STILLS_ROOT", "/home/jarvis/wan-stills"))
OUTPUT_DIR = Path(os.getenv("WAN_OUTPUT_DIR", str(Path.home() / ".local" / "share" / "wan2.2" / "outputs")))
CALIBRATION_PATH = Path(os.getenv("WAN_CALIBRATION_PATH", str(Path.home() / ".local" / "share" / "wan2.2" / "calibration.json")))
OUTPUT_RETENTION_HOURS = int(os.getenv("WAN_OUTPUT_RETENTION_HOURS", "24"))
MAX_QUEUE_DEPTH = 1
JOB_TIMEOUT_SECONDS = int(os.getenv("WAN_JOB_TIMEOUT_SECONDS", "600"))
GPU_IDS = [int(x) for x in os.getenv("WAN_GPU_IDS", "0,1").split(",")]
POLL_INTERVAL_SECONDS = 5.0
PROGRESS_WS_ENABLED = os.getenv("WAN_PROGRESS_WS", "1") == "1"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)