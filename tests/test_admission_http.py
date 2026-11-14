"""HTTP-level admission contract suite (plan v1.3 §2, C1): refusal answers the
POST itself, with ZERO ComfyUI submissions and no leaked staged copies."""
import hashlib
import re
import time

import pytest
from fastapi.testclient import TestClient

from ltx_service import config
from ltx_service.main import create_app
from ltx_service.worker import LtxWorker
from local_media import probe_size
from fake_comfy import FakeComfy, make_mp4

SHA = hashlib.sha256(b"still-bytes").hexdigest()
JOB_RE = re.compile(r"^[A-Za-z0-9_-]+$")


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
    fake.view_data = make_mp4(tmp_path / "fixture.mp4", 1280, 768)
    worker = LtxWorker(fake, input_dir=indir, output_dir=outdir, job_timeout=1, poll_interval=0.01, drain_interval=0.01)
    app = create_app(client=fake, worker=worker)
    return {"client": TestClient(app), "fake": fake, "worker": worker, "stills": stills, "indir": indir, "outdir": outdir}


def body(**over):
    d = {
        "prompt": "a locksmith van", "negative_prompt": "blurry",
        "image_path": "van.png", "image_sha256": SHA,
        "width": 1280, "height": 720, "num_frames": 97, "fps": 24,
        "num_inference_steps": 50, "guidance_scale": 5.0, "seed": 1,
        "model_variant": "ltx-2.5-q3", "output_format": "mp4",
    }
    d.update(over)
    return d


def wait_status(c, job_id, want, timeout=4.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        r = c.get(f"/status/{job_id}")
        if r.status_code == 200 and r.json()["status"] == want:
            return r.json()
        time.sleep(0.01)
    raise AssertionError(f"status never became {want}: {c.get(f'/status/{job_id}').json()}")


def test_happy_path_engine_request(env):
    c, fake = env["client"], env["fake"]
    r = c.post("/generate", json=body())
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    assert JOB_RE.match(job_id)
    pid = fake.wait_submitted()
    fake.complete(pid)
    wait_status(c, job_id, "completed")
    out = c.get(f"/output/{job_id}")
    assert out.status_code == 200
    data = out.content
    assert data[4:8] == b"ftyp"
    assert probe_size_bytes(data) == (1280, 720)
    assert list(env["indir"].iterdir()) == [], "staged copy must be cleaned at terminal"
    # slot freed: a second job is admitted
    r2 = c.post("/generate", json=body())
    assert r2.status_code == 202


def probe_size_bytes(data):
    import tempfile, pathlib
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(data)
        p = pathlib.Path(f.name)
    try:
        return probe_size(p)
    finally:
        p.unlink(missing_ok=True)


@pytest.mark.parametrize("mut,code", [
    ({"image_path": None}, "validation_failed"),
    ({"image_sha256": "xyz"}, "validation_failed"),
    ({"model_variant": "ltx-2.5"}, "validation_failed"),
    ({"image_path": "missing.png"}, "still_not_found"),
    ({"image_sha256": "0" * 64}, "still_hash_mismatch"),
])
def test_refusals_are_400_with_zero_submissions(env, mut, code):
    c, fake = env["client"], env["fake"]
    b = body(**mut)
    if b["image_path"] is None:
        del b["image_path"]
    r = c.post("/generate", json=b)
    assert r.status_code == 400
    assert r.json()["error"] == code
    assert fake.submitted == []
    assert list(env["indir"].iterdir()) == []
    # slot released: a valid request still gets in
    assert c.post("/generate", json=body()).status_code == 202


def test_queue_busy_429(env):
    c, fake = env["client"], env["fake"]
    fake.pending.append("someone-else")
    r = c.post("/generate", json=body())
    assert r.status_code == 429
    assert r.json()["error"] == "queue_busy"
    assert fake.submitted == []


def test_comfy_down_503(env):
    c, fake = env["client"], env["fake"]
    fake.down = True
    r = c.post("/generate", json=body())
    assert r.status_code == 503
    assert fake.submitted == []


def test_health_interlock(env):
    c, fake = env["client"], env["fake"]
    assert c.get("/health").status_code == 200
    fake.pending.append("x")
    assert c.get("/health").status_code >= 400
    fake.pending.clear()
    fake.down = True
    assert c.get("/health").status_code >= 400


def test_status_and_output_404(env):
    c = env["client"]
    assert c.get("/status/gen-nope").status_code == 404
    assert c.get("/output/gen-nope").status_code == 404


def test_seed_null_preserved(env):
    c, fake = env["client"], env["fake"]
    r = c.post("/generate", json=body(seed=None))
    assert r.status_code == 202
    pid = fake.wait_submitted()
    g = fake.submitted[-1]
    s = g["12"]["inputs"]["noise_seed"]
    assert isinstance(s, int) and s == g["24"]["inputs"]["noise_seed"]
    fake.complete(pid)
    wait_status(c, r.json()["job_id"], "completed")


def test_cancel_reports_failed_cancelled(env):
    c, fake = env["client"], env["fake"]
    r = c.post("/generate", json=body())
    job_id = r.json()["job_id"]
    pid = fake.wait_submitted()
    rc = c.post(f"/cancel/{job_id}")
    assert rc.status_code == 200
    st = wait_status(c, job_id, "failed")
    assert st["error"] == "cancelled"
    assert c.get(f"/status/{job_id}").json()["status"] == "failed"  # never "cancelled"
    # targeted interrupt only
    end = time.monotonic() + 3
    while time.monotonic() < end and not fake.interrupts:
        time.sleep(0.01)
    assert fake.interrupts == [pid]
