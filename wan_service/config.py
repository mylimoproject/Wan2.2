"""Configuration from environment variables."""
import os
from pathlib import Path

HOST = os.getenv("WAN_SERVICE_HOST", "0.0.0.0")
PORT = int(os.getenv("WAN_SERVICE_PORT", "8765"))
MODEL_VARIANT = os.getenv("WAN_MODEL_VARIANT", "5b")
MODEL_PATH = Path(os.getenv("WAN_MODEL_PATH", str(Path.home() / "models" / "Wan2.2-TI2V-5B")))
T5_DEVICE = os.getenv("WAN_T5_DEVICE", "cpu")
OUTPUT_DIR = Path(os.getenv("WAN_OUTPUT_DIR", str(Path.home() / ".local" / "share" / "wan2.2" / "outputs")))
OUTPUT_RETENTION_HOURS = int(os.getenv("WAN_OUTPUT_RETENTION_HOURS", "24"))
MAX_QUEUE_DEPTH = int(os.getenv("WAN_MAX_QUEUE_DEPTH", "10"))
JOB_TIMEOUT_SECONDS = int(os.getenv("WAN_JOB_TIMEOUT_SECONDS", "600"))
GPU_IDS = [int(x) for x in os.getenv("WAN_GPU_IDS", "0,1").split(",")]

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
