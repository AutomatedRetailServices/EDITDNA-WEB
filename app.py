# app.py — FastAPI + RQ enqueue + job status

import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from redis import Redis
from rq import Queue
from rq.job import Job

# ENV
REDIS_URL = os.environ["REDIS_URL"]

# Redis / RQ wiring
r = Redis.from_url(REDIS_URL)
q = Queue("default", connection=r)

# incoming request body for /render
class RenderReq(BaseModel):
    session_id: str | None = None
    files: list[str]                # list of public / presigned video URLs
    portrait: bool = True
    max_duration: int = 220
    audio: str = "original"         # not deeply used yet
    output_prefix: str = "editdna/outputs"

app = FastAPI()

@app.get("/health")
def health():
    try:
        pong = r.ping()
        return {"ok": True, "redis": bool(pong)}
    except Exception as e:
        raise HTTPException(500, f"redis error: {e}")

@app.post("/render")
def render(req: RenderReq):
    # push a job onto Redis so the worker can pick it up
    payload = req.model_dump()

    # IMPORTANT: enqueue USING "tasks.job_render"
    # DO NOT CHANGE THIS STRING unless you rename tasks.py
    job = q.enqueue("tasks.job_render", payload, job_timeout=60 * 40)

    return {"job_id": job.id, "status": "queued"}

@app.get("/jobs/{job_id}")
def jobs(job_id: str):
    job = Job.fetch(job_id, connection=r)

    out = {
        "id": job.id,
        "status": job.get_status(),      # queued / started / finished / failed
        "enqueued_at": job.enqueued_at,
        "started_at": job.started_at,
        "ended_at": job.ended_at,
        "result": job.result if job.is_finished else None,
        "meta": job.meta or {},
    }

    if job.is_failed:
        out["error"] = str(job.exc_info or "")

    return out
