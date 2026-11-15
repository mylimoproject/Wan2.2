"""WAN wrapper HTTP surface (plan v1.3 §§1, 2). Admission is synchronous and
runs BEFORE the 202: schema → variant → busy/unavailable → stills last (I2V
only; T2V skips staging). No ComfyUI prompt is submitted at admission; /prompt
happens in the worker."""
from __future__ import annotations

import asyncio
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from . import config
from .schemas import GenerateRequest
from .worker import ComfyUIClient, ComfyUnavailable, WanWorker
from local_media import StillsError, stage_still


def create_app(client=None, worker=None) -> FastAPI:
    app = FastAPI(title="Wan2.2 local wrapper", redirect_slashes=False)
    client = client if client is not None else ComfyUIClient(config.COMFYUI_URL)
    worker = worker if worker is not None else WanWorker(client)
    admission_lock = asyncio.Lock()
    app.state.client = client
    app.state.worker = worker

    @app.exception_handler(RequestValidationError)
    async def _validation(_req: Request, exc: RequestValidationError):
        return JSONResponse(status_code=400, content={
            "error": "validation_failed",
            "detail": str(exc.errors()[:3])[:200],
        })

    @app.get("/health")
    async def health():
        # Interlock: refuse when ComfyUI is unhealthy or busy — the engine then
        # declines at its health gate before any ledger write, costing no attempt.
        try:
            await asyncio.to_thread(client.system_stats)
            q = await asyncio.to_thread(client.queue)
        except ComfyUnavailable:
            return JSONResponse(status_code=503, content={"status": "unavailable", "error": "comfyui_unavailable"})
        if q.get("queue_running") or q.get("queue_pending"):
            return JSONResponse(status_code=503, content={"status": "busy", "error": "queue_busy"})
        return {"status": "ok", "model": config.SERVED_VARIANT, "queue_depth": config.MAX_QUEUE_DEPTH}

    @app.post("/generate", status_code=202)
    async def generate(req: GenerateRequest):
        job_id = f"gen-{uuid.uuid4()}"
        async with admission_lock:
            try:
                q = await asyncio.to_thread(client.queue)
            except ComfyUnavailable:
                return JSONResponse(status_code=503, content={"error": "comfyui_unavailable", "detail": "ComfyUI not reachable"})
            if q.get("queue_running") or q.get("queue_pending"):
                return JSONResponse(status_code=429, content={"error": "queue_busy", "detail": "ComfyUI queue not empty"})
            if not worker.try_reserve(job_id, staged_name=""):
                return JSONResponse(status_code=429, content={"error": "queue_busy", "detail": "worker slot busy"})
            if req.image_path is not None:
                try:
                    staged = await asyncio.to_thread(
                        stage_still, config.STILLS_ROOT, req.image_path, req.image_sha256,
                        config.COMFYUI_INPUT_DIR, job_id,
                    )
                except StillsError as e:
                    worker.release(job_id)
                    return JSONResponse(status_code=400, content={"error": e.code, "detail": e.detail})
                worker.get(job_id).staged_name = staged
        worker.start(job_id, req)
        return JSONResponse(status_code=202, content={"job_id": job_id})

    @app.get("/status/{job_id}")
    async def status(job_id: str):
        rec = worker.get(job_id)
        if rec is None:
            return JSONResponse(status_code=404, content={"error": "not_found", "detail": job_id})
        body = {"status": rec.status, "progress": rec.progress}
        if rec.error:
            body["error"] = rec.error
        return body

    @app.get("/output/{job_id}")
    async def output(job_id: str):
        rec = worker.get(job_id)
        if rec is None or rec.status != "completed" or rec.output_path is None or not rec.output_path.exists():
            return JSONResponse(status_code=404, content={"error": "not_found", "detail": job_id})
        return FileResponse(rec.output_path, media_type="video/mp4", filename=f"{job_id}.mp4")

    @app.post("/cancel/{job_id}")
    async def cancel(job_id: str):
        if not worker.cancel(job_id):
            return JSONResponse(status_code=404, content={"error": "not_found", "detail": job_id})
        return {"status": "failed", "error": "cancelled"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("wan_service.main:app", host=config.HOST, port=config.PORT, workers=1)