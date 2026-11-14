"""Stills snapshot guard tests (plan v1.3 §2.5)."""
import hashlib
import os

import pytest

import local_media as lm

SHA = hashlib.sha256(b"still-bytes").hexdigest()


@pytest.fixture()
def root(tmp_path):
    r = tmp_path / "stills"
    r.mkdir()
    (r / "img.png").write_bytes(b"still-bytes")
    return r


@pytest.fixture()
def indir(tmp_path):
    d = tmp_path / "input"
    d.mkdir()
    return d


def stage(root, indir, name="img.png", sha=SHA, job="gen-job1", **kw):
    return lm.stage_still(root, name, sha, indir, job, **kw)


def test_happy_path_bytes_and_name(root, indir):
    name = stage(root, indir)
    assert name == "gen-job1-img.png"
    assert (indir / name).read_bytes() == b"still-bytes"


def test_relative_nested_join(root, indir):
    (root / "sub").mkdir()
    (root / "sub" / "img2.png").write_bytes(b"nested")
    sha = hashlib.sha256(b"nested").hexdigest()
    name = stage(root, indir, "sub/img2.png", sha)
    assert name == "gen-job1-img2.png"
    assert (indir / name).read_bytes() == b"nested"


@pytest.mark.parametrize("bad", ["../escape.png", "/abs/img.png", "a/../../x.png", "img .png", "name [output].png", ""])
def test_unsafe_paths_refused(root, indir, bad):
    with pytest.raises(lm.StillsError) as e:
        stage(root, indir, bad)
    assert e.value.code == "still_path_invalid"
    assert list(indir.iterdir()) == []


def test_final_symlink_refused(root, indir, tmp_path):
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside")
    (root / "link.png").symlink_to(outside)
    with pytest.raises(lm.StillsError) as e:
        stage(root, indir, "link.png", hashlib.sha256(b"outside").hexdigest())
    assert e.value.code == "still_path_invalid"
    assert list(indir.iterdir()) == []


def test_ancestor_symlink_refused(root, indir, tmp_path):
    outside = tmp_path / "outdir"
    outside.mkdir()
    (outside / "img.png").write_bytes(b"outside")
    (root / "sub").symlink_to(outside, target_is_directory=True)
    with pytest.raises(lm.StillsError) as e:
        stage(root, indir, "sub/img.png", hashlib.sha256(b"outside").hexdigest())
    assert e.value.code == "still_path_invalid"


def test_missing(root, indir):
    with pytest.raises(lm.StillsError) as e:
        stage(root, indir, "nope.png")
    assert e.value.code == "still_not_found"


def test_not_regular(root, indir):
    os.mkfifo(root / "fifo.png")
    with pytest.raises(lm.StillsError) as e:
        stage(root, indir, "fifo.png")
    assert e.value.code == "still_not_regular"


def test_hash_mismatch_no_dst(root, indir):
    with pytest.raises(lm.StillsError) as e:
        stage(root, indir, sha="0" * 64)
    assert e.value.code == "still_hash_mismatch"
    assert list(indir.iterdir()) == []


def test_bad_sha_format(root, indir):
    with pytest.raises(lm.StillsError) as e:
        stage(root, indir, sha="xyz")
    assert e.value.code == "still_hash_invalid"


def test_too_large(root, indir):
    with pytest.raises(lm.StillsError) as e:
        stage(root, indir, max_bytes=4)
    assert e.value.code == "still_too_large"
    assert list(indir.iterdir()) == []


def test_dest_exists_not_overwritten(root, indir):
    (indir / "gen-job1-img.png").write_bytes(b"precious")
    with pytest.raises(lm.StillsError) as e:
        stage(root, indir)
    assert e.value.code == "still_dest_exists"
    assert (indir / "gen-job1-img.png").read_bytes() == b"precious"


def test_dest_symlink_not_followed(root, indir, tmp_path):
    victim = tmp_path / "victim"
    victim.write_bytes(b"victim")
    (indir / "gen-job1-img.png").symlink_to(victim)
    with pytest.raises(lm.StillsError) as e:
        stage(root, indir)
    assert e.value.code == "still_dest_exists"
    assert victim.read_bytes() == b"victim"


def test_same_basename_concurrent_jobs(root, indir):
    n1 = stage(root, indir, job="gen-a")
    n2 = stage(root, indir, job="gen-b")
    assert n1 != n2
    assert (indir / n1).read_bytes() == (indir / n2).read_bytes() == b"still-bytes"


def test_fd_pins_bytes_against_replacement(root, indir):
    # Deterministic race: swap the path AFTER the descriptor is open; the bytes
    # read through the descriptor must still be the original ones.
    fd = lm._open_contained(root, "img.png")
    try:
        (root / "img.png").unlink()
        (root / "img.png").write_bytes(b"REPLACED")
        data = lm._read_all(fd, lm.MAX_STILL_BYTES)
    finally:
        os.close(fd)
    assert data == b"still-bytes"


def test_cleanup(root, indir):
    name = stage(root, indir)
    lm.cleanup_staged(indir, name)
    assert not (indir / name).exists()
    lm.cleanup_staged(indir, name)  # idempotent


def test_bad_job_id(root, indir):
    with pytest.raises(lm.StillsError) as e:
        stage(root, indir, job="bad/id")
    assert e.value.code == "still_path_invalid"
