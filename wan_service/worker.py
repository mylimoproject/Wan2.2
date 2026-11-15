"""WAN wrapper worker (plan v1.3 §§2, 4b, 5): single slot, terminal states are
terminal, cancellation is prompt-targeted, draining ownership until the owned
prompt is absent/terminal and the generation thread has quiesced.

T2V keeps the golden-pinned graph. I2V uses the 5B chain LoadImage → ImageScale
→ WanVideoEncode → WanVideoEmptyEmbeds.extra_latents (the 14B
WanVideoImageToVideoEncode channel-concat path crashes on 5B). INPUT_TYPES
confirmed on the peer 2026-11-14, including the five required tile scalars.
"""
from __future__ import annotations

import json
import random
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

try:
    import websocket  # websocket-client, shipped with ComfyUI
except ImportError:  # progress falls back to a time-based estimate
    websocket = None

from . import config
from local_media import cleanup_staged, finalize_video, TailError


PROGRESS_NODE_ID = "6"  # WanVideoSampler node in build_wan22_workflow

# Calibrated 2026-10-18 on 2x RTX 5060 Ti: 17 frames x 25 steps at 704x1280 took
# 280 s end-to-end. The CPU T5 encode is inside the fixed overhead term.
ESTIMATE_BASE_SECONDS = 20.0
# Starting point measured 2026-10-18: 347 s for 17f x 10 steps at 704x1280.
# The estimate self-calibrates from every completed job, because the CPU T5
# encode dominates and varies with cold/warm model state.
DEFAULT_SECONDS_PER_UNIT = 2.5e-7


def workload_units(request) -> float:
    frames = request.num_frames or 97
    steps = request.num_inference_steps or 50
    width = request.width or 1280
    height = request.height or 720
    return float(frames) * float(steps) * float(width) * float(height)


def _read_ratio() -> float:
    try:
        data = json.loads(config.CALIBRATION_PATH.read_text())
        ratio = float(data["seconds_per_unit"])
        return ratio if ratio > 0 else DEFAULT_SECONDS_PER_UNIT
    except Exception:
        return DEFAULT_SECONDS_PER_UNIT


def _write_ratio(ratio: float) -> None:
    try:
        config.CALIBRATION_PATH.parent.mkdir(parents=True, exist_ok=True)
        config.CALIBRATION_PATH.write_text(json.dumps({"seconds_per_unit": ratio}))
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


