# PEER EVIDENCE — captured 2026-11-14 from jarvis-rog-x570 (read-only)

## wan_service/config.py
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

## wan_service/schemas.py
"""Pydantic request/response schemas."""
from typing import Optional
from pydantic import BaseModel


class GenerateRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = None
    image_path: Optional[str] = None
    width: int = 1280
    height: int = 720
    num_frames: int = 97
    fps: int = 24
    num_inference_steps: int = 50
    guidance_scale: float = 5.0
    seed: Optional[int] = None
    model_variant: str = "5b"
    output_format: str = "mp4"


class GenerateResponse(BaseModel):
    job_id: str
    status: str = "queued"
    gpu: int
    estimated_seconds: int = 180


class StatusResponse(BaseModel):
    job_id: str
    status: str
    progress: float = 0.0
    gpu: int
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class GpuStatus(BaseModel):
    id: int
    model: str
    loaded: bool
    busy: bool
    vram_used_gb: float
    vram_total_gb: float


class HealthResponse(BaseModel):
    status: str
    gpus: list[GpuStatus]
    queue_depth: int
    version: str = "0.1.0"


class ErrorResponse(BaseModel):
    error: str
    detail: str
    job_id: Optional[str] = None

## wan_service/main.py
"""FastAPI application for Wan2.2 local video generation."""
import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .config import HOST, PORT, MODEL_PATH, GPU_IDS
from .schemas import GenerateRequest, GenerateResponse, StatusResponse, HealthResponse, GpuStatus, ErrorResponse
from .worker import WorkerPool, estimate_seconds


pool: WorkerPool = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = WorkerPool(GPU_IDS)
    await pool.start()
    yield
    # cleanup on shutdown


