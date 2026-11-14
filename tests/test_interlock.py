"""Interlock tests (plan v1.3 §5): depth-1 slot, simultaneous admissions."""
import hashlib
import threading

import pytest
from fastapi.testclient import TestClient

from ltx_service import config
from ltx_service.main import create_app
from ltx_service.worker import LtxWorker
from fake_comfy import FakeComfy

SHA = hashlib.sha256(b"still-bytes").hexdigest()


@pytest.fixture()
def env(tmp_path, monkeypatch):
    stills = tmp_path / "stills"
    stills.mkdir()
    (stills / "van.png").write_bytes(b"still-bytes")
    indir = tmp_path / "input"
    indir.mkdir()
    outdir = tmp_path / "out"
    outdir.mkdir()
    monkeypatch.setattr(config, "STILLS_ROOT", stills)
    monkeypatch.setattr(config, "COMFYUI_INPUT_DIR", indir)
    fake = FakeComfy()
    worker = LtxWorker(fake, input_dir=indir, output_dir=outdir, job_timeout=1, poll_interval=0.05, drain_interval=0.01)
    app = create_app(client=fake, worker=worker)
    return {"app": app, "fake": fake}


def body():
    return {
        "prompt": "p", "negative_prompt": "n", "image_path": "van.png", "image_sha256": SHA,
        "width": 1280, "height": 720, "num_frames": 33, "fps": 24,
        "num_inference_steps": 8, "guidance_scale": 1.0, "seed": 1,
        "model_variant": "ltx-2.5-q3", "output_format": "mp4",
    }


def test_simultaneous_admissions_one_wins(env):
    results = []
    barrier = threading.Barrier(2)
    # ONE persistent portal/loop: the admission lock must not be shared across loops
    with TestClient(env["app"]) as c:
        def fire():
            barrier.wait()
            r = c.post("/generate", json=body())
            results.append(r.status_code)

        ts = [threading.Thread(target=fire) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=10)
    assert sorted(results) == [202, 429], results
    assert len(env["fake"].submitted) <= 1
