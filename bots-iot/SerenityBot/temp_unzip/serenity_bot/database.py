# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime

DB_NAME = "actividad.db"


def normalizar_tarea(tarea):
    equivalencias = {
        "Clean": "Cleaner",
        "Cleaner": "Cleaner",
        "Traduccion": "Traductor",
        "Traductor": "Traductor",
        "Edicion": "Editor",
        "Editor": "Editor",
    }
    return equivalencias.get(str(tarea or "").strip(), str(tarea or "").strip())


def get_conn():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def setup_db():
    """Inicializa la base de datos con las tablas necesarias."""
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        """CREATE TABLE IF NOT EXISTS usuarios
           (user_id INTEGER PRIMARY KEY,
            last_msg TEXT,
            ausencia_hasta TEXT)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS config
           (clave TEXT PRIMARY KEY,
            valor INTEGER)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS series_catalog
           (nombre TEXT PRIMARY KEY,
            canal_id TEXT,
            link_drive TEXT,
            folder_id TEXT,
            categoria TEXT,
            idioma TEXT,
            fecha_agregada TEXT,
            admin_id TEXT,
            admin_nombre TEXT)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS asignaciones
           (id INTEGER PRIMARY KEY AUTOINCREMENT,
            proyecto TEXT NOT NULL,
            capitulo TEXT NOT NULL,
            tarea TEXT NOT NULL,
            usuario TEXT NOT NULL,
            estado TEXT NOT NULL,
            id_usuario TEXT NOT NULL)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS registros
           (id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            usuario TEXT NOT NULL,
            proyecto TEXT NOT NULL,
            capitulo TEXT NOT NULL,
            tarea TEXT NOT NULL,
            id_usuario TEXT NOT NULL)"""
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_asignaciones_lookup ON asignaciones (proyecto, capitulo, tarea, estado)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_asignaciones_user ON asignaciones (id_usuario, estado)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_registros_lookup ON registros (proyecto, capitulo, tarea, id_usuario)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_registros_fecha ON registros (fecha)")
    c.execute("INSERT OR IGNORE INTO config (clave, valor) VALUES ('ticket_count', 0)")

    conn.commit()
    conn.close()
    print("Base de datos inicializada correctamente")


def _rows_to_dicts(rows):
    return [dict(row) for row in rows]


def actualizar_actividad(user_id):
    conn = get_conn()
    c = conn.cursor()
    ahora = datetime.now().isoformat()
    c.execute(
        """
        INSERT INTO usuarios (user_id, last_msg) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET last_msg = excluded.last_msg
        """,
        (user_id, ahora),
    )
    conn.commit()
    conn.close()


def set_ausencia(user_id, fecha_iso):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO usuarios (user_id, ausencia_hasta) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET ausencia_hasta = excluded.ausencia_hasta
        """,
        (user_id, fecha_iso),
    )
    conn.commit()
    conn.close()


def obtener_ausencia(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT ausencia_hasta FROM usuarios WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else None


def borrar_ausencia(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE usuarios SET ausencia_hasta = NULL WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def obtener_siguiente_ticket():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT valor FROM config WHERE clave = 'ticket_count'")
    actual = c.fetchone()[0]
    nuevo = actual + 1
    c.execute("UPDATE config SET valor = ? WHERE clave = 'ticket_count'", (nuevo,))
    conn.commit()
    conn.close()
    return nuevo


def replace_series(series):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM series_catalog")
    for serie in series:
        c.execute(
            """
            INSERT INTO series_catalog
            (nombre, canal_id, link_drive, folder_id, categoria, idioma, fecha_agregada, admin_id, admin_nombre)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(serie.get("Nombre", "")).strip(),
                str(serie.get("Canal_ID", "")).strip(),
                str(serie.get("Link_Drive", "")).strip(),
                str(serie.get("Folder_ID", "")).strip(),
                str(serie.get("Categoria", "")).strip(),
                str(serie.get("Idioma", "")).strip(),
                str(serie.get("Fecha_Agregada", "")).strip(),
                str(serie.get("Admin_ID", "")).strip(),
                str(serie.get("Admin_Nombre", "")).strip(),
            ),
        )
    conn.commit()
    conn.close()