app = FastAPI(title="Wan2.2 Video Service", version="0.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
async def health():
    gpus = [GpuStatus(**g) for g in pool.health()]
    return HealthResponse(
        status="ok",
        gpus=gpus,
        queue_depth=pool.total_queue_depth(),
    )


@app.post("/generate", response_model=GenerateResponse, status_code=202)
async def generate(req: GenerateRequest):
    try:
        job = await pool.submit(req)
    except RuntimeError as e:
        if str(e) == "queue_full":
            raise HTTPException(status_code=429, detail="Queue full")
        raise HTTPException(status_code=503, detail=str(e))
    return GenerateResponse(
        job_id=job.job_id,
        status=job.status,
        gpu=job.gpu_id,
        estimated_seconds=estimate_seconds(req),
    )


@app.get("/status/{job_id}", response_model=StatusResponse)
async def status(job_id: str):
    job = pool.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return StatusResponse(
        job_id=job.job_id,
        status=job.status,
        progress=job.progress,
        gpu=job.gpu_id,
        error=job.error,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@app.get("/output/{job_id}")
async def output(job_id: str):
    job = pool.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed":
        raise HTTPException(status_code=404, detail="Output not ready")
    if not job.output_path or not Path(job.output_path).exists():
        raise HTTPException(status_code=404, detail="Output file missing")
    return FileResponse(job.output_path, media_type="video/mp4", filename="{}.mp4".format(job_id))


@app.post("/cancel/{job_id}")
async def cancel(job_id: str):
    job = pool.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in ("completed", "failed"):
        raise HTTPException(status_code=409, detail="Job already finished")
    job.status = "cancelled"
    return {"cancelled": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, workers=1)

## wan_service/worker.py
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
PROGRESS_NODE_ID = "6"  # WanVideoSampler node in build_wan22_workflow

# Calibrated 2026-10-18 on 2x RTX 5060 Ti: 17 frames x 25 steps at 704x1280 took
# 280 s end-to-end. The CPU T5 encode is inside the fixed overhead term.
ESTIMATE_BASE_SECONDS = 20.0
# Starting point measured 2026-10-18: 347 s for 17f x 10 steps at 704x1280.
# The estimate self-calibrates from every completed job, because the CPU T5
# encode dominates and varies with cold/warm model state.
DEFAULT_SECONDS_PER_UNIT = 2.5e-7
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
                "use_disk_cache": True,
                "device": "gpu"
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
            for _ in range(5):
                try:
                    message = json.loads(ws.recv())
                except Exception:
                    break
                if message.get("type") == "progress":
                    data = message.get("data", {})
                    if (
                        data.get("node") == PROGRESS_NODE_ID
                        and data.get("prompt_id") in (None, prompt_id)
                        and data.get("max")
                    ):
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

## proven LTX Q3 I2V API graph (q3-default-i2v-pilot-1088x1920-api.json)
{
  "client_id": "hermes-ltx25-smoke",
  "prompt": {
    "1": {
      "class_type": "UnetLoaderGGUF",
      "inputs": {
        "unet_name": "ltx-2.5-22b-distilled-UD-Q3_K_XL.gguf"
      }
    },
    "2": {
      "class_type": "CLIPLoader",
      "inputs": {
        "clip_name": "gemma4-12b-with-proj-ltx-2.5-nvfp4.safetensors",
        "type": "ltxv",
        "device": "default"
      }
    },
    "3": {
      "class_type": "CLIPTextEncode",
      "inputs": {
        "text": "The woman stands by the white SUV in the sunny parking lot and briefly checks her phone. Subtle natural movements and a gentle stationary handheld camera. Maintain her appearance, outfit, and the car. No text or logos.",
        "clip": [
          "2",
          0
        ]
      }
    },
    "4": {
      "class_type": "CLIPTextEncode",
      "inputs": {
        "text": "blurry, distorted, cartoon",
        "clip": [
          "2",
          0
        ]
      }
    },
    "5": {
      "class_type": "LTXVConditioning",
      "inputs": {
        "positive": [
          "3",
          0
        ],
        "negative": [
          "4",
          0
        ],
        "frame_rate": 24.0
      }
    },
    "6": {
      "class_type": "VAELoader",
      "inputs": {
        "vae_name": "ltx-2.5-video-vae-conv-bf16.safetensors"
      }
    },
    "7": {
      "class_type": "VAELoader",
      "inputs": {
        "vae_name": "ltx-2.5-audio-vae-bf16.safetensors"
      }
    },
    "8": {
      "class_type": "EmptyLTXVLatentVideo",
      "inputs": {
        "width": 544,
        "height": 960,
        "length": 121,
        "batch_size": 1
      }
    },
    "9": {
      "class_type": "LTXVEmptyLatentAudio",
      "inputs": {
        "frames_number": 121,
        "frame_rate": 24,
        "batch_size": 1,
        "audio_vae": [
          "7",
          0
        ]
      }
    },
    "10": {
      "class_type": "LTXVConcatAVLatent",
      "inputs": {
        "video_latent": [
          "33",
          0
        ],
        "audio_latent": [
          "9",
          0
        ]
      }
    },
    "11": {
      "class_type": "LTXVDualCFGGuider",
      "inputs": {
        "model": [
          "1",
          0
        ],
        "positive": [
          "5",
          0
        ],
        "negative": [
          "5",
          1
        ],
        "video_cfg": 1.0,
        "audio_cfg": 1.0
      }
    },
    "12": {
      "class_type": "RandomNoise",
      "inputs": {
        "noise_seed": 42
      }
    },
    "13": {
      "class_type": "KSamplerSelect",
      "inputs": {
        "sampler_name": "euler_ancestral"
      }
    },
    "14": {
      "class_type": "ManualSigmas",
      "inputs": {
        "sigmas": "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"
      }
    },
    "15": {
      "class_type": "SamplerCustomAdvanced",
      "inputs": {
        "noise": [
          "12",
          0
        ],
        "guider": [
          "11",
          0
        ],
        "sampler": [
          "13",
          0
        ],
        "sigmas": [
          "14",
          0
        ],
        "latent_image": [
          "10",
          0
        ]
      }
    },
    "16": {
      "class_type": "LTXVSeparateAVLatent",
      "inputs": {
        "av_latent": [
          "15",
          0
        ]
      }
    },
    "17": {
      "class_type": "VAEDecodeTiled",
      "inputs": {
        "samples": [
          "27",
          0
        ],
        "vae": [
          "6",
          0
        ],
        "tile_size": 256,
        "overlap": 64,
        "temporal_size": 64,
        "temporal_overlap": 16
      }
    },
    "18": {
      "class_type": "LTXVAudioVAEDecode",
      "inputs": {
        "samples": [
          "27",
          1
        ],
        "audio_vae": [
          "7",
          0
        ]
      }
    },
    "19": {
      "class_type": "CreateVideo",
      "inputs": {
        "images": [
          "17",
          0
        ],
        "audio": [
          "18",
          0
        ],
        "fps": 24.0
      }
    },
    "20": {
      "class_type": "SaveVideo",
      "inputs": {
        "video": [
          "19",
          0
        ],
        "filename_prefix": "ltx25-hermes-hires/q3-default-i2v-pilot-1088x1920",
        "format": "auto",
        "codec": "h264"
      }
    },
    "21": {
      "class_type": "LatentUpscaleModelLoader",
      "inputs": {
        "model_name": "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors"
      }
    },
    "22": {
      "class_type": "LTXVLatentUpsampler",
      "inputs": {
        "samples": [
          "16",
          0
        ],
        "upscale_model": [
          "21",
          0
        ],
        "vae": [
          "6",
          0
        ]
      }
    },
    "23": {
      "class_type": "LTXVConcatAVLatent",
      "inputs": {
        "video_latent": [
          "34",
          0
        ],
        "audio_latent": [
          "16",
          1
        ]
      }
    },
    "24": {
      "class_type": "RandomNoise",
      "inputs": {
        "noise_seed": 42
      }
    },
    "25": {
      "class_type": "ManualSigmas",
      "inputs": {
        "sigmas": "0.85, 0.7250, 0.4219, 0.0"
      }
    },
    "26": {
      "class_type": "SamplerCustomAdvanced",
      "inputs": {
        "noise": [
          "24",
          0
        ],
        "guider": [
          "11",
          0
        ],
        "sampler": [
          "13",
          0
        ],
        "sigmas": [
          "25",
          0
        ],
        "latent_image": [
          "23",
          0
        ]
      }
    },
    "27": {
      "class_type": "LTXVSeparateAVLatent",
      "inputs": {
        "av_latent": [
          "26",
          0
        ]
      }
    },
    "31": {
      "class_type": "LoadImage",
      "inputs": {
        "image": "locksmith-pilot-reference-front.png"
      }
    },
    "32": {
      "class_type": "LTXVPreprocess",
      "inputs": {
        "image": [
          "31",
          0
        ],
        "img_compression": 18
      }
    },
    "33": {
      "class_type": "LTXVImgToVideoInplace",
      "inputs": {
        "vae": [
          "6",
          0
        ],
        "image": [
          "32",
          0
        ],
        "latent": [
          "8",
          0
        ],
        "strength": 0.7,
        "bypass": false
      }
    },
    "34": {
      "class_type": "LTXVImgToVideoInplace",
      "inputs": {
        "vae": [
          "6",
          0
        ],
        "image": [
          "32",
          0
        ],
        "latent": [
          "22",
          0
        ],
        "strength": 1.0,
        "bypass": false
      }
    }
  }
}

## verified peer facts (2026-11-14 probes)
- nvidia-smi topo -p2p r/w: CNS both directions (no P2P)
- custom_nodes: ComfyUI-GGUF, ComfyUI-WanVideoWrapper, websocket_image_save.py ONLY (no Raylight/MultiGPU/LTX2-MultiGPU)
- venv /home/jarvis/.venv/wan2.2: torch 2.11.0+cu128, triton 3.6.0; NO ray, NO sageattention
- models present: unet/ltx-2.5-22b-distilled-UD-Q3_K_XL.gguf + Q4_K_XL; diffusion_models/Wan2.2-TI2V-5B-Q8_0.gguf; text_encoders/gemma4-12b-with-proj-ltx-2.5-nvfp4.safetensors + models_t5_umt5-xxl-enc-bf16.pth; vae/ltx-2.5-video-vae-conv-bf16 + ltx-2.5-audio-vae-bf16; latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors; 14B weights PRUNED 2026-10-18
- WanVideoWrapper I2V classes present: WanVideoImageToVideoEncode, WanVideoImageClipEncode, WanVideoImageResizeToClosest
- systemd: wan2.2.service (uvicorn wan_service.main:app --host 0.0.0.0 --port 8765, WorkingDirectory=/home/jarvis/Wan2.2, PYTHONPATH=/home/jarvis/Wan2.2, venv python) + comfyui.service (:8188, --disable-pinned-memory), both enabled/active
- GET :8765/health = 200 {status:ok, gpus:[5b-gguf x2, loaded:false], queue_depth:0}; :8766 connection refused (no LTX service)
- stills staged: /home/jarvis/wan-stills/locksmith-van-front.png + /home/jarvis/ltx-stills/locksmith-van-front.png, both sha256 2b073987f085fa35621272f7af0ab2bf4894281321dfcd8c53d7ae830694fb44 (2580316 bytes)
- peer git: /home/jarvis/Wan2.2 @ 3a4b80b clean; local fork main @ 4b791db (diverged, docs-only local commits)
- runbook: /home/jarvis/ComfyUI/user/default/ltx25-tests/RUNBOOK.txt — Q3 shared-service I2V pilot 2026-11-01: 290.305s, 121f 24fps, 544x960 -> 1088x1920, audio, GPU0 peak 14866 MiB, host swap 5.23 GiB; crop 4px/side to exact 1080x1920; Jose ruling 2026-11-01: ONE video-generator service at a time, labs :8190/:8191 stopped
- ffmpeg present on peer (runbook crop/re-encode used it)
