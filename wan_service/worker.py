"""GPU worker with ComfyUI backend for Wan2.2 video generation."""
import asyncio
import json
import random
import time
import urllib.request
import urllib.parse
import uuid

try:
    import websocket  # websocket-client, shipped with ComfyUI
except ImportError:  # progress falls back to a time-based estimate
    websocket = None
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import MAX_QUEUE_DEPTH, JOB_TIMEOUT_SECONDS, GPU_IDS
from .schemas import GenerateRequest


COMFYUI_URL = "http://localhost:8188"

# Calibrated 2026-10-18 on 2x RTX 5060 Ti: 17 frames x 25 steps at 704x1280 took
# 280 s end-to-end. The CPU T5 encode is inside the fixed overhead term.
ESTIMATE_BASE_SECONDS = 40.0
# Starting point measured 2026-10-18: 347 s for 17f x 10 steps at 704x1280.
# The estimate self-calibrates from every completed job, because the CPU T5
# encode dominates and varies with cold/warm model state.
DEFAULT_SECONDS_PER_UNIT = 2.0e-6
CALIBRATION_PATH = Path.home() / ".local" / "share" / "wan2.2" / "calibration.json"


def workload_units(request) -> float:
    frames = request.num_frames or 97
    steps = request.num_inference_steps or 50
    width = request.width or 1280
    height = request.height or 720
    return float(frames) * float(steps) * float(width) * float(height)


def _read_ratio() -> float:
    try:
        data = json.loads(CALIBRATION_PATH.read_text())
        ratio = float(data["seconds_per_unit"])
        return ratio if ratio > 0 else DEFAULT_SECONDS_PER_UNIT
    except Exception:
        return DEFAULT_SECONDS_PER_UNIT


def _write_ratio(ratio: float) -> None:
    try:
        CALIBRATION_PATH.parent.mkdir(parents=True, exist_ok=True)
        CALIBRATION_PATH.write_text(json.dumps({"seconds_per_unit": ratio}))
    except Exception:
        pass


def record_runtime(request, elapsed_seconds: float) -> None:
    """Fold an observed runtime into the calibration ratio (EMA, alpha=0.5)."""
    units = workload_units(request)
    if units <= 0 or elapsed_seconds <= 0:
        return
    observed = elapsed_seconds / units
    _write_ratio(0.5 * _read_ratio() + 0.5 * observed)


def estimate_seconds(request) -> int:
    """Estimate wall-clock seconds from the workload and observed runtimes."""
    return max(60, int(ESTIMATE_BASE_SECONDS + workload_units(request) * _read_ratio()))


class Job:
    def __init__(self, job_id: str, request: GenerateRequest, gpu_id: int):
        self.job_id = job_id
        self.request = request
        self.gpu_id = gpu_id
        self.status = "queued"
        self.progress = 0.0
        self.error = None
        self.started_at = None
        self.completed_at = None
        self.output_path = None
        self.comfy_prompt_id = None
        self.output_filename = None
        self.output_subfolder = ""
        self.output_type = "output"
        self.created_at = datetime.now(timezone.utc).isoformat()


