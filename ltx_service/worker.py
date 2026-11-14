"""LTX worker (plan v1.3 §§2, 5): single slot, terminal states are terminal,
cancellation is prompt-targeted, draining ownership until the owned prompt is
absent/terminal and the generation thread has quiesced."""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from . import config
from .graph import build_ltx_workflow
from local_media import cleanup_staged, finalize_video, TailError


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
            r = self._http.post(f"{self.base}/prompt", json={"prompt": prompt, "client_id": f"ltx-{uuid.uuid4()}"})
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


class JobRecord:
    def __init__(self, job_id: str, staged_name: str):
        self.job_id = job_id
        self.staged_name = staged_name
        self.status = "queued"
        self.error: str | None = None
        self.comfy_prompt_id: str | None = None
        self.expired = False
        self.draining = False
        self.output_path: Path | None = None
        self.gen_done = threading.Event()


class LtxWorker:
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
        try:
            if rec.expired:  # cancel-while-queued: never submit
                return
            graph = build_ltx_workflow(
                prompt=req.prompt, negative_prompt=req.negative_prompt,
                image_name=rec.staged_name, width=req.width, height=req.height,
                num_frames=req.num_frames, fps=req.fps, seed=req.seed, job_id=job_id,
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
            deadline = time.monotonic() + self.job_timeout
            failures = 0
            while not rec.expired:
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
