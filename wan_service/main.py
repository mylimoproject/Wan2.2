"""FastAPI application for Wan2.2 local video generation."""
import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .config import HOST, PORT, MODEL_PATH, GPU_IDS
from .schemas import GenerateRequest, GenerateResponse, StatusResponse, HealthResponse, GpuStatus, ErrorResponse
from .worker import WorkerPool, estimate_seconds


pool: WorkerPool = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = WorkerPool(GPU_IDS)
    await pool.start()
    yield
    # cleanup on shutdown


app = FastAPI(title="Wan2.2 Video Service", version="0.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
async def health():
    gpus = [GpuStatus(**g) for g in pool.health()]
    return HealthResponse(
        status="ok",
        gpus=gpus,
        queue_depth=pool.total_queue_depth(),
    )


@app.post("/generate", response_model=GenerateResponse, status_code=202)
async def generate(req: GenerateRequest):
    try:
        job = await pool.submit(req)
    except RuntimeError as e:
        if str(e) == "queue_full":
            raise HTTPException(status_code=429, detail="Queue full")
        raise HTTPException(status_code=503, detail=str(e))
    return GenerateResponse(
        job_id=job.job_id,
        status=job.status,
        gpu=job.gpu_id,
        estimated_seconds=estimate_seconds(req),
    )


@app.get("/status/{job_id}", response_model=StatusResponse)
async def status(job_id: str):
    job = pool.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return StatusResponse(
        job_id=job.job_id,
        status=job.status,
        progress=job.progress,
        gpu=job.gpu_id,
        error=job.error,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@app.get("/output/{job_id}")
async def output(job_id: str):
    job = pool.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed":
        raise HTTPException(status_code=404, detail="Output not ready")
    if not job.output_path or not Path(job.output_path).exists():
        raise HTTPException(status_code=404, detail="Output file missing")
    return FileResponse(job.output_path, media_type="video/mp4", filename="{}.mp4".format(job_id))


@app.post("/cancel/{job_id}")
async def cancel(job_id: str):
    job = pool.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in ("completed", "failed"):
        raise HTTPException(status_code=409, detail="Job already finished")
    job.status = "cancelled"
    return {"cancelled": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, workers=1)