class ComfyUIClient:
    """Minimal ComfyUI HTTP client."""

    def __init__(self, base_url=COMFYUI_URL):
        self.base_url = base_url.rstrip("/")

    def submit_workflow(self, workflow: dict) -> str:
        data = json.dumps({"prompt": workflow}).encode()
        req = urllib.request.Request(
            f"{self.base_url}/prompt",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())
        return result["prompt_id"]

    def get_status(self, prompt_id: str) -> dict:
        try:
            req = urllib.request.urlopen(f"{self.base_url}/history/{prompt_id}", timeout=10)
            history = json.loads(req.read())
            if prompt_id in history:
                entry = history[prompt_id]
                status = entry.get("status", {})
                if status.get("completed", False):
                    outputs = entry.get("outputs", {})
                    # Find video output
                    for node_id, node_output in outputs.items():
                        if "images" in node_output:  # ComfyUI calls video outputs "images"
                            for item in node_output["images"]:
                                if item.get("metadata", {}).get("kind") == "video" or item.get("filename", "").endswith(".mp4"):
                                    return {"status": "completed", "filename": item["filename"],
                                            "subfolder": item.get("subfolder", ""),
                                            "type": item.get("type", "output")}
                    # Fallback: any output file
                    for node_id, node_output in outputs.items():
                        if "images" in node_output:
                            for item in node_output["images"]:
                                return {"status": "completed", "filename": item["filename"],
                                        "subfolder": item.get("subfolder", ""),
                                        "type": item.get("type", "output")}
                    return {"status": "completed", "filename": None}
                if status.get("status_str") == "error":
                    msgs = status.get("messages", [])
                    err = msgs[-1][1].get("exception_message", "unknown") if msgs else "unknown"
                    return {"status": "failed", "error": err}
                return {"status": "processing"}
            return {"status": "queued"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def download_output(self, filename: str, subfolder: str = "", output_type: str = "output") -> bytes:
        params = urllib.parse.urlencode({
            "filename": filename,
            "subfolder": subfolder,
            "type": output_type,
        })
        req = urllib.request.urlopen(f"{self.base_url}/view?{params}", timeout=120)
        return req.read()

    def health(self) -> bool:
        try:
            req = urllib.request.urlopen(f"{self.base_url}/system_stats", timeout=5)
            return req.status == 200
        except Exception:
            return False

    def interrupt(self):
        try:
            data = b""
            req = urllib.request.Request(f"{self.base_url}/interrupt", data=data, method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass


def build_wan22_workflow(prompt: str, negative_prompt: str = "", width: int = 704, height: int = 1280,
                          num_frames: int = 17, steps: int = 10, seed: int = None) -> dict:
    """Build a ComfyUI workflow for Wan2.2 5B via GGUF. Produces MP4 video."""
    if seed is None:
        seed = random.randint(0, 2**32 - 1)

    return {
        "1": {
            "class_type": "WanVideoModelLoader",
            "inputs": {
                "model": "Wan2.2-TI2V-5B-Q8_0.gguf",
                "base_precision": "fp16",
                "quantization": "disabled",
                "load_device": "offload_device"
            }
        },
        "2": {
            "class_type": "WanVideoVAELoader",
            "inputs": {
                "model_name": "Wan2.2_VAE.safetensors",
                "precision": "fp16"
            }
        },
        "3": {
            "class_type": "LoadWanVideoT5TextEncoder",
            "inputs": {
                "model_name": "models_t5_umt5-xxl-enc-bf16.pth",
                "precision": "bf16",
                "load_device": "offload_device"
            }
        },
        "4": {
            "class_type": "WanVideoTextEncode",
            "inputs": {
                "positive_prompt": prompt,
                "negative_prompt": negative_prompt or "blurry, low quality, distorted",
                "t5": ["3", 0],
                "force_offload": True,
                "model_to_offload": ["1", 0],
                "device": "cpu"
            }
        },
        "5": {
            "class_type": "WanVideoEmptyEmbeds",
            "inputs": {
                "width": width,
                "height": height,
                "num_frames": num_frames
            }
        },
        "6": {
            "class_type": "WanVideoSampler",
            "inputs": {
                "model": ["1", 0],
                "image_embeds": ["5", 0],
                "text_embeds": ["4", 0],
                "steps": steps,
                "cfg": 5.0,
                "shift": 5.0,
                "seed": seed,
                "force_offload": True,
                "scheduler": "unipc",
                "riflex_freq_index": 0
            }
        },
        "7": {
            "class_type": "WanVideoDecode",
            "inputs": {
                "vae": ["2", 0],
                "samples": ["6", 0],
                "enable_vae_tiling": True,
                "tile_x": 272,
                "tile_y": 272,
                "tile_stride_x": 144,
                "tile_stride_y": 128
            }
        },
        "8": {
            "class_type": "CreateVideo",
            "inputs": {
                "images": ["7", 0],
                "fps": 24.0
            }
        },
        "9": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["8", 0],
                "filename_prefix": "wan22_output",
                "format": "mp4",
                "codec": "h264"
            }
        }
    }


