import os
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import redis
from rq import Queue

# -------------------------------------------------
# Redis / RQ setup
# -------------------------------------------------

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = os.getenv("QUEUE_NAME", "default")

# ⏱️ Timeouts configurables por entorno
JOB_TIMEOUT = int(os.getenv("JOB_TIMEOUT", "1800"))       # 30 min
RESULT_TTL = int(os.getenv("RESULT_TTL", "86400"))        # 24 h
FAILURE_TTL = int(os.getenv("FAILURE_TTL", "86400"))      # 24 h

redis_conn = redis.from_url(REDIS_URL)
queue = Queue(QUEUE_NAME, connection=redis_conn)

app = FastAPI(title="EditDNA Web API")


# -------------------------------------------------
# Pydantic models
# -------------------------------------------------

class RenderRequest(BaseModel):
    session_id: str
    files: List[str]
    # modo opcional: "human" | "clean" | "blooper"
    mode: Optional[str] = "human"


class RenderEnqueueResponse(BaseModel):
    ok: bool
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    ok: bool
    job_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# -------------------------------------------------
# Rutas
# -------------------------------------------------

@app.get("/health")
def health():
    return {"ok": True}


@app.post("/render", response_model=RenderEnqueueResponse)
def render(req: RenderRequest):
    """
    Encola un render en RQ llamando a tasks.job_render(session_id, files, file_urls, mode)

    El timeout REAL del job se controla con job_timeout=JOB_TIMEOUT (30 min por defecto),
    mientras que result_ttl y failure_ttl controlan cuánto tiempo se conserva el resultado
    o el error en Redis.
    """
    # normalizamos el modo
    mode = (req.mode or "human").lower()
    if mode not in ("human", "clean", "blooper"):
        mode = "human"

    job = queue.enqueue(
        "tasks.job_render",           # función que corre en EditDNA-worker
        kwargs={
            "session_id": req.session_id,
            "files": req.files,
            "file_urls": None,
            "mode": mode,
        },
        job_timeout=JOB_TIMEOUT,      # ⏱️ 30 minutos por defecto
        result_ttl=RESULT_TTL,        # resultado vive 24h
        failure_ttl=FAILURE_TTL,      # errores viven 24h
    )

    return RenderEnqueueResponse(
        ok=True,
        job_id=job.id,
        status=job.get_status() or "queued",
    )


@app.get("/job/{job_id}", response_model=JobStatusResponse)
def job_status(job_id: str):
    """
    Devuelve el estado del job:
    - queued / started / finished / failed
    - result (cuando finished)
    - error (cuando failed)
    """
    job = queue.fetch_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.is_failed:
        return JobStatusResponse(
            ok=False,
            job_id=job.id,
            status=job.get_status() or "failed",
            result=None,
            error=str(job.exc_info),
        )

    return JobStatusResponse(
        ok=True,
        job_id=job.id,
        status=job.get_status() or "unknown",
        result=job.result,
        error=None,
    )
