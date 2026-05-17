# coordinador.py — Lógica de coordinación (Drive + hojas de responsables)
# Para MicroPython en ESP32-S3. Sin asyncio, sin gspread.

import gc
import random
from helpers import (
    extraer_numero_cap, caps_coinciden, series_coinciden,
    carpeta_drive_coincide, normalizar_categoria, normalizar_idioma,
    normalizar_tarea, tarea_a_columna_sheet, extraer_folder_id,
    ordenar_cap, fila_asignacion_coincide,
)
from discord_http import make_embed, send_message, send_embed
import gas_client as gas
from config import (
    CANAL_COORDINADORES_ID, CANAL_ASIGNACIONES_LOG,
    OWNER_SHEET_TITLES, SERIE_HEADERS, ITSUKI_ID,
    COORDINADOR_ROLE_ID,
)

CARPETAS_DRIVE = {
    "RAW": "1_RAW", "Clean": "2_CLRD",
    "Traduccion": "3_TRADUCCION", "Edicion": "4_TYPE", "Recorte": "5_RECORTES",
}


def _resolver_hoja(serie_info: dict) -> str:
    admin_id = str(serie_info.get('Admin_ID', '')).strip()
    admin_nombre = str(serie_info.get('Admin_Nombre', '')).strip()
    return OWNER_SHEET_TITLES.get(admin_id) or admin_nombre or "Sin responsable"


def _es_coord_o_admin(roles: list, es_admin: bool) -> bool:
    return es_admin or (COORDINADOR_ROLE_ID in [str(r) for r in roles])


# ──────────────────────────────────────────────
# Lectura de Drive via GAS
# ──────────────────────────────────────────────
def _obtener_caps_drive(folder_id: str) -> dict:
    """Retorna {etapa: set(cap_str)} usando GAS como proxy de Drive."""
    caps = {e: set() for e in CARPETAS_DRIVE}
    gc.collect()
    carpetas_principales = gas.listar_drive(folder_id, solo_carpetas=True)

    for etapa in CARPETAS_DRIVE:
        folder_etapa = None
        for c in carpetas_principales:
            if carpeta_drive_coincide(etapa, c.get('name', '')):
                folder_etapa = c.get('id')
                break
        if not folder_etapa:
            continue

        if etapa == "Traduccion":
            items = gas.listar_drive(folder_etapa, solo_carpetas=False)
        else:
            items = gas.listar_drive(folder_etapa, solo_carpetas=True)

        for it in items:
            num = extraer_numero_cap(it.get('name', ''))
            if num:
                caps[etapa].add(num)

    return caps


# ──────────────────────────────────────────────
# /agregar_serie (ADMIN)
# ──────────────────────────────────────────────
def cmd_agregar_serie(user_id, user_name, es_admin,
                      canal_id, canal_name, link_drive,
                      categoria_val, idioma_val, rtc=None):
    if not es_admin:
        return {"content": "❌ Solo administradores.", "ephemeral": True}

    folder_id = extraer_folder_id(link_drive)
    if not folder_id:
        return {"content": "❌ No pude extraer el ID del Drive.", "ephemeral": True}

    series = gas.get_series()
    for s in series:
        if str(s.get('Canal_ID', '')) == str(canal_id):
            return {"content": f"⚠️ **{canal_name}** ya está registrada.", "ephemeral": True}

    from helpers import fecha_hoy
    fecha = fecha_hoy(rtc) or "2026-01-01"

    nueva = {
        "Nombre": canal_name, "Canal_ID": str(canal_id),
        "Link_Drive": link_drive, "Folder_ID": folder_id,
        "Categoria": categoria_val, "Idioma": idioma_val,
        "Fecha_Agregada": fecha,
        "Admin_ID": str(user_id), "Admin_Nombre": user_name,
    }
    gas.upsert_serie(nueva)
    caps_n = _actualizar_serie_drive(canal_name, folder_id)

    embed = make_embed(
        title="✅ Serie Agregada", color=0xffb6c1,
        fields=[
            {"name": "📚 Serie", "value": f"<#{canal_id}>", "inline": True},
            {"name": "🏷️ Categoría", "value": categoria_val, "inline": True},
            {"name": "🌐 Idioma", "value": idioma_val, "inline": True},
            {"name": "👤 Admin", "value": f"<@{user_id}>", "inline": True},
            {"name": "📁 Caps en Drive", "value": str(caps_n), "inline": True},
        ],
        footer="Bloom Scans • Sistema de producción"
    )
    return {"embed": embed, "ephemeral": True}


