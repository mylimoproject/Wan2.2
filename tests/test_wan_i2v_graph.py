"""WAN I2V chain + T2V golden (plan v1.3 §§3, 4b, NB-7). The 14B
WanVideoImageToVideoEncode channel-concat path crashes on 5B; the chain here is
LoadImage -> ImageScale -> WanVideoEncode -> WanVideoEmptyEmbeds.extra_latents.
INPUT_TYPES confirmed on the peer 2026-11-14: WanVideoEncode requires vae,
image and the five tile scalars; extra_latents is an optional LATENT input."""
import hashlib
import json
from pathlib import Path

from wan_service.worker import build_wan22_workflow

FIXTURE = Path(__file__).parent / "fixtures" / "wan_t2v_golden.json"
FIXTURE_SHA = "daf4a3c2ce60972e7082c3436be598b742cdb38b05e0d8cb4981fb23c33de74d"


def _golden():
    return build_wan22_workflow("golden probe", "", 704, 1280, 17, 10, 42)


def test_fixture_pin():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA


def test_t2v_golden_prompt_object_exact():
    assert _golden() == json.loads(FIXTURE.read_text())


def test_t2v_golden_byte_identical():
    got = json.dumps(_golden(), sort_keys=True, indent=2)
    assert got == FIXTURE.read_text().rstrip("\n")


def test_i2v_chain_all_required_encode_inputs():
    g = build_wan22_workflow("p", "n", 1280, 720, 97, 10, 7, image_name="gen-x-van.png")
    assert g["10"] == {"class_type": "LoadImage", "inputs": {"image": "gen-x-van.png"}}
    assert g["11"]["class_type"] == "ImageScale"
    i = g["11"]["inputs"]
    assert i["image"] == ["10", 0]
    assert i["upscale_method"] == "lanczos"
    assert i["crop"] == "center"
    assert i["width"] == 1280 and i["height"] == 736
    assert g["12"]["class_type"] == "WanVideoEncode"
    # ALL required inputs incl. the five tile scalars (NB-7: missing → /prompt 400)
    assert g["12"]["inputs"] == {
        "vae": ["2", 0],
        "image": ["11", 0],
        "enable_vae_tiling": False,
        "tile_x": 272,
        "tile_y": 272,
        "tile_stride_x": 144,
        "tile_stride_y": 128,
    }
    assert g["5"]["inputs"]["extra_latents"] == ["12", 0]
    assert g["6"]["inputs"]["image_embeds"] == ["5", 0]


def test_t2v_has_no_i2v_nodes():
    g = build_wan22_workflow("p", "n", 704, 1280, 17, 10, 1)
    assert "10" not in g and "11" not in g and "12" not in g
    assert "extra_latents" not in g["5"]["inputs"]


def test_guidance_wired_t2v_and_i2v():
    assert build_wan22_workflow("p", "n", 704, 1280, 17, 10, 1)["6"]["inputs"]["cfg"] == 5.0
    assert build_wan22_workflow("p", "n", 704, 1280, 17, 10, 1, guidance_scale=3.5)["6"]["inputs"]["cfg"] == 3.5
    g = build_wan22_workflow("p", "n", 1280, 720, 17, 10, 1, guidance_scale=2.0, image_name="s.png")
    assert g["6"]["inputs"]["cfg"] == 2.0


def test_seed_null_one_draw():
    g = build_wan22_workflow("p", "n", 704, 1280, 17, 10, None)
    assert isinstance(g["6"]["inputs"]["seed"], int)


def test_fps_hardcoded_24_documented():
    for image in (None, "s.png"):
        g = build_wan22_workflow("p", "n", 1280, 720, 17, 10, 1, image_name=image)
        assert g["8"]["inputs"]["fps"] == 24.0


def test_no_dangling_links():
    for image in (None, "s.png"):
        g = build_wan22_workflow("p", "n", 1280, 720, 97, 10, 1, image_name=image)
        for node in g.values():
            for v in node["inputs"].values():
                if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                    assert v[0] in g, f"dangling link to {v[0]}"