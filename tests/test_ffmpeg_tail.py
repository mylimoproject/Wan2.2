"""Shared ffmpeg tail tests (plan v1.3 §2, NB-2): real media, not arithmetic."""
import json
import shutil
import subprocess

import pytest

import local_media as lm

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not available")


def _make_fixture(path, w, h, audio=True, seconds=1):
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate=24:duration={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    cmd += (["-c:a", "aac", "-shortest"] if audio else ["-an"])
    cmd += [str(path)]
    subprocess.run(cmd, capture_output=True, check=True)


def _streams(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out)["streams"]


def test_wan_crop_736_to_720_with_audio(tmp_path):
    src = tmp_path / "src.mp4"
    _make_fixture(src, 1280, 736)
    dst = tmp_path / "out.mp4"
    lm.finalize_video(src, dst, 1280, 720)
    s = _streams(dst)
    v = [x for x in s if x["codec_type"] == "video"][0]
    assert (v["width"], v["height"]) == (1280, 720)
    assert any(x["codec_type"] == "audio" for x in s), "audio must be retained"
    assert dst.read_bytes()[4:8] == b"ftyp"
    assert not list(tmp_path.glob(".*tmp")), "temp file left behind"


def test_ltx_crop_768_to_720(tmp_path):
    src = tmp_path / "src.mp4"
    _make_fixture(src, 1280, 768)
    dst = tmp_path / "out.mp4"
    lm.finalize_video(src, dst, 1280, 720)
    v = [x for x in _streams(dst) if x["codec_type"] == "video"][0]
    assert (v["width"], v["height"]) == (1280, 720)


def test_exact_dims_rename_only(tmp_path):
    src = tmp_path / "src.mp4"
    _make_fixture(src, 1088, 1920, seconds=0.5)
    before = src.read_bytes()
    dst = tmp_path / "out.mp4"
    lm.finalize_video(src, dst, 1088, 1920)
    assert dst.read_bytes() == before, "exact dims must publish by rename, no re-encode"
    assert not src.exists()


def test_smaller_source_refused_no_padding(tmp_path):
    src = tmp_path / "src.mp4"
    _make_fixture(src, 640, 360, audio=False, seconds=0.5)
    dst = tmp_path / "out.mp4"
    with pytest.raises(lm.TailError):
        lm.finalize_video(src, dst, 1280, 720)
    assert not dst.exists()


def test_corrupt_source_fails_no_dst(tmp_path):
    src = tmp_path / "src.mp4"
    src.write_bytes(b"not a video")
    dst = tmp_path / "out.mp4"
    with pytest.raises(lm.TailError):
        lm.finalize_video(src, dst, 1280, 720)
    assert not dst.exists()