# ──────────────────────────────────────────────
# /estado_serie
# ──────────────────────────────────────────────
def cmd_estado_serie(roles, es_admin, canal_id):
    if not _es_coord_o_admin(roles, es_admin):
        return {"content": "❌ Sin permisos.", "ephemeral": True}

    serie_info = gas.get_serie_by_channel(str(canal_id))
    if not serie_info:
        return {"content": "❌ Serie no registrada. Usa `/agregar_serie`.", "ephemeral": True}

    nombre = serie_info['Nombre']
    hoja = _resolver_hoja(serie_info)
    datos = gas.get_tabla_serie(nombre, hoja)

    activos = [f for f in datos if f.get('Subido_Web') != '✅' and f.get('Cap')]
    if not activos:
        return {"content": f"✅ Todos los caps de **{nombre}** están subidos."}

    def icono(fila, col):
        v = str(fila.get(col, '')).strip()
        return v if v in ("✅", "⏳", "❌") else "❌"

    lineas = []
    for fila in activos[:20]:
        cap = fila.get('Cap', '')
        lineas.append(
            f"Cap {cap:<6}│RAW {icono(fila,'RAW')}│Clean {icono(fila,'Clean')}"
            f"│Trad {icono(fila,'Traduccion')}│Edit {icono(fila,'Edicion')}"
            f"│Rec {icono(fila,'Recorte')}"
        )

    tabla = "```\n" + f"Serie: {nombre}\n" + "─"*55 + "\n"
    tabla += "\n".join(lineas) + "\n" + "─"*55 + "\n```"

    embed = make_embed(
        title=f"📋 Estado de Producción — {nombre}",
        description=tabla, color=0xffb6c1,
        footer=f"Mostrando {min(20, len(activos))} de {len(activos)} caps • Bloom Scans"
    )
    return {"embed": embed}


# ──────────────────────────────────────────────
# /actualizar_drive
# ──────────────────────────────────────────────
def cmd_actualizar_drive(roles, es_admin, canal_id):
    if not _es_coord_o_admin(roles, es_admin):
        return {"content": "❌ Sin permisos.", "ephemeral": True}

    serie_info = gas.get_serie_by_channel(str(canal_id))
    if not serie_info:
        return {"content": "❌ Serie no registrada.", "ephemeral": True}

    nombre = serie_info['Nombre']
    folder_id = serie_info.get('Folder_ID', '')
    caps = _actualizar_serie_drive(nombre, folder_id)

    embed = make_embed(
        title="🔄 Drive Actualizado",
        description=f"**{nombre}** actualizado.\n📁 Caps nuevos: **{caps}**",
        color=0x57F287,
        footer="Bloom Scans • Sistema de producción"
    )
    return {"embed": embed}


