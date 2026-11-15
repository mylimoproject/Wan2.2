"""Scriptable fake ComfyUI client for the offline contract/lifecycle suites.
Exception classes are per-route (WAN never imports ltx_service); both wrappers
share this fake and the env/rig/body builders below."""
import hashlib
import subprocess
import threading
from types import SimpleNamespace

from ltx_service.worker import ComfyRejected, ComfyUnavailable

STILL_BYTES = b"still-bytes"
STILL_SHA = hashlib.sha256(STILL_BYTES).hexdigest()


def make_mp4(path, w, h, audio=True, seconds=0.5):
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate=24:duration={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    cmd += (["-c:a", "aac", "-shortest"] if audio else ["-an"])
    cmd += [str(path)]
    subprocess.run(cmd, capture_output=True, check=True)
    return path.read_bytes()


class FakeComfy:
    def __init__(self, unavailable=None, rejected=None):
        self.Unavailable = unavailable if unavailable is not None else ComfyUnavailable
        self.Rejected = rejected if rejected is not None else ComfyRejected
        self.running = []
        self.pending = []
        self.submitted = []
        self.interrupts = []
        self.deletes = []
        self.histories = {}
        self.view_data = b""
        self.down = False
        self.submit_error = None
        self.queue_script = None
        self.history_script = None
        self._queue_calls = 0
        self._history_calls = 0
        self._n = 0
        self.lock = threading.Lock()

    def queue(self):
        if self.down:
            raise self.Unavailable("down")
        with self.lock:
            self._queue_calls += 1
            if self.queue_script:
                return self.queue_script(self._queue_calls)
            return {
                "queue_running": [[i, p] for i, p in enumerate(self.running)],
                "queue_pending": [[i, p] for i, p in enumerate(self.pending)],
            }

    def system_stats(self):
        if self.down:
            raise self.Unavailable("down")
        return {"system": {}}

    def submit(self, prompt):
        if self.down:
            raise self.Unavailable("down")
        if self.submit_error == "rejected":
            raise self.Rejected("node_errors: bad input")
        if self.submit_error == "unavailable":
            raise self.Unavailable("connection refused")
        with self.lock:
            self._n += 1
            pid = f"prompt-{self._n}"
            self.submitted.append(prompt)
            self.running.append(pid)
        return pid

    def history(self, pid):
        if self.down:
            raise self.Unavailable("down")
        with self.lock:
            self._history_calls += 1
            if self.history_script:
                return self.history_script(self._history_calls, pid)
            return {pid: self.histories[pid]} if pid in self.histories else {}

    def interrupt(self, pid):
        # records the TARGET id; a global/empty-body interrupt would appear as None
        with self.lock:
            self.interrupts.append(pid)
            if pid in self.running:
                self.running.remove(pid)
            self.histories[pid] = {"status": {"status_str": "error", "completed": True}, "outputs": {}}

    def delete_pending(self, pid):
        with self.lock:
            self.deletes.append(pid)
            if pid in self.pending:
                self.pending.remove(pid)

    def view(self, filename, subfolder, ftype):
        if self.down:
            raise self.Unavailable("down")
        return self.view_data

    def complete(self, pid, filename="out.mp4"):
        with self.lock:
            if pid in self.running:
                self.running.remove(pid)
            self.histories[pid] = {
                "status": {"status_str": "success", "completed": True},
                "outputs": {"20": {"gifs": [{"filename": filename, "subfolder": "", "type": "output"}]}},
            }

    def wait_submitted(self, timeout=3.0):
        import time
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self.lock:
                if self.submitted:
                    return f"prompt-{len(self.submitted)}"
            time.sleep(0.01)
        raise AssertionError("no submission within timeout")


def route_modules(route):
    """Per-route config/app/worker/exceptions/variant/generated-fixture-size."""
    if route == "ltx":
        from ltx_service import config, main, worker
        return config, main.create_app, worker.LtxWorker, worker.ComfyUnavailable, worker.ComfyRejected, "ltx-2.5-q3", (1280, 768)
    from wan_service import config, main, worker
    return config, main.create_app, worker.WanWorker, worker.ComfyUnavailable, worker.ComfyRejected, "5b-gguf", (1280, 736)


def body(route, **over):
    """The engine's fixed request shape, with the route's served variant."""
    d = {
        "prompt": "a locksmith van", "negative_prompt": "blurry",
        "image_path": "van.png", "image_sha256": STILL_SHA,
        "width": 1280, "height": 720, "num_frames": 97, "fps": 24,
        "num_inference_steps": 50, "guidance_scale": 5.0, "seed": 1,
        "model_variant": "ltx-2.5-q3" if route == "ltx" else "5b-gguf",
        "output_format": "mp4",
    }
    d.update(over)
    return d


def make_env(route, tmp_path, monkeypatch, job_timeout=1, poll_interval=0.01, drain_interval=0.01):
    """HTTP-level rig: staged still, fake ComfyUI, real app + worker."""
    from fastapi.testclient import TestClient
    config, create_app, Worker, Unavail, Rej, variant, gen_size = route_modules(route)
    stills = tmp_path / "stills"
    stills.mkdir()
    (stills / "van.png").write_bytes(STILL_BYTES)
    indir = tmp_path / "input"
    indir.mkdir()
    outdir = tmp_path / "out"
    outdir.mkdir()
    monkeypatch.setattr(config, "STILLS_ROOT", stills)
    monkeypatch.setattr(config, "COMFYUI_INPUT_DIR", indir)
    fake = FakeComfy(unavailable=Unavail, rejected=Rej)
    fake.view_data = make_mp4(tmp_path / "fixture.mp4", *gen_size)
    worker = Worker(fake, input_dir=indir, output_dir=outdir, job_timeout=job_timeout,
                    poll_interval=poll_interval, drain_interval=drain_interval)
    app = create_app(client=fake, worker=worker)
    return {"route": route, "app": app, "client": TestClient(app), "fake": fake, "worker": worker,
            "stills": stills, "indir": indir, "outdir": outdir, "variant": variant}


def make_rig(route, tmp_path, job_timeout=0.08, poll_interval=0.01, drain_interval=0.01):
    """Worker-level lifecycle rig (no HTTP)."""
    config, create_app, Worker, Unavail, Rej, variant, gen_size = route_modules(route)
    indir = tmp_path / "input"
    indir.mkdir()
    outdir = tmp_path / "out"
    outdir.mkdir()
    fake = FakeComfy(unavailable=Unavail, rejected=Rej)
    fake.view_data = make_mp4(tmp_path / "fx.mp4", *gen_size)
    w = Worker(fake, input_dir=indir, output_dir=outdir, job_timeout=job_timeout,
               poll_interval=poll_interval, drain_interval=drain_interval)
    return SimpleNamespace(w=w, fake=fake, indir=indir, outdir=outdir, route=route)
