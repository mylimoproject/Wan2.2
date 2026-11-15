"""Lifecycle regressions (plan v1.3 §5, C3/C9), BOTH wrappers: terminal states
stay terminal; cancellation is prompt-targeted; draining ownership until the
owned prompt is absent/terminal and the generation thread quiesced. Zero global
interrupts in EVERY case."""
import time
from types import SimpleNamespace

import pytest

from ltx_service.worker import decide_cancel_action as ltx_policy
from wan_service.worker import decide_cancel_action as wan_policy
from fake_comfy import make_rig


def req(**over):
    d = dict(prompt="p", negative_prompt="n", width=1280, height=720, num_frames=33, fps=24, seed=1,
             num_inference_steps=10, guidance_scale=5.0)
    d.update(over)
    return SimpleNamespace(**d)


@pytest.fixture(params=["ltx", "wan"])
def rig(request, tmp_path):
    return make_rig(request.param, tmp_path)


def start(rig, staged="gen-j1-van.png", **over):
    (rig.indir / staged).write_bytes(b"x")
    assert rig.w.try_reserve("gen-j1", staged)
    rig.w.start("gen-j1", req(**over))
    return "gen-j1"


def wait(rig, pred, timeout=4.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return
        time.sleep(0.01)
    raise AssertionError("condition never met")


def slot_free(rig):
    return rig.w.try_reserve("gen-probe", "probe.png")


def test_timeout_then_late_success_never_publishes(rig):
    job = start(rig)
    pid = rig.fake.wait_submitted()
    wait(rig, lambda: rig.w.get(job).status == "failed")
    assert rig.w.get(job).error == "generation_timeout"
    wait(rig, lambda: rig.fake.interrupts == [pid])  # drain targets the running prompt
    rig.fake.complete(pid)  # LATE success, after the interrupt
    time.sleep(0.15)
    assert rig.w.get(job).status == "failed", "terminal state reversed"
    assert rig.w.get(job).output_path is None
    assert list(rig.outdir.glob("*.mp4")) == []
    wait(rig, lambda: slot_free(rig))
    assert list(rig.indir.iterdir()) == []
    assert rig.fake.interrupts == [pid], "must be exactly the targeted own id"


def test_timeout_then_late_error(rig):
    job = start(rig)
    pid = rig.fake.wait_submitted()
    wait(rig, lambda: rig.w.get(job).status == "failed")
    wait(rig, lambda: rig.fake.interrupts == [pid])
    rig.fake.histories[pid] = {"status": {"status_str": "error"}, "outputs": {}}
    time.sleep(0.15)
    assert rig.w.get(job).status == "failed"
    wait(rig, lambda: slot_free(rig))
    assert rig.fake.interrupts == [pid]


def test_completed_is_monotonic(rig):
    rig.w.job_timeout = 5
    job = start(rig)
    pid = rig.fake.wait_submitted()
    rig.fake.complete(pid)
    wait(rig, lambda: rig.w.get(job).status == "completed")
    rig.w.cancel(job)  # late cancel must not reverse completion
    time.sleep(0.1)
    assert rig.w.get(job).status == "completed"
    assert rig.fake.interrupts == []


def test_own_running_then_other_running(rig):
    # queue advances between drain passes: interrupt must stay targeted
    job = start(rig)
    pid = rig.fake.wait_submitted()
    rig.fake.running.clear()
    rig.fake.queue_script = lambda n: (
        {"queue_running": [[0, pid]], "queue_pending": []} if n == 1
        else {"queue_running": [[0, "OTHER-PROMPT"]], "queue_pending": []}
    )
    rig.w.cancel(job)
    wait(rig, lambda: slot_free(rig))
    assert rig.fake.interrupts == [pid]
    assert all(i == pid for i in rig.fake.interrupts), "foreign/global interrupt"
    assert rig.fake.deletes == []
    assert list(rig.indir.iterdir()) == []


def test_own_pending_then_running_before_delete(rig):
    job = start(rig)
    pid = rig.fake.wait_submitted()
    rig.fake.running.clear()
    rig.fake.queue_script = lambda n: (
        {"queue_running": [], "queue_pending": [[0, pid]]} if n == 1
        else {"queue_running": [[0, pid]], "queue_pending": []} if n == 2
        else {"queue_running": [], "queue_pending": []}
    )
    rig.w.cancel(job)
    wait(rig, lambda: slot_free(rig))
    assert rig.fake.deletes == [pid]
    assert rig.fake.interrupts == [pid]  # 200 was not proof; re-read found it running


def test_interrupt_noop_then_gone(rig):
    job = start(rig)
    pid = rig.fake.wait_submitted()
    rig.fake.running.clear()
    rig.fake.queue_script = lambda n: (
        {"queue_running": [[0, pid]], "queue_pending": []} if n <= 3
        else {"queue_running": [], "queue_pending": []}
    )
    rig.w.cancel(job)
    wait(rig, lambda: slot_free(rig))
    assert len(rig.fake.interrupts) >= 1
    assert all(i == pid for i in rig.fake.interrupts)
    assert list(rig.indir.iterdir()) == []


def test_no_prompt_id_no_interrupt_no_delete(rig):
    rig.fake.submit_error = "rejected"
    job = start(rig)
    wait(rig, lambda: rig.w.get(job).status == "failed")
    assert "comfyui_rejected" in rig.w.get(job).error
    time.sleep(0.1)
    assert rig.fake.interrupts == []
    assert rig.fake.deletes == []
    assert slot_free(rig)
    assert list(rig.indir.iterdir()) == []


def test_ownership_retained_while_draining(rig):
    job = start(rig)
    pid = rig.fake.wait_submitted()
    rig.fake.running.clear()
    stuck = {"v": True}
    rig.fake.queue_script = lambda n: (
        {"queue_running": [[0, pid]], "queue_pending": []} if stuck["v"]
        else {"queue_running": [], "queue_pending": []}
    )
    rig.w.cancel(job)
    time.sleep(0.15)
    rec = rig.w.get(job)
    assert rec.status == "failed" and rec.draining
    assert (rig.indir / "gen-j1-van.png").exists(), "input deleted while prompt still draining"
    assert not slot_free(rig), "slot freed while draining"
    stuck["v"] = False
    wait(rig, lambda: slot_free(rig))
    assert list(rig.indir.iterdir()) == []
    assert all(i == pid for i in rig.fake.interrupts)


def test_cancel_while_queued_never_submits(rig):
    (rig.indir / "gen-j1-van.png").write_bytes(b"x")
    assert rig.w.try_reserve("gen-j1", "gen-j1-van.png")
    rig.w.cancel("gen-j1")  # before start
    rig.w.start("gen-j1", req())
    time.sleep(0.15)
    assert rig.fake.submitted == []
    assert rig.w.get("gen-j1").status == "failed"
    assert rig.fake.interrupts == [] and rig.fake.deletes == []
    wait(rig, lambda: slot_free(rig))
    assert list(rig.indir.iterdir()) == []


@pytest.mark.parametrize("policy", [ltx_policy, wan_policy], ids=["ltx", "wan"])
def test_decide_cancel_action_pure(policy):
    q = {"queue_running": [[0, "own"], [1, "other"]], "queue_pending": [[0, "p"]]}
    assert policy(q, "own") == ("interrupt", "own")
    assert policy(q, "p") == ("delete", "p")
    assert policy(q, "absent") == ("none", None)
    assert policy(q, None) == ("none", None)
    assert policy({}, "own") == ("none", None)