def map_size(width: int, height: int) -> tuple[int, int]:
    """TI2V-5B requires multiples of 32 (vae_stride 16 x patch 2); 720 is invalid
    (odd latent → patchify mismatch). Round each dim UP, never pad; the shared
    ffmpeg tail center-crops back to the exact requested size (§4b)."""
    return (32 * ((width + 31) // 32), 32 * ((height + 31) // 32))


def build_wan22_workflow(prompt: str, negative_prompt: str = "", width: int = 704, height: int = 1280,
                          num_frames: int = 17, steps: int = 10, seed: int = None,
                          guidance_scale: float = 5.0, image_name: str = None) -> dict:
    """Build a ComfyUI workflow for Wan2.2 5B via GGUF. Produces MP4 video.

    T2V (no image_name) reproduces the proven golden byte-for-byte at the
    default 704x1280 shape with default cfg. fps stays hardcoded 24 in
    CreateVideo (plan v1.3 §3, documented)."""
    if seed is None:
        seed = random.randint(0, 2**32 - 1)
    gen_w, gen_h = map_size(width, height)

    workflow = {
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
                "width": gen_w,
                "height": gen_h,
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
                "cfg": guidance_scale,
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
    if image_name:
        workflow["5"]["inputs"]["extra_latents"] = ["12", 0]
        workflow["10"] = {
            "class_type": "LoadImage",
            "inputs": {"image": image_name}
        }
        workflow["11"] = {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["10", 0],
                "upscale_method": "lanczos",
                "width": gen_w,
                "height": gen_h,
                "crop": "center"
            }
        }
        workflow["12"] = {
            "class_type": "WanVideoEncode",
            "inputs": {
                "vae": ["2", 0],
                "image": ["11", 0],
                "enable_vae_tiling": False,
                "tile_x": 272,
                "tile_y": 272,
                "tile_stride_x": 144,
                "tile_stride_y": 128
            }
        }
    return workflow


class ComfyRejected(Exception):
    """ComfyUI /prompt answered 400 (node_errors): nothing was queued."""


class ComfyUnavailable(Exception):
    """Connection failure / timeout / non-400 error talking to ComfyUI."""


class ComfyUIClient:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self._http = httpx.Client(timeout=10.0)
        self._dl = httpx.Client(timeout=120.0)

    def queue(self) -> dict:
        try:
            r = self._http.get(f"{self.base}/queue")
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise ComfyUnavailable(str(e)) from None

    def system_stats(self) -> dict:
        try:
            r = self._http.get(f"{self.base}/system_stats")
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise ComfyUnavailable(str(e)) from None

    def submit(self, prompt: dict) -> str:
        try:
            r = self._http.post(f"{self.base}/prompt", json={"prompt": prompt, "client_id": f"wan-{uuid.uuid4()}"})
        except httpx.HTTPError as e:
            raise ComfyUnavailable(str(e)) from None
        if r.status_code == 400:
            raise ComfyRejected(r.text[:400])
        if r.status_code >= 400:
            raise ComfyUnavailable(f"prompt status {r.status_code}")
        return r.json()["prompt_id"]

    def history(self, prompt_id: str) -> dict:
        try:
            r = self._http.get(f"{self.base}/history/{prompt_id}")
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise ComfyUnavailable(str(e)) from None

    def interrupt(self, prompt_id: str) -> None:
        # TARGETED only (C9): the server checks the id against running entries.
        # Never an empty body; never a fallback to a global interrupt.
        try:
            self._http.post(f"{self.base}/interrupt", json={"prompt_id": prompt_id})
        except httpx.HTTPError:
            pass  # drain loop re-checks; a failed interrupt is retried, never globalized

    def delete_pending(self, prompt_id: str) -> None:
        try:
            self._http.post(f"{self.base}/queue", json={"delete": [prompt_id]})
        except httpx.HTTPError:
            pass

    def view(self, filename: str, subfolder: str, ftype: str) -> bytes:
        try:
            r = self._dl.get(f"{self.base}/view", params={"filename": filename, "subfolder": subfolder, "type": ftype})
            r.raise_for_status()
            return r.content
        except httpx.HTTPError as e:
            raise ComfyUnavailable(str(e)) from None


def decide_cancel_action(queue_snapshot: dict, own_prompt_id: str | None) -> tuple[str, str | None]:
    """Pure policy (C9): what to do with the OWN prompt given a queue snapshot.
    Returns (action, prompt_id): 'interrupt' | 'delete' | 'none'. Never global."""
    if not own_prompt_id:
        return ("none", None)
    running = [item[1] for item in queue_snapshot.get("queue_running", []) if len(item) > 1]
    pending = [item[1] for item in queue_snapshot.get("queue_pending", []) if len(item) > 1]
    if own_prompt_id in running:
        return ("interrupt", own_prompt_id)
    if own_prompt_id in pending:
        return ("delete", own_prompt_id)
    return ("none", None)


def _open_progress_socket():
    """Open a ComfyUI websocket; None if unavailable (time-based fallback)."""
    if websocket is None or not config.PROGRESS_WS_ENABLED:
        return None
    try:
        ws_url = config.COMFYUI_URL.replace("http://", "ws://", 1)
        ws = websocket.create_connection(f"{ws_url}/ws?clientId={uuid.uuid4().hex}", timeout=5)
        ws.settimeout(0.2)
        return ws
    except Exception:
        return None


def _pump_progress(ws, prompt_id: str, rec, elapsed: float, estimated: float):
    """Drain buffered websocket messages and update rec.progress in place."""
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
                    rec.progress = max(rec.progress, min(0.95, value))
    if rec.progress < 0.02:
        rec.progress = min(0.90, 0.90 * elapsed / max(estimated, 1.0))


def _close_progress_socket(ws):
    if ws is not None:
        try:
            ws.close()
        except Exception:
            pass


class JobRecord:
    def __init__(self, job_id: str, staged_name: str):
        self.job_id = job_id
        self.staged_name = staged_name
        self.status = "queued"
        self.error: str | None = None
        self.progress = 0.0
        self.comfy_prompt_id: str | None = None
        self.expired = False
        self.draining = False
        self.output_path: Path | None = None
        self.started_monotonic: float | None = None
        self.gen_done = threading.Event()


class WanWorker:
    def __init__(self, client, input_dir=None, output_dir=None, job_timeout=None, poll_interval=None, drain_interval=0.5):
        self.client = client
        self.input_dir = Path(input_dir if input_dir is not None else config.COMFYUI_INPUT_DIR)
        self.output_dir = Path(output_dir if output_dir is not None else config.OUTPUT_DIR)
        self.job_timeout = job_timeout if job_timeout is not None else config.JOB_TIMEOUT_SECONDS
        self.poll_interval = poll_interval if poll_interval is not None else config.POLL_INTERVAL_SECONDS
        self.drain_interval = drain_interval
        self._lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}
        self._slot_busy = False
        self._executor = ThreadPoolExecutor(max_workers=1)

    # ---- admission-side (called under the app's admission lock) ----
    def try_reserve(self, job_id: str, staged_name: str) -> bool:
        with self._lock:
            if self._slot_busy:
                return False
            self._slot_busy = True
            self._jobs[job_id] = JobRecord(job_id, staged_name)
            return True

    def release(self, job_id: str) -> None:
        """Admission failed after reservation: free the slot, keep no record."""
        with self._lock:
            self._jobs.pop(job_id, None)
            self._slot_busy = False

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def start(self, job_id: str, req) -> None:
        self._executor.submit(self._run, job_id, req)

    # ---- terminal transitions (monotonic) ----
    def _finish(self, job_id: str, status: str, error: str | None) -> bool:
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec is None or rec.status in ("completed", "failed"):
                return False
            rec.status = status
            rec.error = error
            return True

    def _expire(self, job_id: str, reason: str) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec is None or rec.status in ("completed", "failed"):
                return
            rec.status = "failed"
            rec.error = reason
            rec.expired = True
            rec.draining = True
        threading.Thread(target=self._drain, args=(job_id,), daemon=True).start()

    def cancel(self, job_id: str) -> bool:
        rec = self.get(job_id)
        if rec is None:
            return False
        self._expire(job_id, "cancelled")
        return True

    # ---- generation (executor thread) ----
    def _run(self, job_id: str, req) -> None:
        rec = self._jobs[job_id]
        progress_ws = None
        try:
            if rec.expired:  # cancel-while-queued: never submit
                return
            graph = build_wan22_workflow(
                prompt=req.prompt, negative_prompt=req.negative_prompt or "",
                width=req.width, height=req.height, num_frames=req.num_frames,
                steps=req.num_inference_steps, seed=req.seed,
                guidance_scale=req.guidance_scale, image_name=rec.staged_name or None,
            )
            try:
                prompt_id = self.client.submit(graph)
            except ComfyRejected as e:
                self._finish(job_id, "failed", f"comfyui_rejected: {e}")
                self._cleanup_now(job_id)
                return
            except ComfyUnavailable as e:
                self._finish(job_id, "failed", f"comfyui_unreachable: {e}")
                self._cleanup_now(job_id)
                return
            with self._lock:
                rec.comfy_prompt_id = prompt_id
                rec.status = "processing"
                rec.started_monotonic = time.monotonic()
            estimated = float(estimate_seconds(req))
            progress_ws = _open_progress_socket()
            deadline = rec.started_monotonic + self.job_timeout
            failures = 0
            while not rec.expired:
                _pump_progress(progress_ws, prompt_id, rec, time.monotonic() - rec.started_monotonic, estimated)
                try:
                    hist = self.client.history(prompt_id)
                    failures = 0
                except ComfyUnavailable:
                    failures += 1
                    if failures >= 10:
                        self._expire(job_id, "poll_failure")
                        return
                    time.sleep(self.poll_interval)
                    continue
                entry = hist.get(prompt_id)
                if entry:
                    st = entry.get("status", {})
                    if st.get("status_str") == "error":
                        self._finish(job_id, "failed", "comfyui_error")
                        self._cleanup_now(job_id)
                        return
                    if st.get("status_str") == "success" or st.get("completed"):
                        self._publish(job_id, req, entry)
                        return
                if time.monotonic() > deadline:
                    self._expire(job_id, "generation_timeout")
                    return
                time.sleep(self.poll_interval)
        finally:
            _close_progress_socket(progress_ws)
            rec.gen_done.set()

    def _publish(self, job_id: str, req, entry: dict) -> None:
        rec = self._jobs[job_id]
        if rec.expired:
            return
        mp4 = None
        for node_out in entry.get("outputs", {}).values():
            for key in ("gifs", "videos", "images"):
                for f in node_out.get(key, []):
                    if str(f.get("filename", "")).endswith(".mp4"):
                        mp4 = f
                        break
        if mp4 is None:
            self._finish(job_id, "failed", "no_mp4_output")
            self._cleanup_now(job_id)
            return
        tmp = self.output_dir / f".{job_id}.download.mp4"
        final = self.output_dir / f"{job_id}.mp4"
        try:
            data = self.client.view(mp4["filename"], mp4.get("subfolder", ""), mp4.get("type", "output"))
            if rec.expired:
                tmp.unlink(missing_ok=True)
                return
            tmp.write_bytes(data)
            finalize_video(tmp, final, req.width, req.height)
        except (ComfyUnavailable, TailError, OSError) as e:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            self._finish(job_id, "failed", f"output_failed: {e}")
            self._cleanup_now(job_id)
            return
        if rec.expired:  # late result: never publish for an expired job
            try:
                final.unlink(missing_ok=True)
            except OSError:
                pass
            return
        with self._lock:
            if rec.status in ("completed", "failed"):
                return
            rec.status = "completed"
            rec.output_path = final
            rec.progress = 1.0
        if rec.started_monotonic is not None:
            record_runtime(req, time.monotonic() - rec.started_monotonic)
        cleanup_staged(self.input_dir, rec.staged_name)
        with self._lock:
            self._slot_busy = False

    def _cleanup_now(self, job_id: str) -> None:
        """Terminal without a queued prompt (submit refused / error / no output):
        safe to clean immediately; no drain needed."""
        rec = self._jobs.get(job_id)
        if rec is not None:
            cleanup_staged(self.input_dir, rec.staged_name)
        with self._lock:
            self._slot_busy = False

    # ---- draining ownership (C9) ----
    def _drain(self, job_id: str) -> None:
        rec = self._jobs[job_id]
        rec.gen_done.wait(timeout=self.job_timeout + 180)
        pid = rec.comfy_prompt_id
        if pid:
            gone_count = 0
            for _ in range(240):
                try:
                    q = self.client.queue()
                except ComfyUnavailable:
                    time.sleep(self.drain_interval)
                    continue
                action, target = decide_cancel_action(q, pid)
                if action == "interrupt":
                    self.client.interrupt(target)  # targeted JSON only; never global
                    gone_count = 0
                elif action == "delete":
                    self.client.delete_pending(target)
                    gone_count = 0  # 200 is not proof; re-read next pass
                else:
                    try:
                        hist = self.client.history(pid)
                    except ComfyUnavailable:
                        hist = {}
                    if pid in hist:
                        break  # terminal in history
                    gone_count += 1
                    if gone_count >= 2:
                        break  # absent from queue twice → gone (submit-race safe)
                time.sleep(self.drain_interval)
        cleanup_staged(self.input_dir, rec.staged_name)
        with self._lock:
            rec.draining = False
            self._slot_busy = False