def upsert_series(serie):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO series_catalog
        (nombre, canal_id, link_drive, folder_id, categoria, idioma, fecha_agregada, admin_id, admin_nombre)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(nombre) DO UPDATE SET
            canal_id=excluded.canal_id,
            link_drive=excluded.link_drive,
            folder_id=excluded.folder_id,
            categoria=excluded.categoria,
            idioma=excluded.idioma,
            fecha_agregada=excluded.fecha_agregada,
            admin_id=excluded.admin_id,
            admin_nombre=excluded.admin_nombre
        """,
        (
            str(serie.get("Nombre", "")).strip(),
            str(serie.get("Canal_ID", "")).strip(),
            str(serie.get("Link_Drive", "")).strip(),
            str(serie.get("Folder_ID", "")).strip(),
            str(serie.get("Categoria", "")).strip(),
            str(serie.get("Idioma", "")).strip(),
            str(serie.get("Fecha_Agregada", "")).strip(),
            str(serie.get("Admin_ID", "")).strip(),
            str(serie.get("Admin_Nombre", "")).strip(),
        ),
    )
    conn.commit()
    conn.close()


def list_series():
    conn = get_conn()
    c = conn.cursor()
    rows = c.execute(
        """
        SELECT nombre AS Nombre, canal_id AS Canal_ID, link_drive AS Link_Drive, folder_id AS Folder_ID,
               categoria AS Categoria, idioma AS Idioma, fecha_agregada AS Fecha_Agregada,
               admin_id AS Admin_ID, admin_nombre AS Admin_Nombre
        FROM series_catalog
        ORDER BY nombre
        """
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def get_serie_by_name(nombre):
    conn = get_conn()
    c = conn.cursor()
    row = c.execute(
        """
        SELECT nombre AS Nombre, canal_id AS Canal_ID, link_drive AS Link_Drive, folder_id AS Folder_ID,
               categoria AS Categoria, idioma AS Idioma, fecha_agregada AS Fecha_Agregada,
               admin_id AS Admin_ID, admin_nombre AS Admin_Nombre
        FROM series_catalog WHERE lower(nombre)=lower(?)
        """,
        (str(nombre).strip(),),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_serie_by_channel(canal_id):
    conn = get_conn()
    c = conn.cursor()
    row = c.execute(
        """
        SELECT nombre AS Nombre, canal_id AS Canal_ID, link_drive AS Link_Drive, folder_id AS Folder_ID,
               categoria AS Categoria, idioma AS Idioma, fecha_agregada AS Fecha_Agregada,
               admin_id AS Admin_ID, admin_nombre AS Admin_Nombre
        FROM series_catalog WHERE canal_id=?
        """,
        (str(canal_id),),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def replace_asignaciones(rows):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM asignaciones")
    for fila in rows:
        c.execute(
            """
            INSERT INTO asignaciones (proyecto, capitulo, tarea, usuario, estado, id_usuario)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(fila.get("Proyecto", "")).strip(),
                str(fila.get("Capítulo", fila.get("Capitulo", ""))).strip(),
                normalizar_tarea(fila.get("Tarea", "")),
                str(fila.get("Usuario", "")).strip(),
                str(fila.get("Estado", "")).strip(),
                str(fila.get("ID_Usuario", "")).strip(),
            ),
        )
    conn.commit()
    conn.close()


def list_asignaciones():
    conn = get_conn()
    c = conn.cursor()
    rows = c.execute(
        """
        SELECT id, proyecto AS Proyecto, capitulo AS "Capítulo", tarea AS Tarea,
               usuario AS Usuario, estado AS Estado, id_usuario AS ID_Usuario
        FROM asignaciones ORDER BY id
        """
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def add_asignacion(proyecto, capitulo, tarea, usuario, estado, id_usuario):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO asignaciones (proyecto, capitulo, tarea, usuario, estado, id_usuario)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (str(proyecto).strip(), str(capitulo).strip(), normalizar_tarea(tarea), str(usuario).strip(), str(estado).strip(), str(id_usuario).strip()),
    )
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_asignacion_estado(asignacion_id, estado):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE asignaciones SET estado = ? WHERE id = ?", (str(estado).strip(), int(asignacion_id)))
    conn.commit()
    conn.close()


def delete_asignacion(asignacion_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM asignaciones WHERE id = ?", (int(asignacion_id),))
    conn.commit()
    conn.close()


def replace_registros(rows):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM registros")
    for fila in rows:
        c.execute(
            """
            INSERT INTO registros (fecha, usuario, proyecto, capitulo, tarea, id_usuario)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(fila.get("Fecha", "")).strip(),
                str(fila.get("Usuario", "")).strip(),
                str(fila.get("Proyecto", "")).strip(),
                str(fila.get("Capítulo", fila.get("Capitulo", ""))).strip(),
                str(fila.get("Tarea", "")).strip(),
                str(fila.get("ID_Usuario", "")).strip(),
            ),
        )
    conn.commit()
    conn.close()


def list_registros():
    conn = get_conn()
    c = conn.cursor()
    rows = c.execute(
        """
        SELECT id, fecha AS Fecha, usuario AS Usuario, proyecto AS Proyecto,
               capitulo AS "Capítulo", tarea AS Tarea, id_usuario AS ID_Usuario
        FROM registros ORDER BY id
        """
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def add_registro(fecha, usuario, proyecto, capitulo, tarea, id_usuario):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO registros (fecha, usuario, proyecto, capitulo, tarea, id_usuario)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (str(fecha).strip(), str(usuario).strip(), str(proyecto).strip(), str(capitulo).strip(), str(tarea).strip(), str(id_usuario).strip()),
    )
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return new_id
