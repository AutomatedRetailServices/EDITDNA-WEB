import os
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import redis
from rq import Queue, Job

# ----------------- Redis / RQ setup -----------------

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = os.getenv("QUEUE_NAME", "default")

# ⏱️ tiempo máximo que puede durar el job en el worker (en segundos)
# antes lanzaba JobTimeoutException a los 180s; ahora lo hacemos configurable
JOB_TIMEOUT = int(os.getenv("JOB_TIMEOUT", "1800"))   # 30 minutos
RESULT_TTL = int(os.getenv("RESULT_TTL", "86400"))    # 1 día
FAILURE_TTL = int(os.getenv("FAILURE_TTL", "86400"))  # 1 día

redis_conn = redis.from_url(REDIS_URL)
queue = Queue(QUEUE_NAME, connection=redis_conn)

app = FastAPI(title="EditDNA Web API")

# CORS abierto para Postman / frontends (ajusta si quieres más estricto)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------- Models -----------------


class RenderRequest(BaseModel):
    session_id: str
    files: List[str]
    # modo de compositor: "human" | "clean" | "blooper"
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


# ----------------- Helpers -----------------


def _normalize_mode(mode: Optional[str]) -> str:
    m = (mode or "human").lower()
    if m not in ("human", "clean", "blooper"):
        m = "human"
    return m


def _build_job_response(job: Optional[Job]) -> JobStatusResponse:
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    status = job.get_status() or "unknown"

    if job.is_failed:
        return JobStatusResponse(
            ok=False,
            job_id=job.id,
            status=status,
            result=None,
            error=str(job.exc_info),
        )

    return JobStatusResponse(
        ok=True,
        job_id=job.id,
        status=status,
        result=job.result,
        error=None,
    )


# ----------------- Routes -----------------


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/render", response_model=RenderEnqueueResponse)
def render(req: RenderRequest):
    """
    Encola un render en RQ llamando a tasks.job_render(session_id, files, file_urls, mode).
    """
    mode = _normalize_mode(req.mode)

    job: Job = queue.enqueue(
        "tasks.job_render",  # se resuelve en el worker (RunPod)
        kwargs={
            "session_id": req.session_id,
            "files": req.files,
            "file_urls": None,
            "mode": mode,
        },
        job_timeout=JOB_TIMEOUT,
        result_ttl=RESULT_TTL,
        failure_ttl=FAILURE_TTL,
    )

    return RenderEnqueueResponse(
        ok=True,
        job_id=job.id,
        status=job.get_status() or "queued",
    )


# Endpoint original (singular)
@app.get("/job/{job_id}", response_model=JobStatusResponse)
def job_status(job_id: str):
    job = queue.fetch_job(job_id)
    return _build_job_response(job)


# Alias plural para que /jobs/{id} también funcione
@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
def job_status_alias(job_id: str):
    job = queue.fetch_job(job_id)
    return _build_job_response(job)
