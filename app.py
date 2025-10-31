import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from redis import Redis
from rq import Queue
from rq.job import Job

REDIS_URL = os.environ["REDIS_URL"]
r = Redis.from_url(REDIS_URL)
q = Queue("default", connection=r)

class RenderReq(BaseModel):
    session_id: str | None = None
    files: list[str]
    portrait: bool = True
    max_duration: int = 220
    output_prefix: str = "editdna/outputs/"

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
    payload = req.model_dump()
    job = q.enqueue(
        "editdna.tasks.job_render",   # <<< THIS STRING IS CRITICAL
        payload,
        job_timeout=60 * 40
    )
    return {"job_id": job.id, "status": "queued"}

@app.get("/jobs/{job_id}")
def jobs(job_id: str):
    job = Job.fetch(job_id, connection=r)
    out = {
        "id": job.id,
        "status": job.get_status(),
        "enqueued_at": job.enqueued_at,
        "started_at": job.started_at,
        "ended_at": job.ended_at,
        "result": job.result if job.is_finished else None,
        "meta": job.meta or {},
    }
    if job.is_failed:
        out["error"] = str(job.exc_info or "")
    return out