class GpuWorker:
    """Manages a single GPU's job queue via ComfyUI."""

    def __init__(self, gpu_id: int):
        self.gpu_id = gpu_id
        self.client = ComfyUIClient()
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE_DEPTH)
        self.current_job: Optional[Job] = None
        self.busy = False
        self._task = None

    async def start(self):
        self._task = asyncio.create_task(self._process_loop())

    async def _process_loop(self):
        while True:
            job = await self.queue.get()
            self.busy = True
            self.current_job = job
            job.status = "processing"
            job.started_at = datetime.now(timezone.utc).isoformat()
            try:
                loop = asyncio.get_event_loop()
                await asyncio.wait_for(
                    loop.run_in_executor(None, self._run_generation, job),
                    timeout=JOB_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                job.status = "failed"
                job.error = "generation_timeout"
            except Exception as e:
                job.status = "failed"
                job.error = str(e)
            finally:
                job.completed_at = datetime.now(timezone.utc).isoformat()
                self.busy = False
                self.current_job = None

    def _open_progress_socket(self):
        """Open a ComfyUI websocket; None if unavailable (time-based fallback)."""
        if websocket is None:
            return None
        try:
            ws = websocket.create_connection(
                f"ws://localhost:8188/ws?clientId={uuid.uuid4().hex}", timeout=5
            )
            ws.settimeout(0.2)
            return ws
        except Exception:
            return None

    def _pump_progress(self, ws, prompt_id: str, job: Job, elapsed: float, estimated: float):
        """Drain buffered websocket messages and update job.progress in place."""
        if ws is not None:
            for _ in range(50):
                try:
                    message = json.loads(ws.recv())
                except Exception:
                    break
                if message.get("type") == "progress":
                    data = message.get("data", {})
                    if data.get("prompt_id") in (None, prompt_id) and data.get("max"):
                        value = float(data["value"]) / float(data["max"]) * 0.95
                        job.progress = max(job.progress, min(0.95, value))
        if job.progress < 0.02:
            job.progress = min(0.90, 0.90 * elapsed / max(estimated, 1.0))

    def _close_progress_socket(self, ws):
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def _run_generation(self, job: Job):
        req = job.request
        workflow = build_wan22_workflow(
            prompt=req.prompt,
            negative_prompt=req.negative_prompt,
            width=req.width or 704,
            height=req.height or 1280,
            num_frames=req.num_frames or 17,
            steps=req.num_inference_steps or 10,
            seed=req.seed,
        )
        prompt_id = self.client.submit_workflow(workflow)
        job.comfy_prompt_id = prompt_id

        started = time.time()
        estimated = float(estimate_seconds(req))
        progress_ws = self._open_progress_socket()

        # Poll for completion
        for _ in range(JOB_TIMEOUT_SECONDS // 5):
            if job.status == "cancelled":
                self.client.interrupt()
                self._close_progress_socket(progress_ws)
                job.status = "failed"
                job.error = "cancelled"
                return
            self._pump_progress(progress_ws, prompt_id, job, time.time() - started, estimated)
            status = self.client.get_status(prompt_id)
            if status["status"] == "completed":
                job.output_filename = status.get("filename")
                job.output_subfolder = status.get("subfolder", "")
                job.output_type = status.get("type", "output")
                # Download output
                if job.output_filename:
                    data = self.client.download_output(
                        job.output_filename, job.output_subfolder, job.output_type
                    )
                    # Save to local file
                    output_path = Path.home() / ".local" / "share" / "wan2.2" / "outputs" / f"{job.job_id}.mp4"
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(data)
                    job.output_path = str(output_path)
                record_runtime(req, time.time() - started)
                self._close_progress_socket(progress_ws)
                job.status = "completed"
                job.progress = 1.0
                return
            elif status["status"] == "failed":
                self._close_progress_socket(progress_ws)
                job.status = "failed"
                job.error = status.get("error", "generation_failed")
                return
            time.sleep(5)

        self._close_progress_socket(progress_ws)
        job.status = "failed"
        job.error = "generation_timeout"

    async def submit(self, request: GenerateRequest) -> Job:
        job_id = "gen-{}".format(uuid.uuid4())
        job = Job(job_id, request, self.gpu_id)
        await self.queue.put(job)
        return job

    def queue_depth(self) -> int:
        return self.queue.qsize()

    def status(self) -> dict:
        return {
            "id": self.gpu_id,
            "model": "5b-gguf",
            "loaded": self.client.health(),
            "busy": self.busy,
            "vram_used_gb": 0.0,
            "vram_total_gb": 16.0,
        }


class WorkerPool:
    """Manages multiple GPU workers with round-robin assignment."""

    def __init__(self, gpu_ids):
        self.workers = [GpuWorker(gid) for gid in gpu_ids]
        self.jobs: dict[str, Job] = {}

    async def start(self):
        for w in self.workers:
            await w.start()

    async def submit(self, request: GenerateRequest) -> Job:
        worker = min(self.workers, key=lambda w: w.queue_depth())
        if worker.queue_depth() >= MAX_QUEUE_DEPTH:
            raise RuntimeError("queue_full")
        job = await worker.submit(request)
        self.jobs[job.job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

    def total_queue_depth(self) -> int:
        return sum(w.queue_depth() for w in self.workers)

    def health(self) -> list[dict]:
        return [w.status() for w in self.workers]
