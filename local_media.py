"""Shared stills snapshot guard + exact-size ffmpeg tail for the local wrappers.

Plan v1.3 §2 (HG-2): the bytes hashed are the bytes staged; the staged name is
unique per job; the source is read exactly once through a symlink-free
descriptor; nothing is written through a pre-existing link; the tail never pads.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path, PurePosixPath

MAX_STILL_BYTES = 64 * 1024 * 1024
_COMPONENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class StillsError(ValueError):
    """Definite admission failure; the HTTP layer maps it to 400 {error, detail}."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class TailError(RuntimeError):
    """The exact-size tail failed; the job stays failed and nothing is published."""


def _open_contained(root: Path, rel: str) -> int:
    """Open rel under root without following ANY symlink, walking dir descriptors.

    Each component is opened with O_NOFOLLOW relative to the previous dir fd, so
    ancestor or final-component symlink substitution cannot escape the root.
    Returns an owned fd for a regular file; raises StillsError otherwise.
    """
    p = PurePosixPath(rel)
    if p.is_absolute() or not p.parts:
        raise StillsError("still_path_invalid", f"not a relative path: {rel!r}")
    for part in p.parts:
        if part in (".", "..") or not _COMPONENT_RE.match(part):
            raise StillsError("still_path_invalid", f"unsafe path component: {part!r}")
    try:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    except FileNotFoundError:
        raise StillsError("still_not_found", f"stills root missing: {root}") from None
    except OSError as e:
        raise StillsError("still_io_error", f"stills root: {e}") from None
    try:
        for i, part in enumerate(p.parts):
            # O_NONBLOCK: opening a FIFO with O_RDONLY would block until a writer
            # appears; the fstat regular-file check below must get a chance to run.
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if i < len(p.parts) - 1:
                flags |= os.O_DIRECTORY
            try:
                nfd = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                raise StillsError("still_not_found", f"missing: {rel}") from None
            except OSError as e:
                raise StillsError("still_path_invalid", f"cannot open {part!r} without following links: {e}") from None
            os.close(fd)
            fd = nfd
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise StillsError("still_not_regular", f"not a regular file: {rel}")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read_all(fd: int, max_bytes: int) -> bytes:
    chunks = []
    total = 0
    while True:
        b = os.read(fd, 1024 * 1024)
        if not b:
            break
        total += len(b)
        if total > max_bytes:
            raise StillsError("still_too_large", f"still exceeds {max_bytes} bytes")
        chunks.append(b)
    return b"".join(chunks)


def stage_still(stills_root, image_path: str, image_sha256: str, input_dir, job_id: str, max_bytes: int = MAX_STILL_BYTES) -> str:
    """Validate + snapshot the still; return the ComfyUI-side filename.

    Reads the source exactly once through a symlink-free descriptor, hashes
    those bytes, compares to image_sha256, and writes those same bytes to a
    unique exclusive destination. On any failure nothing is left behind.
    """
    root = Path(stills_root)
    if not _JOB_ID_RE.match(job_id):
        raise StillsError("still_path_invalid", f"bad job id: {job_id!r}")
    expected = (image_sha256 or "").lower()
    if not _HEX64_RE.match(expected):
        raise StillsError("still_hash_invalid", "image_sha256 must be 64 hex chars")
    basename = PurePosixPath(image_path).name
    fd = _open_contained(root, image_path)
    try:
        data = _read_all(fd, max_bytes)
    finally:
        os.close(fd)
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise StillsError("still_hash_mismatch", f"expected {expected}, got {actual}")
    dst = Path(input_dir) / f"{job_id}-{basename}"
    try:
        with open(dst, "xb") as f:
            f.write(data)
    except FileExistsError:
        raise StillsError("still_dest_exists", f"destination already exists: {dst.name}") from None
    except OSError as e:
        try:
            os.unlink(dst)
        except OSError:
            pass
        raise StillsError("still_io_error", f"staging write failed: {e}") from None
    return dst.name


def cleanup_staged(input_dir, staged_name: str) -> None:
    """Remove a staged copy. Call only when the job is terminal AND its owned
    ComfyUI prompt is absent/terminal AND the executor has quiesced (§2.4)."""
    if not _COMPONENT_RE.match(staged_name):
        return
    try:
        os.unlink(Path(input_dir) / staged_name)
    except FileNotFoundError:
        pass


def probe_size(src: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", str(src)],
        capture_output=True, text=True, check=True,
    ).stdout
    s = json.loads(out)["streams"][0]
    return int(s["width"]), int(s["height"])


def finalize_video(src, dst, width: int, height: int) -> None:
    """Center-crop to exact width x height (audio stream-copied), publish atomically.

    Exact-dimension sources are published by atomic rename alone (no re-encode).
    Smaller sources are refused — padding is forbidden. Raises TailError on any
    failure; never leaves a partial dst or a temp file behind.
    """
    src, dst = Path(src), Path(dst)
    try:
        w, h = probe_size(src)
    except (subprocess.CalledProcessError, KeyError, IndexError, ValueError, json.JSONDecodeError) as e:
        raise TailError(f"ffprobe failed: {e}") from None
    if (w, h) == (width, height):
        os.replace(src, dst)
        return
    if w < width or h < height:
        raise TailError(f"source {w}x{h} smaller than target {width}x{height}; padding is forbidden")
    tmp = dst.with_name(f".{dst.name}.tmp")
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-vf", f"crop={width}:{height}:(iw-{width})/2:(ih-{height})/2",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", "-f", "mp4", str(tmp),
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        os.replace(tmp, dst)
    except subprocess.CalledProcessError as e:
        raise TailError(f"ffmpeg failed: {(e.stderr or '')[-400:]}") from None
    except OSError as e:
        raise TailError(f"publish failed: {e}") from None
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
