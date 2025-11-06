# web/tasks.py — Web/API task adapter
# Purpose: take a request from the API, push a job into Redis/RQ,
# let the GPU worker (which has /workspace/tasks.py) do the real work.

import os
import uuid
from typing import Any, Dict, List

from redis import Redis
from rq import Queue

# Get Redis connection string from env, or default to local
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_conn = Redis.from_url(REDIS_URL)

# Your worker is listening on the "default" queue (we saw that in the logs)
q = Queue("default", connection=redis_conn)


def job_render(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    API-facing helper.
    You call THIS from your web route.
    It pushes a job that will call `tasks.job_render` INSIDE the worker container.
    """
    # make sure we have a session_id
    session_id = data.get("session_id") or f"session-{uuid.uuid4().hex[:8]}"

    payload: Dict[str, Any] = {
        "session_id": session_id,
        "files": data.get("files", []),
        "portrait": bool(data.get("portrait", True)),
        "max_duration": float(data.get("max_duration", 120.0)),
        # match what the worker expects
        "s3_prefix": data.get("s3_prefix", data.get("output_prefix", "editdna/outputs/")),
    }

    # optional: pass funnel counts through to worker
    if "funnel_counts" in data:
        payload["funnel_counts"] = data["funnel_counts"]

    # THIS is the key: we enqueue by string name, not by importing worker code
    job = q.enqueue("tasks.job_render", payload)

    return {
        "ok": True,
        "job_id": job.id,
        "session_id": session_id,
    }
