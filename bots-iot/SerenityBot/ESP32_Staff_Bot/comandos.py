# comandos.py — Lógica de comandos del staff (sin discord.py)
# Cada función recibe los datos del interaction ya parseados
# y retorna un dict {"content": ..., "embed": ..., "ephemeral": bool}
# que main.py entrega a discord_http.respond_interaction()

import gc
from helpers import (
    normalizar_tarea, tarea_a_columna_sheet,
    fila_asignacion_coincide, fila_registro_coincide,
    caps_coinciden, series_coinciden,
    extraer_numero_cap, timestamp_now_iso, fecha_hoy,
    filtrar_registros_por_mes, calcular_ranking, nombre_mes,
    parsear_capitulos,
)
from discord_http import make_embed, send_message, send_embed
import gas_client as gas
from config import (
    ADMIN_CHANNEL_ID, AVISOS_CHANNEL_ID, CANAL_ASIGNACIONES_LOG,
    CANAL_COORDINADORES_ID, CANAL_CREDITOS_APODO,
    CANAL_JUSTIFICACION_ID, BIENVENIDA_CHANNEL_ID,
    REGLAS_CHANNEL_ID, STAFF_ROLE_ID, COORDINADOR_ROLE_ID,
    CANALES_TERMINADOS, OWNER_SHEET_TITLES, ITSUKI_ID,
)


def _es_admin_o_coordinador(roles: list, es_admin: bool) -> bool:
    return es_admin or (COORDINADOR_ROLE_ID in [str(r) for r in roles])


def _resolver_titulo_responsable(admin_id: str, admin_nombre: str) -> str:
    return OWNER_SHEET_TITLES.get(str(admin_id or "").strip()) or str(admin_nombre or "").strip() or "Sin responsable"


# ──────────────────────────────────────────────
# /apodo
# ──────────────────────────────────────────────
def cmd_apodo(user_id, channel_id, nombre: str):
    if str(channel_id) != str(CANAL_CREDITOS_APODO):
        return {"content": f"❌ Usa este comando en <#{CANAL_CREDITOS_APODO}>.", "ephemeral": True}
    gas.set_apodo(str(user_id), nombre)
    embed = make_embed(
        title="✨ Nombre Artístico Configurado",
        description=f"Tu apodo ha sido guardado.",
        color=0xffb6c1,
        fields=[
            {"name": "🎨 Apodo", "value": f"**{nombre}**", "inline": False},
            {"name": "📋 Nota", "value": "Solo se usa en `/creditos`.", "inline": False},
        ],
        footer="Bloom Scans • Identidad artística."
    )
    return {"embed": embed}


# ──────────────────────────────────────────────
# /asignar (ADMIN/COORD)
# ──────────────────────────────────────────────
def _extraer_drive_de_fijados(channel_id: str) -> str:
    """Busca un link de Google Drive en los mensajes fijados del canal."""
    from discord_http import get_pinned_messages
    import re
    msgs = get_pinned_messages(str(channel_id))
    for m in msgs:
        content = m.get("content", "")
        # Buscar links de Drive en el contenido
        match = re.search(r'https?://drive\.google\.com/drive/folders/([a-zA-Z0-9_-]+)', content)
        if match:
            return match.group(1)
        # También revisar embeds adjuntos
        for emb in m.get("embeds", []):
            for field_name in ("url", "description", "title"):
                val = emb.get(field_name, "")
                match = re.search(r'https?://drive\.google\.com/drive/folders/([a-zA-Z0-9_-]+)', str(val))
                if match:
                    return match.group(1)
    return ""


def _asegurar_rol_canal(guild_id: str, channel_id: str, serie_name: str) -> str:
    """Busca un rol con el nombre de la serie. Si no existe, lo crea. Retorna role_id."""
    from discord_http import get_guild_roles, create_guild_role
    roles = get_guild_roles(guild_id)
    nombre_lower = serie_name.strip().lower()
    for r in roles:
        if str(r.get("name", "")).strip().lower() == nombre_lower:
            return str(r.get("id", ""))
    # No existe, crearlo
    nuevo = create_guild_role(guild_id, serie_name, color=0xff7eb3, mentionable=True)
    return str(nuevo.get("id", "")) if nuevo else ""


