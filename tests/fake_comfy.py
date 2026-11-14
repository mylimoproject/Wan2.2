"""Scriptable fake ComfyUI client for the offline contract/lifecycle suites."""
import subprocess
import threading

from ltx_service.worker import ComfyRejected, ComfyUnavailable


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
    def __init__(self):
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
            raise ComfyUnavailable("down")
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
            raise ComfyUnavailable("down")
        return {"system": {}}

    def submit(self, prompt):
        if self.down:
            raise ComfyUnavailable("down")
        if self.submit_error == "rejected":
            raise ComfyRejected("node_errors: bad input")
        if self.submit_error == "unavailable":
            raise ComfyUnavailable("connection refused")
        with self.lock:
            self._n += 1
            pid = f"prompt-{self._n}"
            self.submitted.append(prompt)
            self.running.append(pid)
        return pid

    def history(self, pid):
        if self.down:
            raise ComfyUnavailable("down")
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
            raise ComfyUnavailable("down")
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
