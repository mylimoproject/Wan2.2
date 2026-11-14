"""Mapping math tests (plan v1.3 §4, C6): round UP, never pad, crop to exact."""
import math

import pytest

from ltx_service.graph import final_dims, snap_frames, stage1_dims


def test_hg2_clip_shape():
    assert stage1_dims(1280, 720) == (640, 384)
    assert final_dims(1280, 720) == (1280, 768)
    fw, fh = final_dims(1280, 720)
    assert (fh - 720) // 2 == 24  # crop rows per side
    assert (fw - 1280) // 2 == 0


def test_golden_and_runbook_shape():
    assert stage1_dims(1080, 1920) == (544, 960)
    assert final_dims(1080, 1920) == (1088, 1920)  # crop 4/side, runbook precedent


@pytest.mark.parametrize("w,h", [(1280, 720), (1080, 1920), (704, 1280), (100, 100), (1920, 1080), (333, 555), (64, 64), (4096, 2160)])
def test_never_undershoots_and_grid(w, h):
    w1, h1 = stage1_dims(w, h)
    fw, fh = final_dims(w, h)
    assert w1 % 32 == 0 and h1 % 32 == 0
    assert fw >= w and fh >= h, "padding would be required — forbidden"
    assert fw % 64 == 0 and fh % 64 == 0


@pytest.mark.parametrize("n,expected", [(97, 97), (121, 121), (33, 33), (17, 17), (21, 25), (20, 17), (18, 17), (10, 17), (34, 33), (25, 25)])
def test_frame_snap(n, expected):
    assert snap_frames(n) == expected


def test_frame_snap_always_valid_grid():
    for n in range(1, 300):
        f = snap_frames(n)
        assert f >= 17 and (f - 1) % 8 == 0