def cmd_asignar(interaction_user_id, roles, es_admin,
                target_user_id, target_user_name, tarea_val,
                serie_name, serie_channel_id, capitulo, guild_id):
    if not _es_admin_o_coordinador(roles, es_admin):
        return {"content": "❌ Sin permisos.", "ephemeral": True}

    gc.collect()
    capitulos = parsear_capitulos(str(capitulo))
    datos = gas.get_asignaciones()

    # Verificar duplicados para todos los caps
    duplicados = []
    for cap in capitulos:
        for fila in datos:
            if fila_asignacion_coincide(fila, serie_name, cap, tarea=tarea_val):
                duplicados.append(cap)
                break
    if duplicados:
        return {
            "content": f"❌ **Tarea duplicada** en caps: `{', '.join(duplicados)}`\nUsa `/cancelar_asignacion` primero.",
            "ephemeral": True
        }

    # ── Paso 1: Buscar Drive (de BD o mensajes fijados) ──
    gc.collect()
    serie_info = gas.get_serie_by_channel(str(serie_channel_id))
    folder_id = serie_info.get("Folder_ID", "") if serie_info else ""
    if not folder_id:
        folder_id = _extraer_drive_de_fijados(serie_channel_id)
        if folder_id and serie_info:
            serie_info["Folder_ID"] = folder_id
            serie_info["Link_Drive"] = f"https://drive.google.com/drive/folders/{folder_id}"
            gas.upsert_serie(serie_info)
        elif folder_id and not serie_info:
            gas.upsert_serie({
                "Nombre": serie_name,
                "Canal_ID": str(serie_channel_id),
                "Link_Drive": f"https://drive.google.com/drive/folders/{folder_id}",
                "Folder_ID": folder_id,
                "Admin_ID": str(interaction_user_id),
                "Admin_Nombre": "Auto",
            })

    # ── Paso 2: Buscar/crear rol y asignarlo ──
    gc.collect()
    from discord_http import add_role
    role_id = _asegurar_rol_canal(str(guild_id), str(serie_channel_id), serie_name)
    if role_id:
        add_role(str(guild_id), str(target_user_id), role_id)

    # ── Paso 3: Registrar todos los capítulos (Batch) ──
    gc.collect()
    caps_str = ", ".join(capitulos)
    rows_to_add = []
    for cap in capitulos:
        rows_to_add.append({
            "Proyecto": serie_name,
            "Capitulo": cap,
            "Tarea": tarea_val,
            "Usuario": target_user_name,
            "Estado": "En Proceso",
            "ID_Usuario": str(target_user_id)
        })
    
    gas.add_asignaciones_batch(rows_to_add)
    _actualizar_estado_tarea_batch(serie_name, capitulos, tarea_val, "⏳")

    # Notificar en el canal de la serie (1 solo mensaje para todos los caps)
    cap_display = f"**{caps_str}**" if len(capitulos) > 1 else f"**{capitulos[0]}**"
    embed_serie = make_embed(
        title="🌸 Nueva Tarea Asignada",
        description=f"<@{target_user_id}> Se te ha asignado {'un capítulo' if len(capitulos) == 1 else f'{len(capitulos)} capítulos'}.",
        color=0xffb6c1,
        fields=[
            {"name": "🛠️ Tarea", "value": f"**{tarea_val}**", "inline": True},
            {"name": "📌 Capítulo(s)", "value": cap_display, "inline": True},
        ],
        footer="Bloom Scans • Calidad y Coherencia"
    )
    send_message(str(serie_channel_id), content=f"<@{target_user_id}>", embed=embed_serie)

    # Log en canal de asignaciones
    extras = []
    if folder_id:
        extras.append({"name": "📁 Drive", "value": "✅ Acceso otorgado", "inline": True})
    if role_id:
        extras.append({"name": "🏷️ Rol", "value": f"✅ <@&{role_id}>", "inline": True})

    embed_log = make_embed(
        title="✨ Nueva Asignación Registrada", 
        color=0xff7eb3,
        description=f"Se ha delegado {'una tarea' if len(capitulos) == 1 else f'{len(capitulos)} tareas'} a **{target_user_name}**.",
        fields=[
            {"name": "📘 Proyecto", "value": f"<#{serie_channel_id}>", "inline": True},
            {"name": "📌 Capítulo(s)", "value": f"`{caps_str}`", "inline": True},
            {"name": "👤 Staff", "value": f"<@{target_user_id}>", "inline": True},
            {"name": "🛠️ Tarea", "value": f"**{tarea_val}**", "inline": False},
        ] + extras,
        footer=f"Bloom Scans • ID:{target_user_id} | Caps:{caps_str}"
    )
    send_embed(CANAL_ASIGNACIONES_LOG, embed_log)

    return {"content": f"✅ **{target_user_name}** asignado a **{serie_name}** Cap(s) `{caps_str}` ({tarea_val})."}


