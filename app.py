# app.py — FastAPI web (Render) to enqueue EditDNA jobs to RQ
import os
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field
from typing import List, Optional
import redis
from rq import Queue
from rq.job import Job

# ------------------- Redis setup -------------------
REDIS_URL = os.environ.get("REDIS_URL")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL not configured")

rconn = redis.from_url(REDIS_URL)
q = Queue("default", connection=rconn)

# ------------------- FastAPI app -------------------
app = FastAPI(title="EditDNA Web API")

# ---- Health + root endpoints for Render ----
@app.get("/")
def root():
    return {"ok": True, "service": "editdna-web", "status": "ready"}

@app.head("/")
def root_head():
    return Response(status_code=200)

@app.get("/health")
def health():
    try:
        rconn.ping()
        return {"ok": True, "service": "editdna-web"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ------------------- Job handling -------------------
class RenderPayload(BaseModel):
    session_id: Optional[str] = None
    mode: str = Field(default="funnel")
    files: List[str]
    portrait: Optional[bool] = True
    min_clip_seconds: Optional[float] = 1.5
    max_clip_seconds: Optional[float] = 4.0
    max_duration: Optional[float] = 60.0
    take_top_k: Optional[int] = None
    output_prefix: Optional[str] = "editdna/outputs"

@app.post("/render")
def render_job(payload: RenderPayload):
    try:
        job = q.enqueue("tasks.job_render", payload.model_dump(), job_timeout=60*30)
        return {"job_id": job.get_id(), "status": job.get_status(), "enqueued_at": job.enqueued_at}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/jobs/{job_id}")
def job_status(job_id: str):
    try:
        job = Job.fetch(job_id, connection=rconn)
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")
    out = {
        "job_id": job_id,
        "status": job.get_status(),
        "result": job.result if job.is_finished else None,
        "error": job.exc_info if job.is_failed else None,
        "enqueued_at": job.enqueued_at,
        "ended_at": job.ended_at,
    }
    return out
