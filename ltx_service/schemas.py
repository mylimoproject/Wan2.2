"""Request/response schemas (plan v1.3 §1). The engine adapter pins these fields;
LTX is I2V-only, so image_path and image_sha256 are required. Validation errors
become 400 {error, detail} via the app's RequestValidationError handler."""
import re
from typing import Optional

from pydantic import BaseModel, field_validator

from .config import SERVED_VARIANT

_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


class GenerateRequest(BaseModel):
    prompt: str
    negative_prompt: str = ""
    image_path: str
    image_sha256: str
    width: int = 1280
    height: int = 720
    num_frames: int = 97
    fps: int = 24
    num_inference_steps: int = 8
    guidance_scale: float = 1.0
    seed: Optional[int] = None
    model_variant: str = SERVED_VARIANT
    output_format: str = "mp4"

    @field_validator("prompt")
    @classmethod
    def _prompt_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("prompt must be non-empty")
        return v

    @field_validator("image_path")
    @classmethod
    def _image_path_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("image_path must be non-empty (LTX is I2V-only)")
        return v

    @field_validator("image_sha256")
    @classmethod
    def _hex64(cls, v: str) -> str:
        if not _HEX64.match(v):
            raise ValueError("image_sha256 must be 64 hex chars")
        return v.lower()

    @field_validator("model_variant")
    @classmethod
    def _served_variant(cls, v: str) -> str:
        if v != SERVED_VARIANT:
            raise ValueError(f"unsupported model_variant {v!r}; served: {SERVED_VARIANT}")
        return v

    @field_validator("width", "height")
    @classmethod
    def _dims(cls, v: int) -> int:
        if v < 64 or v > 4096:
            raise ValueError("dimensions must be within [64, 4096]")
        return v

    @field_validator("num_frames")
    @classmethod
    def _frames(cls, v: int) -> int:
        if v < 17 or v > 1001:
            raise ValueError("num_frames must be within [17, 1001]")
        return v

    @field_validator("fps")
    @classmethod
    def _fps(cls, v: int) -> int:
        if v < 1 or v > 60:
            raise ValueError("fps must be within [1, 60]")
        return v

    @field_validator("output_format")
    @classmethod
    def _mp4(cls, v: str) -> str:
        if v != "mp4":
            raise ValueError("output_format must be 'mp4'")
        return v


class GenerateResponse(BaseModel):
    job_id: str


class StatusResponse(BaseModel):
    status: str
    error: Optional[str] = None
    progress: Optional[float] = None