# ──────────────────────────────────────────────
# /terminado
# ──────────────────────────────────────────────
def cmd_terminado(user_id, user_name, channel_id, rol_val, serie_name, serie_channel_id, capitulo, rtc=None):
    if str(channel_id) not in [str(c) for c in CANALES_TERMINADOS]:
        return {"content": "❌ Solo en canales de 'Terminados'.", "ephemeral": True}

    gc.collect()
    capitulos = parsear_capitulos(str(capitulo))
    asig_datos = gas.get_asignaciones()
    reg_datos = gas.get_registros()
    fecha_hoy_str = timestamp_now_iso(rtc) or "2026-01-01 00:00:00"

    exitos = []
    errores = []

    for cap in capitulos:
        # Buscar asignación
        asignacion = None
        for fila in asig_datos:
            if fila_asignacion_coincide(fila, serie_name, cap, tarea=rol_val, usuario_id=user_id):
                asignacion = fila
                break

        if not asignacion:
            errores.append(f"Cap {cap}: no asignado")
            continue
        if asignacion.get('Estado') == "Terminado":
            errores.append(f"Cap {cap}: ya terminado")
            continue

        # Validar si ya estaba registrado
        ya_registrado = any(
            fila_registro_coincide(r, serie_name, cap, tarea=rol_val, usuario_id=user_id)
            for r in reg_datos
        )
        if not ya_registrado:
            # Añadimos al batch (gas.add_registro no tiene batch, podríamos añadir uno
            # pero por lo menos optimizamos la actualización de la hoja de la serie)
            # Para esto usaremos add_registro, que no duele tanto si es uno, pero
            # updateEstadoTareaSerieBatch si salva MUCHO tiempo.
            gas.add_registro(fecha_hoy_str, user_name, serie_name, cap, rol_val, str(user_id))

        row_id = asignacion.get('_rowNum')
        if row_id:
            gas.update_asignacion_estado(row_id, "Terminado")

        exitos.append(cap)

    if exitos:
        _actualizar_estado_tarea_batch(serie_name, exitos, rol_val, "✅")

    if not exitos:
        return {"content": f"❌ No se pudo completar ningún capítulo.\n" + "\n".join(errores), "ephemeral": True}

    caps_str = ", ".join(exitos)

    # Notificar coordinadores (1 mensaje)
    embed_coord = make_embed(
        title="📢 Tareas terminadas",
        description=f"<@{user_id}> completó **{len(exitos)}** capítulo(s).",
        color=0x3498db,
        fields=[
            {"name": "📘 Serie", "value": f"<#{serie_channel_id}>", "inline": True},
            {"name": "📌 Capítulo(s)", "value": f"`{caps_str}`", "inline": True},
            {"name": "🛠️ Rol", "value": rol_val, "inline": True},
        ],
        footer="Bloom Scans • Revisión administrativa"
    )
    send_embed(CANAL_COORDINADORES_ID, embed_coord)

    # Respuesta al usuario
    desc = f"¡Excelente trabajo <@{user_id}>! 🎉"
    if errores:
        desc += f"\n\n⚠️ Algunos caps tuvieron problemas:\n" + "\n".join(f"> {e}" for e in errores)

    embed = make_embed(
        title=f"✅ {'Trabajo' if len(exitos) == 1 else f'{len(exitos)} Trabajos'} Terminado{'s' if len(exitos) > 1 else ''} y Registrado{'s' if len(exitos) > 1 else ''}",
        description=desc,
        color=0x57F287,
        fields=[
            {"name": "📘 Proyecto", "value": f"<#{serie_channel_id}>", "inline": True},
            {"name": "📌 Capítulo(s)", "value": f"`{caps_str}`", "inline": True},
            {"name": "🛠️ Tarea Cumplida", "value": f"**{rol_val}**", "inline": False},
        ],
        footer="Bloom Scans • Usa /trabajos para ver tu acumulado."
    )
    return {"embed": embed}


