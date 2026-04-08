# api/job_worker.py
# Worker async que consume job_queue y actualiza el estado de cada job.
# Se inicia en el startup del servidor y corre de forma continua.

import asyncio
import json
from datetime import datetime, timezone

from core.logger import logger


async def _run_job(job: dict) -> None:
    """Ejecuta el callable del job y actualiza su estado."""
    from api.app_state import jobs, proactive_engine

    job_id   = job["job_id"]
    job_type = job["type"]
    fn       = job["_fn"]
    args     = job.get("_args", ())
    kwargs   = job.get("_kwargs", {})

    jobs[job_id]["status"]   = "running"
    jobs[job_id]["progress"] = 10
    logger.info(f"[JobWorker] Iniciando job {job_id} ({job_type})")

    try:
        result = await asyncio.to_thread(fn, *args, **kwargs)
        jobs[job_id]["status"]      = "done"
        jobs[job_id]["progress"]    = 100
        jobs[job_id]["result"]      = result
        jobs[job_id]["finished_at"] = datetime.now(timezone.utc).isoformat()
        logger.info(f"[JobWorker] Job completado: {job_id}")
    except Exception as e:
        jobs[job_id]["status"]      = "error"
        jobs[job_id]["error"]       = str(e)
        jobs[job_id]["finished_at"] = datetime.now(timezone.utc).isoformat()
        logger.error(f"[JobWorker] Job fallido {job_id}: {e}")

    # Emitir evento por /ws/proactive
    try:
        event = json.dumps({
            "type":     "job_complete",
            "job_id":   job_id,
            "job_type": job_type,
            "status":   jobs[job_id]["status"],
        })
        await proactive_engine.broadcast(event)
    except Exception as e:
        logger.warning(f"[JobWorker] No se pudo emitir evento proactivo: {e}")


async def job_worker_loop() -> None:
    """Loop principal del worker. Se ejecuta de forma indefinida."""
    from api.app_state import job_queue

    logger.info("[JobWorker] Worker iniciado.")
    while True:
        try:
            job = await job_queue.get()
            asyncio.create_task(_run_job(job))
            job_queue.task_done()
        except asyncio.CancelledError:
            logger.info("[JobWorker] Worker cancelado.")
            break
        except Exception as e:
            logger.error(f"[JobWorker] Error inesperado en loop: {e}")
