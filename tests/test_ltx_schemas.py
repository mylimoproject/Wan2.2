"""LTX schema/config tests (plan v1.3 Step 2)."""
import pytest
from pydantic import ValidationError

from ltx_service import config
from ltx_service.schemas import GenerateRequest

SHA = "a" * 64


def base(**over):
    d = dict(prompt="a van", image_path="locksmith-van-front.png", image_sha256=SHA)
    d.update(over)
    return d


def test_valid_full_request():
    r = GenerateRequest(**base(width=1280, height=720, num_frames=97, fps=24,
                               num_inference_steps=50, guidance_scale=5.0, seed=1,
                               model_variant="ltx-2.5-q3", output_format="mp4"))
    assert r.image_sha256 == SHA
    assert r.seed == 1


def test_sha_uppercase_normalized():
    r = GenerateRequest(**base(image_sha256="A" * 64))
    assert r.image_sha256 == SHA


def test_image_path_required():
    d = base()
    del d["image_path"]
    with pytest.raises(ValidationError):
        GenerateRequest(**d)


def test_image_sha256_required():
    d = base()
    del d["image_sha256"]
    with pytest.raises(ValidationError):
        GenerateRequest(**d)


@pytest.mark.parametrize("bad", ["xyz", "a" * 63, "a" * 65, "g" * 64, ""])
def test_bad_sha(bad):
    with pytest.raises(ValidationError):
        GenerateRequest(**base(image_sha256=bad))


def test_variant_mismatch_refused():
    with pytest.raises(ValidationError):
        GenerateRequest(**base(model_variant="ltx-2.5"))


def test_variant_omitted_gets_served_default():
    r = GenerateRequest(**base())
    assert r.model_variant == config.SERVED_VARIANT == "ltx-2.5-q3"


def test_seed_null_allowed():
    assert GenerateRequest(**base(seed=None)).seed is None


@pytest.mark.parametrize("field,val", [("width", 0), ("height", -32), ("num_frames", 8), ("fps", 0), ("width", 8192)])
def test_bad_numbers(field, val):
    with pytest.raises(ValidationError):
        GenerateRequest(**base(**{field: val}))


def test_output_format_must_be_mp4():
    with pytest.raises(ValidationError):
        GenerateRequest(**base(output_format="webm"))


def test_empty_prompt_refused():
    with pytest.raises(ValidationError):
        GenerateRequest(**base(prompt="   "))


def test_config_isolation():
    # conftest redirected LTX_OUTPUT_DIR before import; depth is pinned to 1
    assert str(config.OUTPUT_DIR).startswith("/tmp/") or "hg2" in str(config.OUTPUT_DIR)
    assert config.MAX_QUEUE_DEPTH == 1
    assert config.JOB_TIMEOUT_SECONDS == 900.0