# ──────────────────────────────────────────────
# /ver_asignacion
# ──────────────────────────────────────────────
def cmd_ver_asignacion(serie_name, serie_channel_id, capitulo):
    datos = gas.get_asignaciones()
    staff = {"Traductor": "⚪ No asignado", "Editor": "⚪ No asignado", "Cleaner": "⚪ No asignado"}
    for fila in datos:
        if fila_asignacion_coincide(fila, serie_name, capitulo):
            estado = "✅ Terminado" if fila.get('Estado') == "Terminado" else "⏳ En Proceso"
            t = normalizar_tarea(fila.get('Tarea'))
            if t in staff:
                staff[t] = f"👤 **{fila.get('Usuario')}** — {estado}"

    fields = [{"name": f"✨ {t}", "value": v, "inline": False} for t, v in staff.items()]
    embed = make_embed(
        title=f"🌸 Estado Actual | {serie_name}",
        description=f"Revisando las asignaciones para el **Capítulo `{capitulo}`**.",
        color=0xff7eb3,
        fields=fields,
        footer="Bloom Scans • Consulta de Asignaciones"
    )
    return {"embed": embed}


# ──────────────────────────────────────────────
# /creditos
# ──────────────────────────────────────────────
def cmd_creditos(serie_name, capitulo):
    asig = gas.get_asignaciones()
    reg = gas.get_registros()
    staff = {"Traductor": "⚪ Pendiente", "Editor": "⚪ Pendiente", "Cleaner": "⚪ Pendiente"}

    for fila in asig:
        if fila_asignacion_coincide(fila, serie_name, capitulo):
            uid = fila.get('ID_Usuario')
            apodo = gas.get_apodo(str(uid)) if uid else ""
            nombre = apodo or fila.get('Usuario', 'Desconocido')
            t = normalizar_tarea(fila.get('Tarea', ''))
            if t in staff:
                if fila.get('Estado') == "Terminado":
                    staff[t] = f"✅ {nombre}"
                else:
                    staff[t] = f"⏳ {nombre} — En Proceso"

    for fila in reg:
        if fila_registro_coincide(fila, serie_name, capitulo):
            uid = fila.get('ID_Usuario')
            apodo = gas.get_apodo(str(uid)) if uid else ""
            nombre = apodo or fila.get('Usuario', 'Desconocido')
            t = fila.get('Tarea', '')
            if t in staff:
                staff[t] = f"✅ {nombre}"

    hay = any("Pendiente" not in v for v in staff.values())
    fields = [{"name": k, "value": v, "inline": True} for k, v in staff.items()]
    embed = make_embed(
        title=f"🌸 Créditos: {serie_name}",
        description=f"**Capítulo:** {capitulo}" + ("" if hay else "\n⚠️ Sin asignaciones."),
        color=0xffb6c1 if hay else 0xe67e22,
        fields=fields,
        footer="Información de Asignaciones • Bloom Scans"
    )
    return {"embed": embed}


# ──────────────────────────────────────────────
# /trabajos
# ──────────────────────────────────────────────
def cmd_trabajos(user_id, mes_num=None):
    import utime
    mes = mes_num or utime.localtime()[1]
    datos = gas.get_registros()
    conteo = 0
    for fila in datos:
        f = str(fila.get('Fecha', ''))
        if not f:
            continue
        try:
            m_f = int(f[5:7])
            if str(fila.get('ID_Usuario', '')) == str(user_id) and m_f == mes:
                conteo += 1
        except Exception:
            pass
    embed = make_embed(
        title="📊 Tu Rendimiento", color=0xffb6c1,
        fields=[
            {"name": "Mes", "value": nombre_mes(mes), "inline": True},
            {"name": "Total Trabajos", "value": f"**{conteo}** capítulos", "inline": True},
        ],
        footer="Bloom Scans - ¡Sigue así!"
    )
    return {"embed": embed, "ephemeral": True}


