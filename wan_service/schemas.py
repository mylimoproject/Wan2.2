"""Pydantic request/response schemas."""
from typing import Optional
from pydantic import BaseModel


class GenerateRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = None
    image_path: Optional[str] = None
    width: int = 1280
    height: int = 720
    num_frames: int = 97
    fps: int = 24
    num_inference_steps: int = 50
    guidance_scale: float = 5.0
    seed: Optional[int] = None
    model_variant: str = "5b"
    output_format: str = "mp4"


class GenerateResponse(BaseModel):
    job_id: str
    status: str = "queued"
    gpu: int
    estimated_seconds: int = 180


class StatusResponse(BaseModel):
    job_id: str
    status: str
    progress: float = 0.0
    gpu: int
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class GpuStatus(BaseModel):
    id: int
    model: str
    loaded: bool
    busy: bool
    vram_used_gb: float
    vram_total_gb: float


class HealthResponse(BaseModel):
    status: str
    gpus: list[GpuStatus]
    queue_depth: int
    version: str = "0.1.0"


class ErrorResponse(BaseModel):
    error: str
    detail: str
    job_id: Optional[str] = None
