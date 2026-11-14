"""Parameterized LTX-2.5 Q3 I2V graph (plan v1.3 §4).

Derived node-for-node from the proven shared-service pilot graph
(tests/fixtures/ltx_q3_pilot.json, sha256-pinned). Fixed nodes stay byte-faithful;
only the documented fields are parameterized. The distilled schedule is fixed
(8+3 sigmas, dual CFG 1.0) — engine steps/guidance are intentionally not inputs.
Stage-1 dims round UP to /32; the x2 upsample therefore never undershoots the
request, and the shared ffmpeg tail center-crops to the exact requested size.

The pinned fixture is normative; node numbers in plan prose are indicative.
"""
from __future__ import annotations

import math
import random

UNET_GGUF = "ltx-2.5-22b-distilled-UD-Q3_K_XL.gguf"
TEXT_ENCODER = "gemma4-12b-with-proj-ltx-2.5-nvfp4.safetensors"
VIDEO_VAE = "ltx-2.5-video-vae-conv-bf16.safetensors"
AUDIO_VAE = "ltx-2.5-audio-vae-bf16.safetensors"
UPSCALER = "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors"
STAGE1_SIGMAS = "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"
STAGE2_SIGMAS = "0.85, 0.7250, 0.4219, 0.0"
MIN_FRAMES = 17


def stage1_dims(width: int, height: int) -> tuple[int, int]:
    """Half-resolution, each dim rounded UP to a multiple of 32."""
    return 32 * math.ceil(width / 64), 32 * math.ceil(height / 64)


def final_dims(width: int, height: int) -> tuple[int, int]:
    """The x2-upsampled generation size; always >= the request (never pads)."""
    w1, h1 = stage1_dims(width, height)
    return w1 * 2, h1 * 2


def snap_frames(n: int) -> int:
    """Nearest 8k+1, minimum 17; ties round UP (explicit, tested)."""
    n = max(n, MIN_FRAMES)
    k = math.floor((n - 1) / 8 + 0.5)
    return max(8 * k + 1, MIN_FRAMES)


def build_ltx_workflow(
    prompt: str,
    negative_prompt: str,
    image_name: str,
    width: int,
    height: int,
    num_frames: int,
    fps: int,
    seed: int | None,
    job_id: str,
    filename_prefix: str | None = None,
) -> dict:
    w1, h1 = stage1_dims(width, height)
    frames = snap_frames(num_frames)
    if seed is None:
        seed = random.randint(0, 2**63 - 1)  # one draw, reused in both noise nodes
    prefix = filename_prefix if filename_prefix is not None else f"ltx25-engine/{job_id}"
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": UNET_GGUF}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": TEXT_ENCODER, "type": "ltxv", "device": "default"}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": negative_prompt, "clip": ["2", 0]}},
        "5": {"class_type": "LTXVConditioning", "inputs": {"positive": ["3", 0], "negative": ["4", 0], "frame_rate": float(fps)}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": VIDEO_VAE}},
        "7": {"class_type": "VAELoader", "inputs": {"vae_name": AUDIO_VAE}},
        "8": {"class_type": "EmptyLTXVLatentVideo", "inputs": {"width": w1, "height": h1, "length": frames, "batch_size": 1}},
        "9": {"class_type": "LTXVEmptyLatentAudio", "inputs": {"frames_number": frames, "frame_rate": fps, "batch_size": 1, "audio_vae": ["7", 0]}},
        "10": {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": ["33", 0], "audio_latent": ["9", 0]}},
        "11": {"class_type": "LTXVDualCFGGuider", "inputs": {"model": ["1", 0], "positive": ["5", 0], "negative": ["5", 1], "video_cfg": 1.0, "audio_cfg": 1.0}},
        "12": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "13": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral"}},
        "14": {"class_type": "ManualSigmas", "inputs": {"sigmas": STAGE1_SIGMAS}},
        "15": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["12", 0], "guider": ["11", 0], "sampler": ["13", 0], "sigmas": ["14", 0], "latent_image": ["10", 0]}},
        "16": {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["15", 0]}},
        "17": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["27", 0], "vae": ["6", 0], "tile_size": 256, "overlap": 64, "temporal_size": 64, "temporal_overlap": 16}},
        "18": {"class_type": "LTXVAudioVAEDecode", "inputs": {"samples": ["27", 1], "audio_vae": ["7", 0]}},
        "19": {"class_type": "CreateVideo", "inputs": {"images": ["17", 0], "audio": ["18", 0], "fps": float(fps)}},
        "20": {"class_type": "SaveVideo", "inputs": {"video": ["19", 0], "filename_prefix": prefix, "format": "auto", "codec": "h264"}},
        "21": {"class_type": "LatentUpscaleModelLoader", "inputs": {"model_name": UPSCALER}},
        "22": {"class_type": "LTXVLatentUpsampler", "inputs": {"samples": ["16", 0], "upscale_model": ["21", 0], "vae": ["6", 0]}},
        "23": {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": ["34", 0], "audio_latent": ["16", 1]}},
        "24": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "25": {"class_type": "ManualSigmas", "inputs": {"sigmas": STAGE2_SIGMAS}},
        "26": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["24", 0], "guider": ["11", 0], "sampler": ["13", 0], "sigmas": ["25", 0], "latent_image": ["23", 0]}},
        "27": {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["26", 0]}},
        "31": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "32": {"class_type": "LTXVPreprocess", "inputs": {"image": ["31", 0], "img_compression": 18}},
        "33": {"class_type": "LTXVImgToVideoInplace", "inputs": {"vae": ["6", 0], "image": ["32", 0], "latent": ["8", 0], "strength": 0.7, "bypass": False}},
        "34": {"class_type": "LTXVImgToVideoInplace", "inputs": {"vae": ["6", 0], "image": ["32", 0], "latent": ["22", 0], "strength": 1.0, "bypass": False}},
    }