# ──────────────────────────────────────────────
# /ausente
# ──────────────────────────────────────────────
def cmd_ausente(user_id, user_name, channel_id, es_admin, dias: int, motivo: str, rtc=None):
    if str(channel_id) != str(CANAL_JUSTIFICACION_ID) and not es_admin:
        return {"content": f"❌ Solo en <#{CANAL_JUSTIFICACION_ID}>.", "ephemeral": True}

    import utime
    t = utime.localtime()
    # Sumar días aproximadamente (86400 s/día)
    epoch_fin = utime.time() + dias * 86400
    t_fin = utime.localtime(epoch_fin)
    fecha_fin_iso = "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}".format(*t_fin[:6])

    gas.set_ausencia(str(user_id), fecha_fin_iso)

    embed = make_embed(
        title="💤 Registro de Ausencia", color=0x3498db,
        fields=[
            {"name": "Staff", "value": f"<@{user_id}>", "inline": True},
            {"name": "Regresa", "value": fecha_fin_iso[:10], "inline": True},
            {"name": "Motivo", "value": motivo, "inline": False},
        ]
    )
    send_message(ADMIN_CHANNEL_ID, content=f"<@&{STAFF_ROLE_ID}>", embed=embed)
    return {"content": "✅ Ausencia registrada. ¡Cuídate!"}


# ──────────────────────────────────────────────
# /cancelar_ausencia
# ──────────────────────────────────────────────
def cmd_cancelar_ausencia(user_id, channel_id, es_admin):
    if str(channel_id) != str(CANAL_JUSTIFICACION_ID) and not es_admin:
        return {"content": f"❌ Úsalo en <#{CANAL_JUSTIFICACION_ID}>.", "ephemeral": True}
    usuario = gas.get_usuario(str(user_id))
    if not usuario.get('ausencia_hasta'):
        return {"content": "⚠️ No tienes ausencia registrada.", "ephemeral": True}
    gas.clear_ausencia(str(user_id))
    embed = make_embed(title="🔄 Regreso Anticipado",
                       description=f"<@{user_id}> canceló su ausencia.", color=0x57F287)
    send_embed(ADMIN_CHANNEL_ID, embed)
    return {"content": "✅ Ausencia cancelada. ¡Bienvenido de vuelta!"}


# ──────────────────────────────────────────────
# /abandonar
# ──────────────────────────────────────────────
def _borrar_mensaje_asignacion(serie_name: str, target_user_id: str, capitulo: str):
    from discord_http import get_channel_messages, delete_message
    series = gas.get_series()
    canal_id = None
    for s in series:
        if series_coinciden(s.get('Nombre', ''), serie_name):
            canal_id = s.get('Canal_ID')
            break
    if not canal_id:
        return

    msgs = get_channel_messages(canal_id, limit=50)
    for m in msgs:
        if m.get('author', {}).get('bot'):
            content = m.get('content', '')
            embeds = m.get('embeds', [])
            if embeds:
                title = str(embeds[0].get('title', ''))
                if "Asignada" in title or "Asignación" in title or "Autoasignación" in title:
                    # Verifica si menciona al usuario
                    if f"<@{target_user_id}>" in content or f"<@{target_user_id}>" in str(embeds[0]):
                        # Verifica el capítulo
                        for field in embeds[0].get('fields', []):
                            if "Capítulo" in field.get('name', '') and str(capitulo) in field.get('value', ''):
                                delete_message(canal_id, m.get('id'))
                                return

def cmd_abandonar(user_id, serie_name, capitulo, tarea_val):
    datos = gas.get_asignaciones()
    fila_enc = None
    for fila in datos:
        if fila_asignacion_coincide(fila, serie_name, capitulo, tarea=tarea_val,
                                    usuario_id=user_id, incluir_terminadas=False):
            fila_enc = fila
            break
    if not fila_enc:
        return {"content": "❌ No encontré esa tarea asignada a ti.", "ephemeral": True}
    row_id = fila_enc.get('_rowNum')
    if row_id:
        gas.delete_asignacion(row_id)
    _actualizar_estado_tarea(serie_name, capitulo, tarea_val, "❌")
    
    # Intentar borrar el mensaje original
    _borrar_mensaje_asignacion(serie_name, str(user_id), capitulo)
    
    return {"content": "✅ Has abandonado la tarea.", "ephemeral": True}


