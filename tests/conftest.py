"""Hermetic test setup (plan v1.3 §0.7, NB-1).

HOME and both output dirs are redirected to temp BEFORE any application import;
the worktree root is on sys.path; a session fixture asserts the LIVE home's
calibration.json and outputs directory were not touched by the tests.
"""
import hashlib
import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_REAL_HOME = Path(os.environ.get("HOME", str(Path.home())))
_CAL = _REAL_HOME / ".local" / "share" / "wan2.2" / "calibration.json"
_OUT = _REAL_HOME / ".local" / "share" / "wan2.2" / "outputs"


def _sig(path: Path):
    if not path.exists():
        return None
    return (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())


_CAL_SIG = _sig(_CAL)
_OUT_SIG = sorted(p.name for p in _OUT.iterdir()) if _OUT.exists() else None

_TMP = Path(tempfile.mkdtemp(prefix="hg2-tests-"))
(_TMP / "home").mkdir(parents=True, exist_ok=True)
os.environ["HOME"] = str(_TMP / "home")
os.environ["WAN_OUTPUT_DIR"] = str(_TMP / "wan-out")
os.environ["LTX_OUTPUT_DIR"] = str(_TMP / "ltx-out")
os.environ["WAN_PROGRESS_WS"] = "0"  # hermetic: no websocket to the live ComfyUI

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _real_home_unchanged():
    yield
    assert _sig(_CAL) == _CAL_SIG, "tests wrote into the LIVE calibration.json"
    now = sorted(p.name for p in _OUT.iterdir()) if _OUT.exists() else None
    assert now == _OUT_SIG, "tests wrote into the LIVE outputs directory"
