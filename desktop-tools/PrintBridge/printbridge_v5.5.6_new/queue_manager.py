"""
queue_manager.py — PrintBridge v5.5.0
Mejoras 1 y 3 del Roadmap Técnico:
  - Mejora 1: lógica de impresión en proceso separado (ProcessPoolExecutor)
  - Mejora 3: cola y historial persistidos en SQLite (QueueDB)
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import multiprocessing
import os
import signal
import threading
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import load_config, load_history, save_history  # load/save_history: solo migración one-shot
from queue_db import QueueDB

log = logging.getLogger("PrintBridge.QueueManager")

_BASE_DIR = Path(__file__).parent
_QUEUE_DB_PATH = _BASE_DIR / "data" / "queue.db"

# Forzar método "spawn" para consistencia Windows/Linux con ProcessPoolExecutor.
# En Windows es el default; en Linux el default es "fork" que causa problemas
# con threads y locks heredados del proceso padre.
try:
    multiprocessing.set_start_method("spawn", force=False)
except RuntimeError:
    pass   # Ya fue llamado antes (frecuente en tests)


class PrintJob:
    def __init__(self, filename, filepath, device_name, ip, copies=1, options=None):
        self.id          = uuid.uuid4().hex
        self.filename    = filename
        self.filepath    = filepath
        self.device_name = device_name
        self.ip          = ip
        self.copies      = copies
        self.options     = options or {}
        self.status      = "waiting"   # waiting | printing | done | error | cancelled
        self.error       = None
        self.created_at  = datetime.now().isoformat()
        self.finished_at = None

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "filename":    self.filename,
            "device_name": self.device_name,
            "ip":          self.ip,
            "copies":      self.copies,
            "options":     self.options,
            "status":      self.status,
            "error":       self.error,
            "created_at":  self.created_at,
            "finished_at": self.finished_at,
        }


class QueueManager:
    """
    Gestiona la cola de trabajos de impresión.

    Mejora 1: cada job se ejecuta en un proceso hijo aislado via
    ProcessPoolExecutor(max_workers=1). Si el driver de la impresora
    se cuelga, el proceso hijo muere sin afectar al servidor principal.
    """

    def __init__(self, printer_module):
        self.printer         = printer_module
        self.queue: deque    = deque()
        self.current_job: Optional[PrintJob] = None
        self.lock            = threading.Lock()
        self._history_lock   = threading.Lock()
        self._history_cache: list[dict] = []

        # Mejora 3: backend de persistencia en SQLite
        self._db = QueueDB(_QUEUE_DB_PATH)

        # Migración: si existe history.json, importarlo a SQLite y eliminarlo
        self._migrate_history_json()

        # Mejora 3: recuperar jobs 'waiting' que sobrevivieron el reinicio
        self._recover_waiting_jobs()

        # Mejora 1: ProcessPoolExecutor con max_workers=1 (impresión secuencial)
        self._executor = concurrent.futures.ProcessPoolExecutor(
            max_workers=1,
            mp_context=multiprocessing.get_context("spawn"),
        )
        self._executor_lock = threading.Lock()

        self.worker = threading.Thread(
            target=self._worker_loop, daemon=True, name="QueueWorker"
        )
        self.worker.start()

    def _migrate_history_json(self) -> None:
        """
        Mejora 3: importa history.json a SQLite si existe y luego lo elimina.
        Migración one-shot — solo se ejecuta si el archivo existe.
        """
        try:
            from config import HISTORY_FILE
            if not HISTORY_FILE.exists():
                return
            history = load_history()
            if history:
                log.info(f"Migrando {len(history)} entradas de history.json a SQLite…")
                for entry in reversed(history):   # más antiguo primero
                    job = PrintJob(
                        filename    = entry.get("filename", ""),
                        filepath    = "",
                        device_name = entry.get("device_name", ""),
                        ip          = entry.get("ip", ""),
                        copies      = entry.get("copies", 1),
                        options     = entry.get("options", {}),
                    )
                    job.id          = entry.get("id", job.id)
                    job.status      = entry.get("status", "done")
                    job.error       = entry.get("error")
                    job.created_at  = entry.get("created_at", job.created_at)
                    job.finished_at = entry.get("finished_at")
                    self._db.insert_job(job)
                log.info("Migración de historial completada.")
            HISTORY_FILE.unlink(missing_ok=True)
            tmp = HISTORY_FILE.with_suffix(".tmp")
            tmp.unlink(missing_ok=True)
        except Exception as e:
            log.warning(f"Error en migración de history.json: {e}")

    def _recover_waiting_jobs(self) -> None:
        """
        Mejora 3: recarga jobs 'waiting' de SQLite al arrancar.
        Los jobs que sobrevivieron un reinicio del servidor se vuelven a encolar.
        """
        waiting = self._db.recover_waiting_jobs()
        if not waiting:
            return
        log.info(f"Recuperando {len(waiting)} job(s) pendientes de reinicio anterior…")
        for row in waiting:
            job = PrintJob(
                filename    = row["filename"],
                filepath    = row["filepath"],
                device_name = row.get("device_name", ""),
                ip          = row.get("ip", ""),
                copies      = row.get("copies", 1),
                options     = json.loads(row.get("options") or "{}"),
            )
            job.id         = row["id"]
            job.status     = "waiting"
            job.created_at = row.get("created_at", job.created_at)
            self.queue.append(job)
        log.info(f"{len(waiting)} job(s) recuperados y encolados.")

    # ── API pública ─────────────────────────────────────────────────────────

    def add_job(self, job: PrintJob) -> Optional[str]:
        config = load_config()
        with self.lock:
            if len(self.queue) >= config.get("max_queue_size", 20):
                return None
            self.queue.append(job)
        # Mejora 3: persistir inmediatamente — sobrevivirá un reinicio
        try:
            self._db.insert_job(job)
        except Exception as e:
            log.warning(f"Error persistiendo job {job.id[:8]} en SQLite: {e}")
        return job.id

    def cancel_job(self, job_id: str) -> bool:
        with self.lock:
            for job in list(self.queue):
                if job.id == job_id and job.status == "waiting":
                    job.status = "cancelled"
                    self.queue.remove(job)
                    self._add_to_history(job)
                    return True
        return False

    def get_queue(self) -> list[dict]:
        with self.lock:
            result = []
            if self.current_job:
                result.append(self.current_job.to_dict())
            result += [j.to_dict() for j in self.queue]
            return result

    def get_history(self) -> list[dict]:
        # Mejora 3: leer desde SQLite con paginación nativa
        config = load_config()
        max_h  = config.get("max_history", 100)
        return self._db.get_history(limit=max_h)

    def shutdown(self, wait: bool = True) -> None:
        """Apagado limpio del executor. Llamar desde app._quit()."""
        log.info("QueueManager: cerrando executor…")
        with self._executor_lock:
            self._executor.shutdown(wait=wait, cancel_futures=not wait)
        self._db.close()
        log.info("QueueManager: executor cerrado.")

    # ── Worker loop ─────────────────────────────────────────────────────────

    def _worker_loop(self) -> None:
        import time

        while True:
            try:
                self._process_next_job()
            except concurrent.futures.process.BrokenProcessPool as e:
                log.error(f"ProcessPool roto: {e}. Recreando executor…")
                self._recreate_executor()
                with self.lock:
                    if self.current_job:
                        self.current_job.status = "error"
                        self.current_job.error  = "Proceso de impresión terminado inesperadamente."
                        self._finalize_job(self.current_job)
                        self.current_job = None
                time.sleep(1)
            except BaseException as e:
                log.critical(f"Worker crash inesperado: {e}", exc_info=True)
                with self.lock:
                    if self.current_job:
                        Path(self.current_job.filepath).unlink(missing_ok=True)
                        self.current_job = None
                if isinstance(e, (SystemExit, KeyboardInterrupt)):
                    log.critical("Worker recibió señal de cierre — notificando proceso principal")
                    os.kill(os.getpid(), signal.SIGTERM)
                    return
                time.sleep(1)

    def _process_next_job(self) -> None:
        """
        Mejora 1: toma el siguiente job y lo ejecuta en un proceso hijo
        con timeout configurable por extensión de archivo.
        """
        import time
        from print_worker import get_timeout_for_ext, run_print_job

        job: Optional[PrintJob] = None
        with self.lock:
            if self.queue:
                job = self.queue.popleft()
                self.current_job = job
                job.status = "printing"
        
        if not job:
            time.sleep(0.5)
            return

        # Mejora 3: persistir estado 'printing' para que sea visible si el proceso crashea
        try:
            self._db.update_status(job.id, "printing")
        except Exception:
            pass

        ext          = Path(job.filepath).suffix.lower().lstrip(".")
        timeout_secs = get_timeout_for_ext(ext)
        future       = None

        try:
            with self._executor_lock:
                future = self._executor.submit(
                    run_print_job,
                    job.filepath,
                    job.copies,
                    job.options,
                )
            future.result(timeout=timeout_secs)
            job.status = "done"
            log.info(f"Job {job.id[:8]} completado: {job.filename}")

        except concurrent.futures.TimeoutError:
            job.status = "error"
            job.error  = (
                f"Tiempo de impresión excedido ({timeout_secs}s). "
                "El driver puede estar colgado. Verifica la impresora."
            )
            log.error(f"Job {job.id[:8]} timeout ({timeout_secs}s): {job.filename}")
            if future:
                future.cancel()
            # Recrear executor — el proceso hijo puede seguir corriendo
            self._recreate_executor()

        except concurrent.futures.process.BrokenProcessPool:
            raise   # manejar en _worker_loop

        except Exception as e:
            job.status = "error"
            job.error  = str(e)
            log.error(f"Job {job.id[:8]} error: {e}", exc_info=True)

        finally:
            self._finalize_job(job)
            with self.lock:
                self.current_job = None

    def _finalize_job(self, job: PrintJob) -> None:
        """Marca el job como terminado, persiste en historial y limpia el archivo."""
        job.finished_at = datetime.now().isoformat()
        self._add_to_history(job)
        try:
            Path(job.filepath).unlink(missing_ok=True)
        except Exception:
            pass

    def _recreate_executor(self) -> None:
        """Recrea el ProcessPoolExecutor tras un timeout o fallo irrecuperable."""
        log.warning("Recreando ProcessPoolExecutor…")
        with self._executor_lock:
            try:
                self._executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
            self._executor = concurrent.futures.ProcessPoolExecutor(
                max_workers=1,
                mp_context=multiprocessing.get_context("spawn"),
            )

    # ── Historial ───────────────────────────────────────────────────────────

    def _add_to_history(self, job: PrintJob) -> None:
        """Mejora 3: persistir en SQLite en lugar de JSON en memoria."""
        try:
            self._db.update_status(
                job.id,
                status     = job.status,
                error      = job.error,
                finished_at= job.finished_at,
            )
            # Podar entradas antiguas para no crecer indefinidamente
            config = load_config()
            self._db.prune_history(config.get("max_history", 100))
        except Exception as e:
            log.warning(f"Error persistiendo historial en SQLite: {e}")