# ──────────────────────────────────────────────
# /cancelar_asignacion (ADMIN/COORD)
# ──────────────────────────────────────────────
def cmd_cancelar_asignacion(roles, es_admin, serie_name, capitulo_str, tarea_val):
    if not _es_admin_o_coordinador(roles, es_admin):
        return {"content": "❌ Sin permisos.", "ephemeral": True}
        
    capitulos = parsear_capitulos(capitulo_str)
    if not capitulos:
        return {"content": "❌ Formato de capítulo inválido.", "ephemeral": True}
        
    datos = gas.get_asignaciones()
    exitos = []
    errores = []
    usuarios_notificados = set()

    for cap in capitulos:
        fila_enc = None
        for fila in datos:
            if fila_asignacion_coincide(fila, serie_name, cap, tarea=tarea_val):
                fila_enc = fila
                break
                
        if not fila_enc:
            errores.append(f"Cap {cap}: no asignado")
            continue
            
        row_id = fila_enc.get('_rowNum')
        if row_id:
            gas.delete_asignacion(row_id)
            
        target_uid = fila_enc.get('ID_Usuario')
        if target_uid:
            _borrar_mensaje_asignacion(serie_name, str(target_uid), cap)
            usuarios_notificados.add(target_uid)
            
        exitos.append(cap)

    if exitos:
        _actualizar_estado_tarea_batch(serie_name, exitos, tarea_val, "❌")

    desc = f"✅ Asignación de **{tarea_val}** cancelada para {len(exitos)} cap(s)."
    if errores:
        desc += f"\n\n⚠️ Errores:\n" + "\n".join(f"> {e}" for e in errores)

    return {"content": desc, "ephemeral": True}



# ──────────────────────────────────────────────
# /posibles_ganadores
# ──────────────────────────────────────────────
def cmd_posibles_ganadores(mes_num=None, anio_num=None):
    import utime
    mes = mes_num or utime.localtime()[1]
    anio = anio_num or utime.localtime()[0]
    registros = gas.get_registros()
    filtrados = filtrar_registros_por_mes(registros, mes, anio)
    ranking = calcular_ranking(filtrados)

    calificados = [r for r in ranking if r["count"] >= 25]
    no_calif = [r for r in ranking if r["count"] < 25]

    fields = []
    if calificados:
        medallas = ["🥇", "🥈", "🥉"]
        txt = ""
        for i, r in enumerate(calificados):
            txt += f"{medallas[i] if i < 3 else '🎖️'} **{r['nombre']}** — `{r['count']}` caps\n"
        fields.append({"name": "✅ CALIFICAN (25+ caps)", "value": txt, "inline": False})
    else:
        fields.append({"name": "⚠️ NADIE CALIFICA AÚN", "value": "Mínimo 25 caps.", "inline": False})

    if no_calif:
        txt2 = ""
        for r in no_calif[:8]:
            txt2 += f"• **{r['nombre']}** — `{r['count']}` (faltan {25 - r['count']})\n"
        fields.append({"name": "📌 CERCA DE CALIFICAR", "value": txt2, "inline": False})

    embed = make_embed(
        title="🏆 POSIBLES GANADORES DEL MES 🏆",
        description=f"**Mes:** {nombre_mes(mes)} {anio}",
        color=0xffd700,
        fields=fields,
        footer="Bloom Scans • Motivación y Competencia Sana"
    )
    return {"embed": embed, "ephemeral": True}


# ──────────────────────────────────────────────
# /refrescar_asignaciones (ADMIN/COORD)
# ──────────────────────────────────────────────
def cmd_refrescar_asignaciones(roles, es_admin):
    if not _es_admin_o_coordinador(roles, es_admin):
        return {"content": "❌ Sin permisos.", "ephemeral": True}
    # Solo confirma; el GAS es la fuente de verdad, no hay SQLite local
    asig = gas.get_asignaciones()
    embed = make_embed(
        title="🔄 Asignaciones verificadas", color=0x57F287,
        fields=[{"name": "Filas en GAS", "value": str(len(asig)), "inline": True}],
        footer="Bloom Scans • El GAS es la fuente de verdad."
    )
    return {"embed": embed, "ephemeral": True}