# ──────────────────────────────────────────────
# /asignarme
# ──────────────────────────────────────────────
def cmd_asignarme(user_id, user_name, guild_id, tarea_val, categoria_val, idioma_val="cualquiera"):
    gc.collect()
    series = gas.get_series()
    asig_datos = gas.get_asignaciones()

    candidatas = []
    for s in series:
        if normalizar_categoria(s.get('Categoria')) != categoria_val:
            continue
        if idioma_val and idioma_val != "cualquiera":
            if normalizar_idioma(s.get('Idioma')) not in [idioma_val, "Ambos"]:
                continue
        candidatas.append(s)

    if not candidatas:
        return {"content": f"❌ No hay series con categoría **{categoria_val}**.", "ephemeral": True}

    random.shuffle(candidatas)
    col_tarea = tarea_a_columna_sheet(tarea_val)
    cap_encontrado = None
    serie_encontrada = None

    for serie in candidatas:
        nombre = serie['Nombre']
        folder_id = serie.get('Folder_ID', '')
        hoja = _resolver_hoja(serie)
        datos = gas.get_tabla_serie(nombre, hoja)
        caps_drive = _obtener_caps_drive(folder_id) if folder_id else {}

        for fila in datos:
            cap = fila.get('Cap', '')
            if not cap or fila.get('Subido_Web') == '✅':
                continue
            if str(fila.get('RAW', '')) != '✅':
                continue

            cap_n = extraer_numero_cap(str(cap))
            if caps_drive and cap_n not in caps_drive.get("RAW", set()):
                continue
            if str(fila.get(col_tarea, '')) == '✅':
                continue
            if caps_drive and cap_n in caps_drive.get(tarea_val, set()):
                continue

            if tarea_val == "Edicion":
                if str(fila.get('Clean', '')) != '✅' or str(fila.get('Traduccion', '')) != '✅':
                    continue

            ya = any(
                fila_asignacion_coincide(a, nombre, cap_n, tarea=tarea_val, estado="En Proceso")
                for a in asig_datos
            )
            if not ya:
                cap_encontrado = cap
                serie_encontrada = serie
                break

        if cap_encontrado:
            break

    if not cap_encontrado:
        return {
            "content": f"😔 No hay caps para **{tarea_val}** en **{categoria_val}** ahora.",
            "ephemeral": True
        }

    cap_n = extraer_numero_cap(str(cap_encontrado))
    gas.add_asignacion(serie_encontrada['Nombre'], cap_encontrado,
                       tarea_val, user_name, "En Proceso", str(user_id))

    hoja = _resolver_hoja(serie_encontrada)
    gas.update_estado_tarea_serie(serie_encontrada['Nombre'], hoja, cap_encontrado, col_tarea, "⏳")

    canal_id = serie_encontrada.get('Canal_ID', '')
    if canal_id:
        embed_serie = make_embed(
            title="🌸 Nueva Autoasignación",
            description=f"<@{user_id}> se asignó a un nuevo capítulo.",
            color=0xffb6c1,
            fields=[
                {"name": "🛠️ Tarea", "value": tarea_val, "inline": True},
                {"name": "📌 Capítulo", "value": f"`{cap_encontrado}`", "inline": True},
            ],
            footer="Bloom Scans • Autoasignación"
        )
        send_message(canal_id, content=f"<@{user_id}>", embed=embed_serie)

    embed_log = make_embed(
        title="✨ Asignación Registrada", color=0x3498db,
        fields=[
            {"name": "Proyecto", "value": f"<#{canal_id}>" if canal_id else serie_encontrada['Nombre'], "inline": True},
            {"name": "Capítulo", "value": f"`{cap_encontrado}`", "inline": True},
            {"name": "Staff", "value": f"<@{user_id}>", "inline": True},
            {"name": "Tarea", "value": tarea_val, "inline": False},
        ],
        footer=f"ID:{user_id} | Cap:{cap_encontrado}"
    )
    send_embed(CANAL_ASIGNACIONES_LOG, embed_log)

    embed = make_embed(
        title="✅ ¡Te has asignado exitosamente!", color=0x57F287,
        fields=[
            {"name": "📚 Serie", "value": serie_encontrada['Nombre'], "inline": True},
            {"name": "📌 Capítulo", "value": f"`{cap_encontrado}`", "inline": True},
            {"name": "🛠️ Tarea", "value": tarea_val, "inline": True},
        ],
        footer="Cuando termines usa /terminado • Bloom Scans"
    )
    return {"embed": embed}


# ──────────────────────────────────────────────
# Tarea automática: revisión de Drive
# ──────────────────────────────────────────────
def tarea_revision_automatica():
    """Llamar desde main.py cada 12 horas."""
    gc.collect()
    series = gas.get_series()
    for serie in series:
        nombre = serie.get('Nombre', '')
        folder_id = serie.get('Folder_ID', '')
        canal_id = serie.get('Canal_ID', '')
        if not nombre or not folder_id:
            continue

        try:
            _, filas = _actualizar_serie_drive(nombre, folder_id, incluir_filas=True)
            hoja = _resolver_hoja(serie)
            datos = gas.get_tabla_serie(nombre, hoja)

            for fila in datos:
                cap = fila.get('Cap', '')
                if (str(fila.get('Recorte', '')) == '✅' and
                        str(fila.get('Subido_Web', '')) != '✅' and canal_id):
                    embed = make_embed(
                        title="✂️ ¡Capítulo listo para subir!",
                        description=f"**Cap {cap}** de **{nombre}** listo para la web.",
                        color=0x57F287,
                        footer="Bloom Scans • Sistema de producción"
                    )
                    admin_id = str(serie.get('Admin_ID', ''))
                    mention = f"<@{admin_id}>" if admin_id else ""
                    send_message(canal_id, content=mention, embed=embed)
        except Exception as e:
            print(f"[coordinador] Error en revisión {nombre}: {e}")


