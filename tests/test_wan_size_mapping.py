"""WAN size mapping (plan v1.3 §4b): TI2V-5B requires /32 dimensions
(vae_stride 16 x patch 2); 720 is invalid. Round UP, never pad; the shared
ffmpeg tail center-crops back to the exact requested size."""
import pytest

from wan_service.worker import build_wan22_workflow, map_size


@pytest.mark.parametrize("req,gen", [
    ((1280, 720), (1280, 736)),
    ((704, 1280), (704, 1280)),
    ((1080, 1920), (1088, 1920)),
    ((64, 64), (64, 64)),
    ((65, 65), (96, 96)),
    ((1280, 736), (1280, 736)),
    ((1920, 1080), (1920, 1088)),
])
def test_map_size(req, gen):
    assert map_size(*req) == gen


def test_never_undershoots_and_always_32_grid():
    for w in range(64, 1400, 37):
        for h in range(64, 1400, 41):
            gw, gh = map_size(w, h)
            assert gw >= w and gh >= h
            assert gw % 32 == 0 and gh % 32 == 0
            assert gw - w < 32 and gh - h < 32


def test_graph_uses_generated_size_for_embeds_and_still():
    g = build_wan22_workflow("p", "n", 1280, 720, 97, 10, 1, image_name="s.png")
    assert g["5"]["inputs"]["width"] == 1280
    assert g["5"]["inputs"]["height"] == 736
    assert g["11"]["inputs"]["width"] == 1280
    assert g["11"]["inputs"]["height"] == 736


def test_proven_shape_passes_through_unchanged():
    g = build_wan22_workflow("p", "n", 704, 1280, 17, 10, 1)
    assert g["5"]["inputs"]["width"] == 704
    assert g["5"]["inputs"]["height"] == 1280