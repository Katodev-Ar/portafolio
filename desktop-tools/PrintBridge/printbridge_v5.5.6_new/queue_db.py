"""
queue_db.py — PrintBridge v5.5.0
Mejora 3 del Roadmap Técnico: cola de impresión persistida en SQLite.

PROBLEMA RESUELTO:
    La cola de trabajos vivía exclusivamente en memoria. Un reinicio del
    servidor (actualización, corte de luz, crash) descartaba silenciosamente
    todos los jobs pendientes sin avisar al usuario.

SOLUCIÓN:
    SQLite con WAL mode para escrituras atómicas y lecturas concurrentes.
    La misma base de datos (queue.db) almacena tanto los jobs activos
    como el historial, eliminando el archivo history.json.

ESQUEMA:
    jobs (
        id           TEXT PRIMARY KEY,
        filename     TEXT NOT NULL,
        filepath     TEXT NOT NULL,
        device_name  TEXT,
        ip           TEXT,
        copies       INTEGER DEFAULT 1,
        options      TEXT,           -- JSON serializado
        status       TEXT DEFAULT 'waiting',
        error        TEXT,
        created_at   TEXT,
        finished_at  TEXT
    )

INTEGRACIÓN:
    QueueDB es usado por QueueManager como backend de persistencia.
    La API pública de QueueManager (add_job, cancel_job, etc.) no cambia.

RECUPERACIÓN AL ARRANQUE:
    QueueDB.recover_waiting_jobs() retorna todos los jobs en estado
    'waiting' ordenados por created_at — QueueManager los recarga en
    la deque al iniciar.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Optional

log = logging.getLogger("PrintBridge.QueueDB")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    filename    TEXT NOT NULL,
    filepath    TEXT NOT NULL,
    device_name TEXT DEFAULT '',
    ip          TEXT DEFAULT '',
    copies      INTEGER DEFAULT 1,
    options     TEXT DEFAULT '{}',
    status      TEXT DEFAULT 'waiting',
    error       TEXT,
    created_at  TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_status     ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_created_at ON jobs(created_at);
"""


class QueueDB:
    """
    Capa de acceso a datos para la cola de impresión en SQLite.

    Thread-safe: todas las operaciones usan un RLock interno y
    verifican/reabren la conexión si el thread cambió (sqlite3 no comparte
    conexiones entre threads por defecto).

    La conexión usa WAL journal mode para mejor concurrencia de lectura
    y escrituras atómicas.
    """

    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._lock = threading.RLock()
        self._local = threading.local()   # conexión por thread
        self._init_schema()

    # ── Conexión ─────────────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        """Retorna (o crea) la conexión SQLite del thread actual."""
        if not getattr(self._local, "conn", None):
            conn = sqlite3.connect(str(self._path), timeout=10, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self) -> None:
        """Crear tablas si no existen."""
        with self._lock:
            self._conn().executescript(_SCHEMA)
            self._conn().commit()
        log.debug(f"QueueDB inicializada en {self._path}")

    # ── Escrituras ────────────────────────────────────────────────────────────

    def insert_job(self, job) -> None:
        """Persiste un nuevo job en estado 'waiting'."""
        with self._lock:
            self._conn().execute(
                """INSERT OR REPLACE INTO jobs
                   (id, filename, filepath, device_name, ip, copies,
                    options, status, error, created_at, finished_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job.id,
                    job.filename,
                    job.filepath,
                    job.device_name,
                    job.ip,
                    job.copies,
                    json.dumps(job.options, ensure_ascii=False),
                    job.status,
                    job.error,
                    job.created_at,
                    job.finished_at,
                ),
            )
            self._conn().commit()

    def update_status(
        self,
        job_id: str,
        status: str,
        error: Optional[str] = None,
        finished_at: Optional[str] = None,
    ) -> None:
        """Actualiza el estado de un job existente."""
        with self._lock:
            self._conn().execute(
                "UPDATE jobs SET status=?, error=?, finished_at=? WHERE id=?",
                (status, error, finished_at, job_id),
            )
            self._conn().commit()

    def delete_job(self, job_id: str) -> None:
        """Elimina un job de la base de datos (jobs cancelados muy antiguos)."""
        with self._lock:
            self._conn().execute("DELETE FROM jobs WHERE id=?", (job_id,))
            self._conn().commit()

    # ── Lecturas ──────────────────────────────────────────────────────────────

    def recover_waiting_jobs(self) -> list[dict]:
        """
        Retorna todos los jobs en estado 'waiting' ordenados por created_at.
        Llamar al arrancar QueueManager para recargar la cola tras reinicio.
        """
        with self._lock:
            rows = self._conn().execute(
                "SELECT * FROM jobs WHERE status='waiting' ORDER BY created_at ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_history(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """
        Retorna el historial paginado de jobs completados/fallidos/cancelados.
        Reemplaza history.json — elimina el archivo JSON de historial.
        """
        with self._lock:
            rows = self._conn().execute(
                """SELECT * FROM jobs
                   WHERE status IN ('done', 'error', 'cancelled')
                   ORDER BY COALESCE(finished_at, created_at) DESC
                   LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["options"] = json.loads(d.get("options") or "{}")
            except Exception:
                d["options"] = {}
            result.append(d)
        return result

    def get_active_jobs(self) -> list[dict]:
        """Retorna jobs en estado 'waiting' o 'printing'."""
        with self._lock:
            rows = self._conn().execute(
                "SELECT * FROM jobs WHERE status IN ('waiting','printing') ORDER BY created_at ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def count_waiting(self) -> int:
        """Cuenta jobs en espera (para verificar límite de cola)."""
        with self._lock:
            return self._conn().execute(
                "SELECT COUNT(*) FROM jobs WHERE status='waiting'"
            ).fetchone()[0]

    def prune_history(self, max_entries: int = 100) -> int:
        """
        Elimina entradas antiguas del historial para no crecer indefinidamente.
        Conserva las `max_entries` más recientes. Retorna el número eliminado.
        """
        with self._lock:
            count_before = self._conn().execute(
                "SELECT COUNT(*) FROM jobs WHERE status IN ('done','error','cancelled')"
            ).fetchone()[0]
            if count_before <= max_entries:
                return 0
            self._conn().execute(
                """DELETE FROM jobs WHERE id IN (
                       SELECT id FROM jobs
                       WHERE status IN ('done','error','cancelled')
                       ORDER BY COALESCE(finished_at, created_at) DESC
                       LIMIT -1 OFFSET ?
                   )""",
                (max_entries,),
            )
            self._conn().commit()
            pruned = count_before - max_entries
            log.debug(f"QueueDB: {pruned} entradas antiguas eliminadas del historial")
            return pruned

    def close(self) -> None:
        """Cierra la conexión del thread actual."""
        if getattr(self._local, "conn", None):
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None
