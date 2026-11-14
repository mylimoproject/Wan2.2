"""Golden graph test (plan v1.3 §3): the builder must reproduce the proven Q3
pilot prompt object node-for-node, and parameterize exactly the documented fields.
The pinned fixture is normative; plan-prose node numbers are indicative."""
import hashlib
import json
from pathlib import Path

from ltx_service.graph import build_ltx_workflow

FIXTURE = Path(__file__).parent / "fixtures" / "ltx_q3_pilot.json"
FIXTURE_SHA = "8df04851a885d136a6ec20de2235a7d65c62c6f3dfd5ebfc7fc33b40a485c6c0"

PILOT_PROMPT = (
    "The woman stands by the white SUV in the sunny parking lot and briefly checks her phone. "
    "Subtle natural movements and a gentle stationary handheld camera. Maintain her appearance, "
    "outfit, and the car. No text or logos."
)
PILOT_NEG = "blurry, distorted, cartoon"
PILOT_PREFIX = "ltx25-hermes-hires/q3-default-i2v-pilot-1088x1920"


def _pilot():
    return build_ltx_workflow(
        prompt=PILOT_PROMPT, negative_prompt=PILOT_NEG,
        image_name="locksmith-pilot-reference-front.png",
        width=1080, height=1920, num_frames=121, fps=24,
        seed=42, job_id="gen-golden", filename_prefix=PILOT_PREFIX,
    )


def test_fixture_pin():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA


def test_golden_prompt_object_exact():
    # the fixture is the full API envelope; the golden compares the PROMPT OBJECT
    expected = json.loads(FIXTURE.read_text())["prompt"]
    assert _pilot() == expected


def test_parameterized_fields_vary():
    g = build_ltx_workflow("p", "n", "staged.png", 1280, 720, 97, 24, 7, "gen-x")
    assert g["3"]["inputs"]["text"] == "p"
    assert g["4"]["inputs"]["text"] == "n"
    assert g["31"]["inputs"]["image"] == "staged.png"
    assert g["8"]["inputs"]["width"] == 640 and g["8"]["inputs"]["height"] == 384
    assert g["8"]["inputs"]["length"] == 97
    assert g["9"]["inputs"]["frames_number"] == 97
    assert g["5"]["inputs"]["frame_rate"] == 24.0
    assert g["9"]["inputs"]["frame_rate"] == 24
    assert g["19"]["inputs"]["fps"] == 24.0
    assert g["12"]["inputs"]["noise_seed"] == 7 == g["24"]["inputs"]["noise_seed"]
    assert g["20"]["inputs"]["filename_prefix"] == "ltx25-engine/gen-x"


def test_seed_null_one_draw_reused():
    g = build_ltx_workflow("p", "n", "s.png", 1280, 720, 97, 24, None, "gen-y")
    s1 = g["12"]["inputs"]["noise_seed"]
    assert isinstance(s1, int)
    assert s1 == g["24"]["inputs"]["noise_seed"]


def test_fixed_distilled_schedule_and_cfg():
    g = build_ltx_workflow("p", "n", "s.png", 1280, 720, 97, 24, 1, "gen-z")
    assert g["14"]["inputs"]["sigmas"].count(",") == 8  # 9 values = 8 steps
    assert g["25"]["inputs"]["sigmas"].count(",") == 3  # 4 values = 3 steps
    assert g["11"]["inputs"]["video_cfg"] == 1.0 and g["11"]["inputs"]["audio_cfg"] == 1.0
    assert g["15"]["inputs"]["guider"] == ["11", 0] == g["26"]["inputs"]["guider"]  # shared guider
    assert g["33"]["inputs"]["strength"] == 0.7 and g["34"]["inputs"]["strength"] == 1.0
    assert g["20"]["inputs"]["codec"] == "h264" and g["20"]["inputs"]["format"] == "auto"
    assert g["18"]["class_type"] == "LTXVAudioVAEDecode"  # audio path kept
    assert g["9"]["class_type"] == "LTXVEmptyLatentAudio"


def test_no_dangling_links():
    g = build_ltx_workflow("p", "n", "s.png", 1280, 720, 97, 24, 1, "gen-w")
    for node in g.values():
        for v in node["inputs"].values():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                assert v[0] in g, f"dangling link to {v[0]}"