# ──────────────────────────────────────────────
# Tarea automática: reporte semanal
# ──────────────────────────────────────────────
def tarea_reporte_semanal(rtc=None):
    """Llamar desde main.py cada lunes."""
    import utime
    if utime.localtime()[6] != 0:  # 0 = lunes en MicroPython
        return
    gc.collect()
    series = gas.get_series()
    fields = []
    for serie in series[:10]:  # límite para no exceder embed
        nombre = serie.get('Nombre', '')
        if not nombre:
            continue
        hoja = _resolver_hoja(serie)
        datos = gas.get_tabla_serie(nombre, hoja)
        total = len(datos)
        listos = sum(1 for f in datos if f.get('Subido_Web') == '✅')
        en_proceso = total - listos
        atascados = sum(1 for f in datos
                        if f.get('RAW') == '✅' and f.get('Clean') != '✅'
                        and f.get('Subido_Web') != '✅')
        info = f"📁 En proceso: **{en_proceso}** | ✅ Subidos: **{listos}**"
        if atascados:
            info += f"\n⚠️ Atascados en Clean: **{atascados}**"
        fields.append({"name": f"📚 {nombre}", "value": info, "inline": False})

    if not fields:
        return
    embed = make_embed(
        title="📊 Reporte Semanal de Producción",
        description="Resumen de la semana",
        color=0xffb6c1, fields=fields,
        footer="Bloom Scans • Reporte automático semanal"
    )
    send_embed(CANAL_COORDINADORES_ID, embed)


# ──────────────────────────────────────────────
# Interno: actualizar serie desde Drive
# ──────────────────────────────────────────────
def _actualizar_serie_drive(nombre_serie: str, folder_id: str, incluir_filas=False):
    try:
        caps_drive = _obtener_caps_drive(folder_id)
        todos = set(caps_drive.get("RAW", set()))
        if not todos:
            return (0, []) if incluir_filas else 0

        serie_info = gas.get_serie_by_name(nombre_serie)
        hoja = _resolver_hoja(serie_info) if serie_info else "Sin responsable"
        datos = gas.get_tabla_serie(nombre_serie, hoja)

        existentes = {}
        for fila in datos:
            cap_n = extraer_numero_cap(str(fila.get('Cap', '')))
            if cap_n and cap_n not in existentes:
                existentes[cap_n] = fila

        caps_nuevos = sum(1 for c in todos if c not in existentes)
        filas_finales = []

        for cap in sorted(todos, key=ordenar_cap):
            actual = existentes.get(cap, {})
            filas_finales.append({
                "Cap": cap,
                "Idioma": actual.get("Idioma", ""),
                "RAW": "✅",
                "Clean": "✅" if cap in caps_drive.get("Clean", set()) or actual.get("Clean") == "✅"
                         else ("⏳" if actual.get("Clean") == "⏳" else "❌"),
                "Traduccion": "✅" if cap in caps_drive.get("Traduccion", set()) or actual.get("Traduccion") == "✅"
                              else ("⏳" if actual.get("Traduccion") == "⏳" else "❌"),
                "Edicion": "✅" if cap in caps_drive.get("Edicion", set()) or actual.get("Edicion") == "✅"
                           else ("⏳" if actual.get("Edicion") == "⏳" else "❌"),
                "Recorte": "✅" if cap in caps_drive.get("Recorte", set()) or actual.get("Recorte") == "✅"
                           else "❌",
                "Subido_Web": "✅" if actual.get("Subido_Web") == "✅" else "❌",
                "Fecha_RAW": actual.get("Fecha_RAW", ""),
            })

        gas.write_tabla_serie(nombre_serie, hoja, filas_finales)
        return (caps_nuevos, filas_finales) if incluir_filas else caps_nuevos

    except Exception as e:
        print(f"[coordinador] Error actualizando Drive {nombre_serie}: {e}")
        return (-1, []) if incluir_filas else -1
