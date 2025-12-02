import os
import uuid
from typing import Any, Dict, List

from redis import Redis
from rq import Queue

# Obtener la URL de Redis desde el entorno
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_conn = Redis.from_url(REDIS_URL)

# Tu worker está escuchando en la cola "default"
q = Queue("default", connection=redis_conn)


def job_render(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    API-facing helper.

    Lo llamas desde tu ruta web (app.py).
    Empuja un job a la cola que luego el worker llama a tasks.job_render
    (en el repo del worker).
    """

    # Nos aseguramos de tener un session_id
    session_id = data.get("session_id") or uuid.uuid4().hex[:8]

    # Normalizar mode: "human" | "clean" | "blooper"
    mode = (data.get("mode") or "human").lower()
    if mode not in ("human", "clean", "blooper"):
        mode = "human"

    payload: Dict[str, Any] = {
        "session_id": session_id,
        "files": data.get("files", []),
        "file_urls": data.get("file_urls", []),
        "portrait": bool(data.get("portrait", True)),
        "max_duration": float(data.get("max_duration", 120.0)),
        "s3_prefix": data.get("s3_prefix", "editdna/outputs"),
        "mode": mode,  # 👈👈 AQUÍ VA LA CLAVE
    }

    # Pasar funnel_counts si viene en el payload
    if "funnel_counts" in data:
        payload["funnel_counts"] = data["funnel_counts"]

    # Encolamos por NOMBRE: "tasks.job_render"
    # Esto es lo que el worker debe resolver (tasks.py en el worker repo)
    job = q.enqueue("tasks.job_render", payload)

    return {
        "ok": True,
        "job_id": job.id,
        "session_id": session_id,
    }
