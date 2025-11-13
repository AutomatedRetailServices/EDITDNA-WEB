import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import redis
from rq import Queue

REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL not set")

redis_conn = redis.from_url(REDIS_URL)
q = Queue("default", connection=redis_conn)

app = FastAPI(title="EditDNA API")


class RenderRequest(BaseModel):
    session_id: str
    files: List[str]
    s3_prefix: Optional[str] = "editdna/outputs/"


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/render")
def render(req: RenderRequest):
    """
    Enqueue a job for the GPU worker (RunPod).
    The worker must have the EditDNA-worker repo with tasks.job_render.
    """
    if not req.files:
        raise HTTPException(status_code=400, detail="files list cannot be empty")

    job = q.enqueue(
        "tasks.job_render",  # string path; resolved on the WORKER side
        req.session_id,
        req.files,
        s3_prefix=req.s3_prefix,
    )

    return {
        "job_id": job.get_id(),
        "status": job.get_status(),
    }


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    from rq.job import Job
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except Exception:
        raise HTTPException(status_code=404, detail="job not found")

    resp = {
        "id": job.id,
        "status": job.get_status(),
    }
    if job.is_finished:
        resp["result"] = job.result
    if job.is_failed:
        resp["error"] = str(job.exc_info)
    return resp
