"""Interlock tests (plan v1.3 §5), BOTH wrappers: depth-1 slot, simultaneous
admissions."""
import threading

import pytest
from fastapi.testclient import TestClient

from fake_comfy import body, make_env


@pytest.fixture(params=["ltx", "wan"])
def env(request, tmp_path, monkeypatch):
    return make_env(request.param, tmp_path, monkeypatch, poll_interval=0.05)


def test_simultaneous_admissions_one_wins(env):
    results = []
    barrier = threading.Barrier(2)
    # ONE persistent portal/loop: the admission lock must not be shared across loops
    with TestClient(env["app"]) as c:
        def fire():
            barrier.wait()
            r = c.post("/generate", json=body(env["route"]))
            results.append(r.status_code)

        ts = [threading.Thread(target=fire) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=10)
    assert sorted(results) == [202, 429], results
    assert len(env["fake"].submitted) <= 1