"""HTTP-level admission contract suite (plan v1.3 §2, C1), BOTH wrappers:
refusal answers the POST itself, with ZERO ComfyUI submissions and no leaked
staged copies."""
import re
import time

import pytest

from local_media import probe_size
from fake_comfy import body, make_env

JOB_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@pytest.fixture(params=["ltx", "wan"])
def env(request, tmp_path, monkeypatch):
    return make_env(request.param, tmp_path, monkeypatch)


def wait_status(c, job_id, want, timeout=4.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        r = c.get(f"/status/{job_id}")
        if r.status_code == 200 and r.json()["status"] == want:
            return r.json()
        time.sleep(0.01)
    raise AssertionError(f"status never became {want}: {c.get(f'/status/{job_id}').json()}")


def probe_size_bytes(data):
    import tempfile, pathlib
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(data)
        p = pathlib.Path(f.name)
    try:
        return probe_size(p)
    finally:
        p.unlink(missing_ok=True)


def test_happy_path_engine_request(env):
    c, fake = env["client"], env["fake"]
    r = c.post("/generate", json=body(env["route"]))
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
    r2 = c.post("/generate", json=body(env["route"]))
    assert r2.status_code == 202


@pytest.mark.parametrize("mut,code", [
    ({"image_path": None}, "validation_failed"),
    ({"image_sha256": "xyz"}, "validation_failed"),
    ({"model_variant": "__WRONG__"}, "validation_failed"),
    ({"image_path": "missing.png"}, "still_not_found"),
    ({"image_sha256": "0" * 64}, "still_hash_mismatch"),
])
def test_refusals_are_400_with_zero_submissions(env, mut, code):
    if env["route"] == "wan" and "image_path" in mut and mut["image_path"] is None:
        pytest.skip("WAN admits T2V without a still (covered by test_wan_t2v_admitted_without_still)")
    c, fake = env["client"], env["fake"]
    b = body(env["route"], **mut)
    if b["image_path"] is None:
        del b["image_path"]
    if b["model_variant"] == "__WRONG__":
        b["model_variant"] = "ltx-2.5" if env["route"] == "ltx" else "5b"
    r = c.post("/generate", json=b)
    assert r.status_code == 400
    assert r.json()["error"] == code
    assert fake.submitted == []
    assert list(env["indir"].iterdir()) == []
    # slot released: a valid request still gets in
    assert c.post("/generate", json=body(env["route"])).status_code == 202


def test_queue_busy_429(env):
    c, fake = env["client"], env["fake"]
    fake.pending.append("someone-else")
    r = c.post("/generate", json=body(env["route"]))
    assert r.status_code == 429
    assert r.json()["error"] == "queue_busy"
    assert fake.submitted == []


@pytest.mark.parametrize("path", ["../escape.png", "/abs/path.png", "sub/../../escape.png"])
def test_traversal_refused_at_http_boundary(env, path):
    c, fake = env["client"], env["fake"]
    r = c.post("/generate", json=body(env["route"], image_path=path))
    assert r.status_code == 400
    assert r.json()["error"] == "still_path_invalid"
    assert fake.submitted == []
    assert list(env["indir"].iterdir()) == []
    assert c.post("/generate", json=body(env["route"])).status_code == 202


def test_comfy_down_503(env):
    c, fake = env["client"], env["fake"]
    fake.down = True
    r = c.post("/generate", json=body(env["route"]))
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


def test_health_reports_served_variant(env):
    r = env["client"].get("/health")
    assert r.status_code == 200
    assert r.json()["model"] == env["variant"]


def test_status_and_output_404(env):
    c = env["client"]
    assert c.get("/status/gen-nope").status_code == 404
    assert c.get("/output/gen-nope").status_code == 404


def test_seed_null_preserved(env):
    c, fake = env["client"], env["fake"]
    r = c.post("/generate", json=body(env["route"], seed=None))
    assert r.status_code == 202
    pid = fake.wait_submitted()
    g = fake.submitted[-1]
    if env["route"] == "ltx":
        s = g["12"]["inputs"]["noise_seed"]
        assert isinstance(s, int) and s == g["24"]["inputs"]["noise_seed"]
    else:
        assert isinstance(g["6"]["inputs"]["seed"], int)
    fake.complete(pid)
    wait_status(c, r.json()["job_id"], "completed")


def test_cancel_reports_failed_cancelled(env):
    c, fake = env["client"], env["fake"]
    r = c.post("/generate", json=body(env["route"]))
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


def test_wan_t2v_admitted_without_still(env):
    if env["route"] != "wan":
        pytest.skip("LTX is I2V-only")
    c, fake = env["client"], env["fake"]
    b = body("wan")
    del b["image_path"]
    del b["image_sha256"]
    r = c.post("/generate", json=b)
    assert r.status_code == 202
    pid = fake.wait_submitted()
    g = fake.submitted[-1]
    assert "10" not in g and "11" not in g and "12" not in g
    assert "extra_latents" not in g["5"]["inputs"]
    assert list(env["indir"].iterdir()) == [], "T2V must not stage anything"
    fake.complete(pid)
    wait_status(c, r.json()["job_id"], "completed")


def test_wan_bare_request_gets_served_default(env):
    if env["route"] != "wan":
        pytest.skip("LTX requires a still; bare-request default is WAN's T2V regression")
    c, fake = env["client"], env["fake"]
    r = c.post("/generate", json={"prompt": "p"})
    assert r.status_code == 202
    pid = fake.wait_submitted()
    g = fake.submitted[-1]
    assert "extra_latents" not in g["5"]["inputs"]
    assert g["6"]["inputs"]["cfg"] == 5.0
    fake.complete(pid)
    wait_status(c, r.json()["job_id"], "completed")