# ──────────────────────────────────────────────
# /registrar_correo
# ──────────────────────────────────────────────
def cmd_registrar_correo(user_id, user_name, correo_val):
    if "@" not in correo_val or "." not in correo_val:
        return {"content": "❌ Por favor ingresa un correo electrónico válido.", "ephemeral": True}
    res = gas.set_correo(str(user_id), correo_val)
    if res and res.get("ok"):
        embed = make_embed(
            title="📧 Correo Registrado",
            description=f"¡Gracias {user_name}! Tu correo **{correo_val}** ha sido vinculado a tu cuenta.",
            color=0x57F287,
            fields=[{"name": "🔒 Acceso a Drive", "value": "Se te dará acceso automáticamente a las carpetas de Drive cuando te asignes o te asignen a un proyecto.", "inline": False}],
            footer="Bloom Scans • Infraestructura de Accesos"
        )
        return {"embed": embed, "ephemeral": True}
    return {"content": "❌ Hubo un error al guardar tu correo.", "ephemeral": True}

# ──────────────────────────────────────────────
# /quitar_staff (ADMIN)
# ──────────────────────────────────────────────
def cmd_quitar_staff(roles, es_admin, target_user_id):
    if not _es_admin_o_coordinador(roles, es_admin):
        return {"content": "❌ Sin permisos.", "ephemeral": True}
    
    res = gas.quitar_staff(str(target_user_id))
    if res and res.get("ok"):
        embed = make_embed(
            title="🚫 Revocación de Accesos",
            description=f"Se han eliminado todas las asignaciones y se ha revocado el acceso a los archivos de Drive para el usuario <@{target_user_id}>.",
            color=0xE74C3C,
            footer="Bloom Scans • Administración de Seguridad"
        )
        send_embed(ADMIN_CHANNEL_ID, embed)
        return {"content": f"✅ Accesos revocados para <@{target_user_id}>.", "ephemeral": True}
    return {"content": "❌ Error al procesar la revocación.", "ephemeral": True}

# ──────────────────────────────────────────────
# /helps
# ──────────────────────────────────────────────
def cmd_helps():
    embed = make_embed(
        title="🌸 Bloom Scans - Guía de Comandos", color=0xffb6c1,
        description="Comandos disponibles para el staff:",
        fields=[
            {"name": "✅ /terminado", "value": "Registra capítulos finalizados.", "inline": False},
            {"name": "🏃 /abandonar", "value": "Libera un capítulo.", "inline": False},
            {"name": "📊 /trabajos", "value": "Consulta tu acumulado mensual.", "inline": False},
            {"name": "💤 /ausente", "value": "Pide vacaciones (máx 30 días).", "inline": False},
            {"name": "🔄 /cancelar_ausencia", "value": "Informa tu regreso.", "inline": False},
            {"name": "🎨 /apodo", "value": "Elige tu nombre artístico.", "inline": False},
            {"name": "🙋 /asignarme", "value": "Asígnate a un cap disponible.", "inline": False},
            {"name": "🏆 /posibles_ganadores", "value": "Ranking actual del mes.", "inline": False},
        ],
        footer="Bloom Scans • Dudas → contacta a un admin."
    )
    return {"embed": embed}


# ──────────────────────────────────────────────
# Helper interno: actualizar estado en hoja
# ──────────────────────────────────────────────
def _actualizar_estado_tarea(serie_name: str, capitulo: str, tarea: str, valor: str):
    series = gas.get_series()
    serie_info = None
    for s in series:
        if series_coinciden(s.get('Nombre', ''), serie_name):
            serie_info = s
            break
    if not serie_info:
        return
    from config import OWNER_SHEET_TITLES
    admin_id = str(serie_info.get('Admin_ID', '')).strip()
    admin_nombre = str(serie_info.get('Admin_Nombre', '')).strip()
    hoja = OWNER_SHEET_TITLES.get(admin_id) or admin_nombre or "Sin responsable"
    columna = tarea_a_columna_sheet(tarea)
    gas.update_estado_tarea_serie(serie_name, hoja, capitulo, columna, valor)

def _actualizar_estado_tarea_batch(serie_name: str, capitulos: list, tarea: str, valor: str):
    series = gas.get_series()
    serie_info = None
    for s in series:
        if series_coinciden(s.get('Nombre', ''), serie_name):
            serie_info = s
            break
    if not serie_info:
        return
    from config import OWNER_SHEET_TITLES
    admin_id = str(serie_info.get('Admin_ID', '')).strip()
    admin_nombre = str(serie_info.get('Admin_Nombre', '')).strip()
    hoja = OWNER_SHEET_TITLES.get(admin_id) or admin_nombre or "Sin responsable"
    columna = tarea_a_columna_sheet(tarea)
    gas.update_estado_tarea_serie_batch(serie_name, hoja, capitulos, columna, valor)


# ──────────────────────────────────────────────
# /mis_asignaciones — ver tus capítulos asignados
# ──────────────────────────────────────────────
def cmd_mis_asignaciones(user_id, user_name, avatar_url=""):
    gc.collect()
    datos = gas.get_asignaciones()
    mis = [f for f in datos if str(f.get("ID_Usuario", "")).strip() == str(user_id).strip()
           and str(f.get("Estado", "")).strip() != "Terminado"]

    if not mis:
        embed = make_embed(
            title="📋 Mis Asignaciones",
            description="No tienes capítulos asignados actualmente. ¡Buen trabajo! 🎉",
            color=0x2ecc71,
            footer="Bloom Scans • Este mensaje se eliminará en 5 min."
        )
        if avatar_url:
            embed["thumbnail"] = {"url": avatar_url}
        return {"embed": embed, "ephemeral": True, "auto_delete": 300}

    # Agrupar por proyecto
    proyectos = {}
    for f in mis:
        proy = f.get("Proyecto", "Sin proyecto")
        if proy not in proyectos:
            proyectos[proy] = []
        cap = f.get("Capitulo", f.get("Capítulo", "?"))
        tarea = f.get("Tarea", "?")
        estado = str(f.get("Estado", "")).strip()
        icono = "⌛" if estado.lower() == "en proceso" else "📌"
        proyectos[proy].append(f"> {icono} **Cap {cap}** — `{tarea}`  *( {estado} )*")

    fields = []
    for proy, items in proyectos.items():
        fields.append({
            "name": f"📘 {proy.title()}",
            "value": "\n".join(items[:10]) + ("\n> ..." if len(items) > 10 else ""),
            "inline": False
        })

    embed = make_embed(
        title=f"🌸 Panel de Asignaciones | {user_name}",
        description=f"Hola {user_name}, tienes **{len(mis)}** tarea(s) pendiente(s) actualmente. ¡Mucho éxito! ✨",
        color=0xff7eb3,  # Un tono rosado/estético
        fields=fields[:25],
        footer="Bloom Scans • Calidad y Coherencia • Se eliminará en 5 min"
    )
    if avatar_url:
        embed["thumbnail"] = {"url": avatar_url}
    return {"embed": embed, "ephemeral": True, "auto_delete": 300}


# ──────────────────────────────────────────────
# /helps
# ──────────────────────────────────────────────
def cmd_helps():
    fields = [
        {"name": "📝 /terminado", "value": "Registra un capítulo que terminaste (rol + serie + cap).", "inline": False},
        {"name": "📋 /trabajos", "value": "Muestra tus capítulos completados del mes actual.", "inline": False},
        {"name": "🔍 /ver_asignacion", "value": "Consulta quién está asignado a un capítulo.", "inline": False},
        {"name": "🎯 /asignarme", "value": "Asígnate automáticamente a un capítulo disponible.", "inline": False},
        {"name": "📌 /mis_asignaciones", "value": "Muestra todas tus tareas pendientes.", "inline": False},
        {"name": "🏆 /creditos", "value": "Muestra el staff que trabajó en un capítulo.", "inline": False},
        {"name": "🏅 /posibles_ganadores", "value": "Ranking del staff más activo del mes.", "inline": False},
        {"name": "✨ /apodo", "value": "Configura tu nombre artístico para créditos.", "inline": False},
        {"name": "🚫 /abandonar", "value": "Libera una tarea que tenías asignada.", "inline": False},
        {"name": "😴 /ausente", "value": "Registra una ausencia temporal (días + motivo).", "inline": False},
        {"name": "✅ /cancelar_ausencia", "value": "Cancela tu ausencia si regresaste antes.", "inline": False},
        {"name": "📧 /registrar_correo", "value": "Registra tu correo para acceso a Drive.", "inline": False},
    ]
    embed = make_embed(
        title="🌸 Guía de Comandos — Bloom Scans Staff",
        description="Aquí tienes todos los comandos disponibles para el staff.\nUsa cada comando con `/` en Discord.",
        color=0xff7eb3,
        fields=fields,
        footer="Bloom Scans • Staff Bot • /helps"
    )
    return {"embed": embed, "ephemeral": True}

