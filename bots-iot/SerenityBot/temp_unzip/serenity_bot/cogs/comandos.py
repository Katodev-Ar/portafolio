# -*- coding: utf-8 -*-
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import sqlite3
import gspread
import asyncio
import re
import unicodedata
from database import (
    actualizar_actividad,
    set_ausencia,
    obtener_ausencia,
    borrar_ausencia,
    obtener_siguiente_ticket,
    list_series,
    get_serie_by_name,
    replace_series,
    upsert_series,
    list_asignaciones,
    add_asignacion,
    update_asignacion_estado,
    delete_asignacion,
    list_registros,
    add_registro,
    replace_registros,
)

# IDs DE CONFIGURACIÓN
ADMIN_CHANNEL_ID = 1432254360666247168
AVISOS_CHANNEL_ID = 1444910811863711825
STAFF_ROLE_ID = 1132158706851786854
CANAL_JUSTIFICACION_ID = 1458363364727328903
CANAL_TICKET_COMANDO = 1459418420436013282
CATEGORIA_TICKETS = 1458356934489935882
BIENVENIDA_CHANNEL_ID = 1458357173737361520
REGLAS_CHANNEL_ID = 1458360744893481045
CANAL_CREDITOS_APODO = 1458363518725390452
CANAL_ASIGNACIONES_LOG = 1460771399999160442
CANAL_COORDINADORES_ID = 1483864769239978064
COORDINADOR_ROLE_ID = 1460674417460777138
SERIE_HEADERS = ["Cap", "Idioma", "RAW", "Clean", "Traduccion", "Edicion", "Recorte", "Subido_Web", "Fecha_RAW"]
BLOCK_WIDTH = 11
OWNER_SHEET_TITLES = {
    "1154257480734490664": "Itsuki",
    "643559580990701596": "Kato",
    "1203552106041180220": "Celeste",
    "1123475061664387093": "El pirateador",
}

CANALES_TERMINADOS = [1458345407959797902, 1458345512624459951, 1458345602151878767]

class ComandosBloom(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_inactividad.start()
        conn = sqlite3.connect("actividad.db")
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS apodos (user_id INTEGER PRIMARY KEY, apodo TEXT)")
        conn.commit()
        conn.close()

    def cog_unload(self):
        self.check_inactividad.cancel()

    async def sheets_call(self, func, *args, retries=4, base_delay=1.5, **kwargs):
        ultimo_error = None
        for intento in range(retries):
            try:
                return await asyncio.to_thread(func, *args, **kwargs)
            except gspread.exceptions.APIError as e:
                ultimo_error = e
                if "429" not in str(e):
                    raise
                if intento == retries - 1:
                    raise
                await asyncio.sleep(base_delay * (intento + 1))
        raise ultimo_error

    async def obtener_worksheet(self, title: str):
        return await self.sheets_call(self.bot.spreadsheet.worksheet, title)

    async def obtener_records_worksheet(self, title: str):
        hoja = await self.obtener_worksheet(title)
        datos = await self.sheets_call(hoja.get_all_records)
        return hoja, datos

    async def db_list_series(self):
        return await asyncio.to_thread(list_series)

    async def db_get_serie_by_name(self, nombre: str):
        return await asyncio.to_thread(get_serie_by_name, nombre)

    async def db_list_asignaciones(self):
        return await asyncio.to_thread(list_asignaciones)

    async def db_add_asignacion(self, proyecto, capitulo, tarea, usuario, estado, id_usuario):
        return await asyncio.to_thread(add_asignacion, proyecto, capitulo, tarea, usuario, estado, id_usuario)

    async def db_update_asignacion_estado(self, asignacion_id, estado):
        return await asyncio.to_thread(update_asignacion_estado, asignacion_id, estado)

    async def db_delete_asignacion(self, asignacion_id):
        return await asyncio.to_thread(delete_asignacion, asignacion_id)

    async def db_list_registros(self):
        return await asyncio.to_thread(list_registros)

    async def db_add_registro(self, fecha, usuario, proyecto, capitulo, tarea, id_usuario):
        return await asyncio.to_thread(add_registro, fecha, usuario, proyecto, capitulo, tarea, id_usuario)

    async def sync_asignaciones_sheet(self):
        hoja = await self.obtener_worksheet("Asignaciones")
        filas = await self.db_list_asignaciones()
        headers = ["Proyecto", "Capítulo", "Tarea", "Usuario", "Estado", "ID_Usuario"]
        values = [headers] + [
            [fila.get("Proyecto", ""), fila.get("Capítulo", ""), fila.get("Tarea", ""), fila.get("Usuario", ""), fila.get("Estado", ""), fila.get("ID_Usuario", "")]
            for fila in filas
        ]
        await self.sheets_call(hoja.clear)
        await self.sheets_call(hoja.update, values=values, range_name=f"A1:F{len(values)}")

    async def resetear_estados_en_proceso_hojas_responsables(self):
        for titulo in OWNER_SHEET_TITLES.values():
            try:
                hoja = await self.obtener_worksheet(titulo)
            except Exception:
                continue

            valores = await self.sheets_call(hoja.get_all_values)
            if not valores:
                continue

            cambiado = False
            for row_idx in range(4, len(valores)):
                fila = valores[row_idx]
                if not fila:
                    continue
                for start_col in range(0, max(len(fila), 1), BLOCK_WIDTH):
                    for offset in (3, 4, 5):
                        col_idx = start_col + offset
                        if col_idx >= len(fila):
                            continue
                        valor = fila[col_idx]
                        if valor == "⏳":
                            valores[row_idx][col_idx] = "❌"
                            cambiado = True

            if cambiado:
                end_col = max(len(fila) for fila in valores)
                for fila in valores:
                    if len(fila) < end_col:
                        fila.extend([""] * (end_col - len(fila)))
                end_a1 = gspread.utils.rowcol_to_a1(len(valores), end_col)
                await self.sheets_call(hoja.update, values=valores, range_name=f"A1:{end_a1}")

    async def refrescar_asignaciones_desde_excel(self):
        hoja = await self.obtener_worksheet("Asignaciones")
        datos_excel = await self.sheets_call(hoja.get_all_records)

        normalizadas = []
        for fila in datos_excel:
            tarea = self.normalizar_tarea_asignacion(fila.get("Tarea", ""))
            normalizadas.append({
                "Proyecto": str(fila.get("Proyecto", "")).strip(),
                "Capítulo": str(fila.get("Capítulo", fila.get("Capitulo", ""))).strip(),
                "Tarea": tarea,
                "Usuario": str(fila.get("Usuario", "")).strip(),
                "Estado": str(fila.get("Estado", "")).strip(),
                "ID_Usuario": str(fila.get("ID_Usuario", "")).strip(),
            })

        await asyncio.to_thread(replace_asignaciones, normalizadas)
        await self.resetear_estados_en_proceso_hojas_responsables()

        activas = [fila for fila in normalizadas if fila.get("Estado") == "En Proceso"]
        aplicadas = 0
        for fila in activas:
            actualizado = await self.actualizar_estado_tarea_serie(
                fila.get("Proyecto", ""),
                fila.get("Capítulo", ""),
                fila.get("Tarea", ""),
                "⏳"
            )
            if actualizado:
                aplicadas += 1

        return len(normalizadas), len(activas), aplicadas

    async def refrescar_series_desde_excel(self):
        hoja = await self.obtener_worksheet("Series")
        datos_excel = await self.sheets_call(hoja.get_all_records)
        await asyncio.to_thread(replace_series, datos_excel)
        return len(datos_excel)

    def obtener_mes_nombre(self, num):
        meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        return meses[num - 1]

    def obtener_opciones_meses(self):
        return [
            app_commands.Choice(name="Enero", value=1),
            app_commands.Choice(name="Febrero", value=2),
            app_commands.Choice(name="Marzo", value=3),
            app_commands.Choice(name="Abril", value=4),
            app_commands.Choice(name="Mayo", value=5),
            app_commands.Choice(name="Junio", value=6),
            app_commands.Choice(name="Julio", value=7),
            app_commands.Choice(name="Agosto", value=8),
            app_commands.Choice(name="Septiembre", value=9),
            app_commands.Choice(name="Octubre", value=10),
            app_commands.Choice(name="Noviembre", value=11),
            app_commands.Choice(name="Diciembre", value=12),
        ]

    def resolver_mes_y_anio_objetivo(self, registros, mes_choice=None, anio=None):
        if mes_choice:
            return mes_choice.value, anio or datetime.now().year

        fechas = []
        for reg in registros:
            if not reg.get('Fecha'):
                continue
            try:
                fechas.append(datetime.strptime(reg['Fecha'], "%Y-%m-%d %H:%M:%S"))
            except Exception:
                continue

        if not fechas:
            ahora = datetime.now()
            return ahora.month, ahora.year

        ultima_fecha = max(fechas)
        return ultima_fecha.month, ultima_fecha.year

    def filtrar_registros_por_mes(self, registros, mes_objetivo, anio_objetivo):
        filtrados = []
        for reg in registros:
            if not reg.get('Fecha'):
                continue
            try:
                fecha = datetime.strptime(reg['Fecha'], "%Y-%m-%d %H:%M:%S")
                if fecha.month == mes_objetivo and fecha.year == anio_objetivo:
                    filtrados.append(reg)
            except Exception:
                continue
        return filtrados

    def es_admin_o_coordinador(self, interaction: discord.Interaction) -> bool:
        roles_ids = [r.id for r in interaction.user.roles]
        return interaction.user.guild_permissions.administrator or COORDINADOR_ROLE_ID in roles_ids
    
    def obtener_nombre_artistico(self, user_id, default_name):
        try:
            conn = sqlite3.connect("actividad.db")
            c = conn.cursor()
            c.execute("SELECT apodo FROM apodos WHERE user_id = ?", (user_id,))
            res = c.fetchone()
            conn.close()
            return res[0] if res else default_name
        except Exception as e:
            print(f"Error al obtener apodo: {e}")
            return default_name

    async def obtener_admin_responsable_serie(self, serie_name: str, guild: discord.Guild = None) -> str:
        try:
            serie = await self.db_get_serie_by_name(serie_name)
            if serie:
                admin_id = str(serie.get("Admin_ID", "")).strip()
                admin_nombre = str(serie.get("Admin_Nombre", "")).strip()
                if not admin_id:
                    return admin_nombre

                if guild:
                    miembro = guild.get_member(int(admin_id))
                    if miembro:
                        return miembro.mention

                return admin_nombre or f"Admin ({admin_id})"
        except Exception as e:
            print(f"Error obteniendo admin responsable: {e}")
        return ""

    async def obtener_info_serie(self, serie_name: str):
        try:
            return await self.db_get_serie_by_name(serie_name)
        except Exception as e:
            print(f"Error obteniendo info serie: {e}")
        return None

    def resolver_titulo_responsable(self, admin_id: str, admin_nombre: str) -> str:
        admin_id = str(admin_id or "").strip()
        admin_nombre = str(admin_nombre or "").strip()
        return OWNER_SHEET_TITLES.get(admin_id) or admin_nombre or "Sin responsable"

    async def obtener_bloque_serie(self, serie_name: str):
        try:
            serie_info = await self.obtener_info_serie(serie_name)
            if not serie_info:
                return None, None

            titulo_hoja = self.resolver_titulo_responsable(
                serie_info.get("Admin_ID", ""),
                serie_info.get("Admin_Nombre", ""),
            )
            try:
                hoja_responsable = await self.obtener_worksheet(titulo_hoja)
            except Exception:
                hojas = await self.sheets_call(self.bot.spreadsheet.worksheets)
                hoja_responsable = next(
                    (ws for ws in hojas if str(ws.title).strip().lower() == titulo_hoja.strip().lower()),
                    None
                )
                if not hoja_responsable:
                    return None, None
            valores = await self.sheets_call(hoja_responsable.get_all_values)
            fila_titulos = valores[0] if valores else []

            for start_col in range(1, hoja_responsable.col_count + 1, BLOCK_WIDTH):
                idx = start_col - 1
                titulo = fila_titulos[idx] if idx < len(fila_titulos) else ""
                if self.proyectos_coinciden(titulo, serie_name):
                    return hoja_responsable, start_col
        except Exception as e:
            print(f"Error obteniendo bloque serie: {e}")
        return None, None

    def normalizar_nombre_drive(self, nombre: str) -> str:
        texto = unicodedata.normalize("NFKD", str(nombre or ""))
        texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
        return texto.lower().strip()

    def extraer_numero_capitulo(self, valor: str) -> str:
        texto = re.sub(r'\.[a-zA-Z0-9]+$', '', str(valor or '')).strip()
        if not texto:
            return ""

        texto_normalizado = texto.lower().replace('_', ' ')
        patrones = [
            r'(?:cap(?:itulo)?|chapter|ch|episodio|ep)\s*[:#-]?\s*(\d+(?:[.-]\d+)?)',
            r'(?:traduccion|traducción|trad|clean|clrd|edicion|edición|type|recorte|raw)\s*[:#-]?\s*(\d+(?:[.-]\d+)?)',
            r'(\d+(?:[.-]\d+)?)',
        ]

        for patron in patrones:
            match = re.search(patron, texto_normalizado, re.IGNORECASE)
            if match:
                return match.group(1).replace('.', '-')

        return texto.strip()

    def proyectos_coinciden(self, proyecto_a: str, proyecto_b: str) -> bool:
        return str(proyecto_a or "").strip().lower() == str(proyecto_b or "").strip().lower()

    def capitulos_coinciden(self, capitulo_a: str, capitulo_b: str) -> bool:
        return self.extraer_numero_capitulo(str(capitulo_a)) == self.extraer_numero_capitulo(str(capitulo_b))

    def normalizar_tarea_asignacion(self, tarea: str) -> str:
        equivalencias = {
            "Clean": "Cleaner",
            "Cleaner": "Cleaner",
            "Traduccion": "Traductor",
            "Traductor": "Traductor",
            "Edicion": "Editor",
            "Editor": "Editor",
        }
        return equivalencias.get(str(tarea or "").strip(), str(tarea or "").strip())

    def resolver_nombre_staff(self, user_id, default_name):
        return self.obtener_nombre_artistico(user_id, default_name or "Desconocido")

    def fila_asignacion_coincide(self, fila, proyecto: str, capitulo: str, tarea: str = None, usuario_id=None, incluir_terminadas: bool = True) -> bool:
        if not self.proyectos_coinciden(fila.get('Proyecto', ''), proyecto):
            return False
        if not self.capitulos_coinciden(fila.get('Capítulo', ''), capitulo):
            return False
        if tarea is not None and self.normalizar_tarea_asignacion(fila.get('Tarea')) != self.normalizar_tarea_asignacion(tarea):
            return False
        if usuario_id is not None and str(fila.get('ID_Usuario', '')) != str(usuario_id):
            return False
        if not incluir_terminadas and fila.get('Estado') == "Terminado":
            return False
        return True

    def fila_registro_coincide(self, fila, proyecto: str, capitulo: str, tarea: str = None, usuario_id=None) -> bool:
        if not self.proyectos_coinciden(fila.get('Proyecto', ''), proyecto):
            return False
        if not self.capitulos_coinciden(fila.get('Capítulo', ''), capitulo):
            return False
        if tarea is not None and fila.get('Tarea') != tarea:
            return False
        if usuario_id is not None and str(fila.get('ID_Usuario', '')) != str(usuario_id):
            return False
        return True

    def carpeta_drive_coincide(self, rol: str, nombre_carpeta: str) -> bool:
        nombre_normalizado = self.normalizar_nombre_drive(nombre_carpeta)
        aliases = {
            "Cleaner": ["2_clrd", "2_clean"],
            "Traductor": ["3_traduccion", "3_tl", "tl"],
            "Editor": ["4_type", "4_ts", "ts"],
        }
        return any(alias in nombre_normalizado for alias in aliases.get(rol, []))

    def obtener_menciones_admins_generales(self, guild: discord.Guild) -> str:
        menciones = []
        vistos = set()

        for member in guild.members:
            if member.bot:
                continue
            es_admin = member.guild_permissions.administrator
            es_coordinador = any(role.id == COORDINADOR_ROLE_ID for role in getattr(member, "roles", []))
            if not es_admin and not es_coordinador:
                continue
            if member.id in vistos:
                continue
            vistos.add(member.id)
            menciones.append(member.mention)

        return " ".join(menciones[:8])

    def obtener_drive_service(self):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        creds = service_account.Credentials.from_service_account_file(
            "credentials.json",
            scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
        return build('drive', 'v3', credentials=creds)

    async def verificar_archivo_en_drive(self, serie_name: str, capitulo: str, rol: str) -> bool:
        """Verifica que exista el archivo/carpeta del cap en el Drive según el rol"""
        try:
            serie_info = await self.db_get_serie_by_name(serie_name)

            if not serie_info:
                return True

            folder_id_principal = serie_info.get('Folder_ID', '')
            if not folder_id_principal:
                return True

            if rol not in {"Cleaner", "Traductor", "Editor"}:
                return True

            service = self.obtener_drive_service()

            carpetas_principales = await asyncio.to_thread(
                lambda: service.files().list(
                    q=f"'{folder_id_principal}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                    fields="files(id, name)"
                ).execute()
            )

            folder_etapa = None
            for carpeta in carpetas_principales.get('files', []):
                if self.carpeta_drive_coincide(rol, carpeta['name']):
                    folder_etapa = carpeta['id']
                    break

            if not folder_etapa:
                return False

            if rol == "Traductor":
                resultado = await asyncio.to_thread(
                    lambda: service.files().list(
                        q=f"'{folder_etapa}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed=false",
                        fields="files(id, name)"
                    ).execute()
                )
            else:
                resultado = await asyncio.to_thread(
                    lambda: service.files().list(
                        q=f"'{folder_etapa}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                        fields="files(id, name)"
                    ).execute()
                )

            items = resultado.get('files', [])
            cap_str = self.extraer_numero_capitulo(str(capitulo))

            for item in items:
                item_num = self.extraer_numero_capitulo(item['name'])
                if item_num == cap_str:
                    return True

            return False

        except Exception as e:
            print(f"Error verificando Drive: {e}")
            return True

    async def actualizar_hoja_serie_terminado(self, serie_name: str, capitulo: str, rol: str) -> bool:
        """Actualiza la columna correspondiente en la hoja de la serie al marcar terminado"""
        return await self.actualizar_estado_tarea_serie(serie_name, capitulo, rol, "✅")

    async def actualizar_estado_tarea_serie(self, serie_name: str, capitulo: str, rol: str, valor: str) -> bool:
        """Actualiza el estado visual de una tarea en la hoja del responsable."""
        try:
            hoja_serie, start_col = await self.obtener_bloque_serie(serie_name)
            if not hoja_serie or not start_col:
                return False

            columnas_rol = {
                "Cleaner": 3,
                "Traductor": 4,
                "Editor": 5
            }
            offset = columnas_rol.get(rol)
            if offset is None:
                return False

            valores = await self.sheets_call(hoja_serie.get_all_values)
            cap_str = self.extraer_numero_capitulo(str(capitulo))

            for row_idx in range(4, len(valores)):
                fila = valores[row_idx]
                col_idx = start_col - 1
                nombre_cap = self.extraer_numero_capitulo(str(fila[col_idx] if col_idx < len(fila) else "").strip())
                if not nombre_cap:
                    break
                if nombre_cap == cap_str:
                    await self.sheets_call(hoja_serie.update_cell, row_idx + 1, start_col + offset, valor)
                    print(f"✅ Estado {valor} aplicado a {rol} cap {capitulo} en hoja de responsable para {serie_name}")
                    return True

            return False

        except Exception as e:
            print(f"Error actualizando hoja serie: {e}")
            return False

    # ==========================================
    #                EVENTOS
    # ==========================================

    @commands.Cog.listener()
    async def on_member_join(self, member):
        await self.ejecutar_bienvenida_completa(member)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        chan = self.bot.get_channel(ADMIN_CHANNEL_ID)
        if chan:
            embed = discord.Embed(
                title="🏃 Usuario ha salido",
                description=f"El usuario **{member.name}** ({member.mention}) abandonó el servidor.",
                color=discord.Color.dark_grey()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await chan.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return
        actualizar_actividad(message.author.id)
        if message.mentions:
            for mencionado in message.mentions:
                fecha_iso = obtener_ausencia(mencionado.id)
                if fecha_iso:
                    fecha_fin = datetime.fromisoformat(fecha_iso)
                    if datetime.now() < fecha_fin:
                        embed = discord.Embed(
                            title="🛡️ Escudo de Ausencia",
                            description=f"{mencionado.mention} no debe ser mencionado, pues pidió ausentarse.",
                            color=discord.Color.orange()
                        )
                        embed.add_field(name="📅 Regresa en", value=f"<t:{int(fecha_fin.timestamp())}:R>")
                        embed.set_footer(text="Bloom Scans - Respetamos el descanso del staff.")
                        await message.channel.send(embed=embed, delete_after=15)

    # ==========================================
    #             SISTEMA DE APODOS
    # ==========================================

    @app_commands.command(name="apodo", description="Establece tu nombre artístico para los créditos")
    async def apodo(self, interaction: discord.Interaction, nombre: str):
        if interaction.channel_id != CANAL_CREDITOS_APODO:
            await interaction.response.send_message(f"❌ Este comando solo puede usarse en <#{CANAL_CREDITOS_APODO}>.", ephemeral=True)
            return
        conn = sqlite3.connect("actividad.db")
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO apodos (user_id, apodo) VALUES (?, ?)", (interaction.user.id, nombre))
        conn.commit()
        conn.close()
        embed = discord.Embed(title="✨ Nombre Artístico Configurado", description=f"¡Hola {interaction.user.mention}! Tu apodo ha sido guardado.", color=0xffb6c1)
        embed.add_field(name="🎨 Apodo para Créditos", value=f"**{nombre}**", inline=False)
        embed.add_field(name="📋 Nota importante", value="Este nombre **solo** se usará cuando alguien use `/creditos`.", inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Bloom Scans • Gestión de identidad artística.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="asignar", description="ADMIN/COORD: Asigna a un miembro a una tarea de un capítulo")
    @app_commands.choices(tarea=[
        app_commands.Choice(name="Traductor", value="Traductor"),
        app_commands.Choice(name="Editor", value="Editor"),
        app_commands.Choice(name="Cleaner", value="Cleaner"),
    ])
    async def asignar(self, interaction: discord.Interaction, usuario: discord.Member, tarea: app_commands.Choice[str], serie: discord.TextChannel, capitulo: str):
        if not self.es_admin_o_coordinador(interaction):
            await interaction.response.send_message("❌ No tienes permisos para usar este comando.", ephemeral=True)
            return

        await interaction.response.defer()
        try:
            datos = await self.db_list_asignaciones()
            
            for fila in datos:
                if self.fila_asignacion_coincide(fila, serie.name, capitulo, tarea=tarea.value):
                    await interaction.followup.send(
                        f"❌ **Error: Tarea duplicada detectada**\n\n"
                        f"📋 **Proyecto:** {serie.name}\n📌 **Capítulo:** `{capitulo}`\n🛠️ **Tarea:** {tarea.value}\n\n"
                        f"🔴 **Estado actual:** `{fila['Estado']}`\n👤 **Asignado a:** {fila['Usuario']}\n\n"
                        f"💡 **Solución:** Si necesitas reasignar, primero usa `/cancelar_asignacion`.",
                        ephemeral=True
                    )
                    return

            try:
                await serie.set_permissions(usuario, view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True)
            except discord.Forbidden:
                await interaction.followup.send("⚠️ No tengo permisos para modificar este canal.", ephemeral=True)
                return
            except Exception as e:
                print(f"Error dando permisos: {e}")

            nombre_buscado = serie.name.replace("-", " ").lower()
            rol = next((r for r in interaction.guild.roles if r.name.lower() == nombre_buscado), None)
            resumen_rol = f"\n✅ Se otorgó el rol **{rol.name}**." if rol else f"\n⚠️ No se encontró el rol. Crea uno llamado: **{serie.name.replace('-', ' ').title()}**"
            if rol:
                await usuario.add_roles(rol)

            await self.db_add_asignacion(serie.name, capitulo, tarea.value, usuario.name, "En Proceso", str(usuario.id))
            await self.sync_asignaciones_sheet()
            await self.actualizar_estado_tarea_serie(serie.name, capitulo, tarea.value, "⏳")

            embed_serie = discord.Embed(title="🌸 Nueva Tarea Asignada", description=f"¡Hola {usuario.mention}! Se te ha asignado un nuevo capítulo.", color=0xffb6c1)
            embed_serie.add_field(name="🛠️ Tarea", value=f"**{tarea.name}**", inline=True)
            embed_serie.add_field(name="📌 Capítulo", value=f"**{capitulo}**", inline=True)
            embed_serie.set_footer(text="Bloom Scans • Calidad y Coherencia")
            await serie.send(content=f"{usuario.mention}", embed=embed_serie)

            canal_asig = self.bot.get_channel(CANAL_ASIGNACIONES_LOG)
            if canal_asig:
                embed_log = discord.Embed(title="✨ Asignación Registrada", color=0x3498db)
                embed_log.add_field(name="Proyecto", value=serie.mention, inline=True)
                embed_log.add_field(name="Capítulo", value=f"`{capitulo}`", inline=True)
                embed_log.add_field(name="Staff", value=usuario.mention, inline=True)
                embed_log.add_field(name="Tarea", value=tarea.name, inline=False)
                embed_log.set_footer(text=f"ID:{usuario.id} | Cap:{capitulo}")
                await canal_asig.send(embed=embed_log)
            
            await interaction.followup.send(f"✅ Asignado **{usuario.name}** a **{serie.name} {capitulo}**.\n🔓 Acceso al canal otorgado.{resumen_rol}")
        
        except Exception as e:
            print(f"Error en asignar: {e}")
            await interaction.followup.send(f"❌ Error crítico: {e}")

    @app_commands.command(name="ver_asignacion", description="ADMIN: Revisa quién está trabajando en un capítulo")
    async def ver_asignacion(self, interaction: discord.Interaction, serie: discord.TextChannel, capitulo: str):
        await interaction.response.defer()
        try:
            datos = await self.db_list_asignaciones()
            staff_estado = {"Traductor": "⚪ No asignado", "Editor": "⚪ No asignado", "Cleaner": "⚪ No asignado"}
            for fila in datos:
                if self.fila_asignacion_coincide(fila, serie.name, capitulo):
                    estado = "✅ Terminado" if fila['Estado'] == "Terminado" else "⏳ En Proceso"
                    tarea_normalizada = self.normalizar_tarea_asignacion(fila.get('Tarea'))
                    if tarea_normalizada in staff_estado:
                        staff_estado[tarea_normalizada] = f"👤 **{fila['Usuario']}** — {estado}"
            embed = discord.Embed(title=f"📋 Estado del Proyecto: {serie.name}", description=f"**Capítulo:** `{capitulo}`", color=0xffb6c1)
            for tarea, info in staff_estado.items():
                embed.add_field(name=f"✨ {tarea}", value=info, inline=False)
            embed.set_footer(text="Consulta de gestión interna • Bloom Scans")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"Error en ver_asignacion: {e}")
            await interaction.followup.send("❌ Ocurrió un error al consultar las asignaciones.")

    # ==========================================
    #             LÓGICA DE BIENVENIDA
    # ==========================================
    async def ejecutar_bienvenida_completa(self, member):
        rol = member.guild.get_role(STAFF_ROLE_ID)
        if rol:
            try: await member.add_roles(rol)
            except: pass
        actualizar_actividad(member.id)
        canal = self.bot.get_channel(BIENVENIDA_CHANNEL_ID)
        if canal:
            embed = discord.Embed(
                title="✦・✧ ＢＩＥＮＶＥＮＩＤ@ ＡＬ ＳＴＡＦＦ ＤＥ ＢＬＯＯＭ ＳＣＡＮＳ ✧・✦",
                description="┌─  ──────────────────┐\nNos alegra darte la bienvenida al equipo de Bloom Scans.\nEste proyecto se construye con compromiso, orden y pasión por los manwhas.\n└──────────────────────┘",
                color=0xffb6c1
            )
            embed.add_field(name="❖ Información Importante", value=f"✨ Revisa nuestras reglas en <#{REGLAS_CHANNEL_ID}>\n📢 Mira el sistema de premios en <#{AVISOS_CHANNEL_ID}>\n📂 En el canal **#para-staff** tienes las tipografías y herramientas oficiales.", inline=False)
            embed.add_field(name="❖ Soporte", value=f"Si necesitas hablar en privado con un admin, usa `/ticket` en <#{CANAL_TICKET_COMANDO}>.", inline=False)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text="Trabajemos juntos con calidad y coherencia. ✨")
            await canal.send(content=f"🌸 {member.mention}, ¡te estábamos esperando!", embed=embed)

    # ==========================================
    #             COMANDOS SLASH
    # ==========================================

    @app_commands.command(name="dar_bienvenida", description="ADMIN: Da el rol de staff y la bienvenida manualmente")
    @app_commands.checks.has_permissions(administrator=True)
    async def dar_bienvenida(self, interaction: discord.Interaction, usuario: discord.Member):
        await interaction.response.defer(ephemeral=True)
        await self.ejecutar_bienvenida_completa(usuario)
        await interaction.followup.send(f"✅ Bienvenida procesada para {usuario.mention}.", ephemeral=True)

    @app_commands.command(name="terminado", description="Registra un capítulo finalizado")
    @app_commands.choices(rol=[
        app_commands.Choice(name="Traductor", value="Traductor"),
        app_commands.Choice(name="Editor", value="Editor"),
        app_commands.Choice(name="Cleaner", value="Cleaner"),
    ])
    async def terminado(self, interaction: discord.Interaction, rol: app_commands.Choice[str], serie: discord.TextChannel, capitulo: str):
        if interaction.channel_id not in CANALES_TERMINADOS:
            await interaction.response.send_message("❌ Este comando solo funciona en los canales de 'Terminados'.", ephemeral=True)
            return

        await interaction.response.defer()

        try:
            # --- VERIFICAR ARCHIVO EN DRIVE ---
            archivo_existe = await self.verificar_archivo_en_drive(serie.name, capitulo, rol.value)

            # --- VERIFICACIÓN DE ASIGNACIÓN ---
            asig_datos = await self.db_list_asignaciones()
            asignacion_id = None
            datos_de_la_fila = None
            
            for fila in asig_datos:
                if self.fila_asignacion_coincide(
                    fila,
                    serie.name,
                    capitulo,
                    tarea=rol.value,
                    usuario_id=interaction.user.id
                ):
                    asignacion_id = fila.get("id")
                    datos_de_la_fila = fila
                    break
            
            if asignacion_id is None:
                await interaction.followup.send("❌ No estás asignado a esta tarea o los datos no coinciden.", ephemeral=True)
                return

            if datos_de_la_fila['Estado'] == "Terminado":
                await interaction.followup.send("⚠️ Esta tarea ya fue registrada como **Terminada** anteriormente.", ephemeral=True)
                return

            reg_datos = await self.db_list_registros()
            
            registro_existente = False
            for fila in reg_datos:
                if self.fila_registro_coincide(
                    fila,
                    serie.name,
                    capitulo,
                    tarea=rol.value,
                    usuario_id=interaction.user.id
                ):
                    registro_existente = True
                    break

            # --- REGISTRAR ---
            actualizar_actividad(interaction.user.id)
            fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if not registro_existente:
                await self.db_add_registro(fecha_hoy, interaction.user.name, serie.name, capitulo, rol.value, str(interaction.user.id))
                sheet_reg = await self.obtener_worksheet("Registro")
                await self.sheets_call(sheet_reg.append_row, [fecha_hoy, interaction.user.name, serie.name, capitulo, rol.value, str(interaction.user.id)])
            await self.db_update_asignacion_estado(asignacion_id, "Terminado")
            await self.sync_asignaciones_sheet()

            # --- ACTUALIZAR HOJA DE LA SERIE ---
            hoja_actualizada = await self.actualizar_hoja_serie_terminado(serie.name, capitulo, rol.value)

            canal_revision = self.bot.get_channel(CANAL_COORDINADORES_ID)
            if canal_revision:
                admin_responsable = await self.obtener_admin_responsable_serie(serie.name, interaction.guild)
                menciones = admin_responsable or self.obtener_menciones_admins_generales(interaction.guild)
                embed_admin = discord.Embed(
                    title="📢 Tarea terminada",
                    description=f"{interaction.user.mention} terminó una tarea.",
                    color=discord.Color.blue()
                )
                embed_admin.add_field(name="📚 Serie", value=serie.mention, inline=True)
                embed_admin.add_field(name="📌 Capítulo", value=f"`{capitulo}`", inline=True)
                embed_admin.add_field(name="🛠️ Rol", value=rol.value, inline=True)
                embed_admin.add_field(name="📄 Registro", value="✅ Actualizado" if not registro_existente else "⚠️ Ya existía", inline=True)
                embed_admin.add_field(name="📋 Hoja del manhwa", value="✅ Actualizada" if hoja_actualizada else "⚠️ No se encontró fila", inline=True)
                embed_admin.set_footer(text="Bloom Scans • Revisión administrativa")
                await canal_revision.send(content=menciones, embed=embed_admin)

            embed = discord.Embed(title="✅ Trabajo Registrado", description=f"¡Buen trabajo {interaction.user.mention}!", color=discord.Color.green())
            embed.add_field(name="📚 Proyecto", value=serie.mention, inline=True)
            embed.add_field(name="🛠️ Rol", value=f"**{rol.name}**", inline=True)
            embed.add_field(name="📌 Capítulo", value=f"`{capitulo}`", inline=True)
            embed.set_footer(text="Bloom Scans - Usa /trabajos para ver tu acumulado.")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"Error en terminado: {e}")
            await interaction.followup.send(f"❌ Error al procesar el registro: {e}", ephemeral=True)

    @app_commands.command(name="creditos", description="Muestra el staff que trabajó en un capítulo específico")
    async def creditos(self, interaction: discord.Interaction, serie: discord.TextChannel, capitulo: str):
        await interaction.response.defer()
        try:
            datos_asig = await self.db_list_asignaciones()
            datos_reg = await self.db_list_registros()
            staff_encontrado = {"Traductor": "⚪ Pendiente", "Editor": "⚪ Pendiente", "Cleaner": "⚪ Pendiente"}
            hay_coincidencia = False

            for fila in datos_asig:
                if self.fila_asignacion_coincide(fila, serie.name, capitulo):
                    user_id = fila.get('ID_Usuario')
                    nombre_a_mostrar = self.resolver_nombre_staff(user_id, fila.get('Usuario', 'Desconocido'))
                    rol_en_fila = fila.get('Tarea')
                    if rol_en_fila in staff_encontrado:
                        if fila.get('Estado') == "Terminado":
                            staff_encontrado[rol_en_fila] = f"✅ {nombre_a_mostrar}"
                        else:
                            staff_encontrado[rol_en_fila] = f"⏳ {nombre_a_mostrar} — En Proceso"
                        hay_coincidencia = True

            for fila in datos_reg:
                if self.fila_registro_coincide(fila, serie.name, capitulo):
                    user_id = fila.get('ID_Usuario')
                    nombre_a_mostrar = self.resolver_nombre_staff(user_id, fila.get('Usuario', 'Desconocido'))
                    rol_en_fila = fila.get('Tarea')
                    if rol_en_fila in staff_encontrado:
                        staff_encontrado[rol_en_fila] = f"✅ {nombre_a_mostrar}"
                        hay_coincidencia = True

            embed = discord.Embed(
                title=f"🌸 Créditos: {serie.name}",
                description=f"**Capítulo:** {capitulo}\n" + ("" if hay_coincidencia else "⚠️ *No hay asignaciones para este capítulo.*"),
                color=0xffb6c1 if hay_coincidencia else discord.Color.orange()
            )
            for rol, estado in staff_encontrado.items():
                embed.add_field(name=rol, value=estado, inline=True)
            embed.set_footer(text="Información extraída de Asignaciones • Bloom Scans")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"Error en créditos: {e}")
            await interaction.followup.send("❌ Ocurrió un error al consultar la hoja de cálculo.")

    @app_commands.command(name="trabajos", description="Mira cuántos trabajos llevas acumulados")
    @app_commands.choices(mes=[
        app_commands.Choice(name="Enero", value=1), app_commands.Choice(name="Febrero", value=2),
        app_commands.Choice(name="Marzo", value=3), app_commands.Choice(name="Abril", value=4),
        app_commands.Choice(name="Mayo", value=5), app_commands.Choice(name="Junio", value=6),
        app_commands.Choice(name="Julio", value=7), app_commands.Choice(name="Agosto", value=8),
        app_commands.Choice(name="Septiembre", value=9), app_commands.Choice(name="Octubre", value=10),
        app_commands.Choice(name="Noviembre", value=11), app_commands.Choice(name="Diciembre", value=12),
    ])
    async def trabajos(self, interaction: discord.Interaction, mes: app_commands.Choice[int] = None):
        await interaction.response.defer(ephemeral=True)
        mes_query = mes.value if mes else datetime.now().month
        nombre_mes = self.obtener_mes_nombre(mes_query)
        datos = await self.db_list_registros()
        conteo = 0
        for fila in datos:
            if not fila.get('Fecha'): continue
            try:
                if str(fila['ID_Usuario']) == str(interaction.user.id):
                    f_dt = datetime.strptime(fila['Fecha'], "%Y-%m-%d %H:%M:%S")
                    if f_dt.month == mes_query:
                        conteo += 1
            except: continue
        embed = discord.Embed(title="📊 Tu Rendimiento", color=0xffb6c1)
        embed.add_field(name="Mes", value=nombre_mes, inline=True)
        embed.add_field(name="Total Trabajos", value=f"**{conteo}** capítulos", inline=True)
        embed.set_footer(text="Bloom Scans - ¡Sigue así!")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="vertrabajos", description="ADMIN: Mira la cantidad de trabajos de un miembro")
    @app_commands.choices(mes=[
        app_commands.Choice(name="Enero", value=1), app_commands.Choice(name="Febrero", value=2),
        app_commands.Choice(name="Marzo", value=3), app_commands.Choice(name="Abril", value=4),
        app_commands.Choice(name="Mayo", value=5), app_commands.Choice(name="Junio", value=6),
        app_commands.Choice(name="Julio", value=7), app_commands.Choice(name="Agosto", value=8),
        app_commands.Choice(name="Septiembre", value=9), app_commands.Choice(name="Octubre", value=10),
        app_commands.Choice(name="Noviembre", value=11), app_commands.Choice(name="Diciembre", value=12),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def vertrabajos(self, interaction: discord.Interaction, usuario: discord.Member, mes: app_commands.Choice[int] = None):
        await interaction.response.defer(ephemeral=True)
        mes_query = mes.value if mes else datetime.now().month
        nombre_mes = self.obtener_mes_nombre(mes_query)
        datos = await self.db_list_registros()
        conteo = 0
        for fila in datos:
            if not fila.get('Fecha'): continue
            try:
                if str(fila['ID_Usuario']) == str(usuario.id):
                    f_dt = datetime.strptime(fila['Fecha'], "%Y-%m-%d %H:%M:%S")
                    if f_dt.month == mes_query:
                        conteo += 1
            except: continue
        embed = discord.Embed(title="📋 Reporte Administrativo", color=discord.Color.purple())
        embed.set_thumbnail(url=usuario.display_avatar.url)
        embed.add_field(name="Staff", value=usuario.mention, inline=False)
        embed.add_field(name="Mes Consultado", value=nombre_mes, inline=True)
        embed.add_field(name="Cantidad", value=f"**{conteo}** caps", inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="ausente", description="Registra tu ausencia (Solo canal justificativo o Admin)")
    async def ausente(self, interaction: discord.Interaction, dias: app_commands.Range[int, 1, 30], motivo: str):
        if interaction.channel_id != CANAL_JUSTIFICACION_ID and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(f"❌ Solo puedes usar este comando en <#{CANAL_JUSTIFICACION_ID}>.", ephemeral=True)
            return
        fecha_fin = datetime.now() + timedelta(days=dias)
        set_ausencia(interaction.user.id, fecha_fin.isoformat())
        chan = self.bot.get_channel(ADMIN_CHANNEL_ID)
        embed = discord.Embed(title="💤 Registro de Ausencia", color=discord.Color.blue())
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="Staff", value=interaction.user.mention, inline=True)
        embed.add_field(name="Regresa", value=f"<t:{int(fecha_fin.timestamp())}:D>", inline=True)
        embed.add_field(name="Motivo", value=motivo, inline=False)
        if chan: await chan.send(content=f"<@&{STAFF_ROLE_ID}>", embed=embed)
        await interaction.response.send_message("✅ Ausencia registrada exitosamente. ¡Cuídate!")

    @app_commands.command(name="cancelar_ausencia", description="Cancela tu ausencia si regresaste antes")
    async def cancelar_ausencia(self, interaction: discord.Interaction):
        if interaction.channel_id != CANAL_JUSTIFICACION_ID and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(f"❌ Debes cancelar tu ausencia en <#{CANAL_JUSTIFICACION_ID}>.", ephemeral=True)
            return
        estado = obtener_ausencia(interaction.user.id)
        if estado is None:
            await interaction.response.send_message("⚠️ No tienes ninguna ausencia registrada actualmente.", ephemeral=True)
            return
        borrar_ausencia(interaction.user.id)
        chan = self.bot.get_channel(ADMIN_CHANNEL_ID)
        if chan:
            embed = discord.Embed(title="🔄 Regreso Anticipado", description=f"{interaction.user.mention} ha cancelado su ausencia.", color=discord.Color.green())
            await chan.send(embed=embed)
        await interaction.response.send_message("✅ Tu ausencia ha sido cancelada. ¡Bienvenido de vuelta!")

    @app_commands.command(name="abandonar", description="Libera una tarea asignada")
    @app_commands.choices(tarea=[
        app_commands.Choice(name="Traductor", value="Traductor"),
        app_commands.Choice(name="Editor", value="Editor"),
        app_commands.Choice(name="Cleaner", value="Cleaner"),
    ])
    async def abandonar(self, interaction: discord.Interaction, serie: discord.TextChannel, capitulo: str, tarea: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)
        try:
            datos = await self.db_list_asignaciones()
            fila_encontrada = None
            for fila in datos:
                if self.fila_asignacion_coincide(
                    fila,
                    serie.name,
                    capitulo,
                    tarea=tarea.value,
                    usuario_id=interaction.user.id,
                    incluir_terminadas=False
                ):
                    fila_encontrada = fila
                    break
            if fila_encontrada is None:
                await interaction.followup.send("❌ No encontré esa tarea asignada a ti.", ephemeral=True)
                return
            await self.borrar_mensajes_asignacion(serie, capitulo, interaction.user.id, tarea.name)
            await self.db_delete_asignacion(fila_encontrada["id"])
            await self.sync_asignaciones_sheet()
            await self.actualizar_estado_tarea_serie(serie.name, capitulo, tarea.value, "❌")
            await interaction.followup.send("✅ Has abandonado la tarea. Los mensajes de asignación han sido eliminados.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="cancelar_asignacion", description="ADMIN: Quita una asignación a la fuerza")
    @app_commands.choices(tarea=[
        app_commands.Choice(name="Traductor", value="Traductor"),
        app_commands.Choice(name="Editor", value="Editor"),
        app_commands.Choice(name="Cleaner", value="Cleaner"),
    ])
    async def cancelar_asignacion(self, interaction: discord.Interaction, serie: discord.TextChannel, capitulo: str, tarea: app_commands.Choice[str]):
        if not self.es_admin_o_coordinador(interaction):
            await interaction.response.send_message("❌ No tienes permisos para usar este comando.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            datos = await self.db_list_asignaciones()
            fila_encontrada = None
            usuario_id_encontrado = None
            for fila in datos:
                if self.fila_asignacion_coincide(fila, serie.name, capitulo, tarea=tarea.value):
                    fila_encontrada = fila
                    usuario_id_encontrado = fila['ID_Usuario']
                    break
            if fila_encontrada is None:
                await interaction.followup.send("❌ No encontré esa asignación.", ephemeral=True)
                return
            if usuario_id_encontrado:
                await self.borrar_mensajes_asignacion(serie, capitulo, usuario_id_encontrado, tarea.name)
            await self.db_delete_asignacion(fila_encontrada["id"])
            await self.sync_asignaciones_sheet()
            await self.actualizar_estado_tarea_serie(serie.name, capitulo, tarea.value, "❌")
            await interaction.followup.send(f"✅ Asignación de **{tarea.name}** cancelada y mensajes borrados.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="refrescar_asignaciones", description="ADMIN/COORD: Sincroniza Asignaciones desde el Excel hacia el bot")
    async def refrescar_asignaciones(self, interaction: discord.Interaction):
        if not self.es_admin_o_coordinador(interaction):
            await interaction.response.send_message("❌ No tienes permisos para usar este comando.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            total, activas, aplicadas = await self.refrescar_asignaciones_desde_excel()
            embed = discord.Embed(title="🔄 Asignaciones Refrescadas", color=discord.Color.green())
            embed.add_field(name="Filas leídas del Excel", value=str(total), inline=True)
            embed.add_field(name="Asignaciones en proceso", value=str(activas), inline=True)
            embed.add_field(name="⏳ Aplicadas en hojas", value=str(aplicadas), inline=True)
            embed.add_field(
                name="Qué hizo",
                value="SQLite ahora quedó igual a la hoja `Asignaciones`. Si borraste filas manualmente, ya dejaron de existir para el bot.",
                inline=False
            )
            embed.set_footer(text="Bloom Scans • Sincronización manual")
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"Error en refrescar_asignaciones: {e}")
            await interaction.followup.send(f"❌ Error al refrescar asignaciones: {e}", ephemeral=True)

    @app_commands.command(name="refrescar_series", description="ADMIN/COORD: Sincroniza la hoja Series del Excel hacia el bot")
    async def refrescar_series(self, interaction: discord.Interaction):
        if not self.es_admin_o_coordinador(interaction):
            await interaction.response.send_message("❌ No tienes permisos para usar este comando.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            total = await self.refrescar_series_desde_excel()
            embed = discord.Embed(title="🔄 Series Refrescadas", color=discord.Color.green())
            embed.add_field(name="Filas leídas del Excel", value=str(total), inline=True)
            embed.add_field(
                name="Qué hizo",
                value="SQLite ahora quedó igual a la hoja `Series`. Úsalo cuando agregues, borres o edites series manualmente en el Excel.",
                inline=False
            )
            embed.set_footer(text="Bloom Scans • Sincronización manual")
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"Error en refrescar_series: {e}")
            await interaction.followup.send(f"❌ Error al refrescar series: {e}", ephemeral=True)

    @app_commands.command(name="estatus_equipo", description="Muestra la actividad actual de los miembros de un rol")
    async def estatus_equipo(self, interaction: discord.Interaction, rol: discord.Role):
        await interaction.response.defer()
        try:
            datos = await self.db_list_asignaciones()
            asignaciones_activas = [f for f in datos if f['Estado'] == "En Proceso"]
            embed = discord.Embed(
                title=f"👥 Estatus de Equipo: {rol.name}",
                description=f"Revisando qué están haciendo los miembros con el rol {rol.mention}\n{'─' * 30}",
                color=rol.color if rol.color.value != 0 else 0xffb6c1
            )
            for miembro in rol.members:
                if miembro.bot: continue
                tareas_miembro = [t for t in asignaciones_activas if str(t['ID_Usuario']) == str(miembro.id)]
                if tareas_miembro:
                    info_tareas = ""
                    for t in tareas_miembro:
                        canal_obj = discord.utils.get(interaction.guild.text_channels, name=t['Proyecto'].lower().replace(" ", "-"))
                        canal_mencion = canal_obj.mention if canal_obj else f"#{t['Proyecto']}"
                        info_tareas += f"🔹 **{t['Tarea']}** en {canal_mencion}\n┗ 📌 *Capítulo:* `{t['Capítulo']}`\n"
                else:
                    info_tareas = "✅ *Disponible / Sin asignaciones activas*"
                embed.add_field(name=f"👤 {miembro.display_name}", value=f"{info_tareas}\n\u200b", inline=False)
            embed.set_footer(text="Bloom Scans • Gestión de flujo de trabajo", icon_url=self.bot.user.display_avatar.url)
            if not rol.members:
                await interaction.followup.send(f"⚠️ No hay nadie con el rol {rol.mention} en este servidor.")
            else:
                await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"Error en estatus_equipo: {e}")
            await interaction.followup.send(f"❌ Ocurrió un error al consultar: {e}", ephemeral=True)

    @app_commands.command(name="posibles_ganadores", description="Muestra quiénes van ganando en el ranking mensual")
    @app_commands.choices(mes=[
        app_commands.Choice(name="Enero", value=1),
        app_commands.Choice(name="Febrero", value=2),
        app_commands.Choice(name="Marzo", value=3),
        app_commands.Choice(name="Abril", value=4),
        app_commands.Choice(name="Mayo", value=5),
        app_commands.Choice(name="Junio", value=6),
        app_commands.Choice(name="Julio", value=7),
        app_commands.Choice(name="Agosto", value=8),
        app_commands.Choice(name="Septiembre", value=9),
        app_commands.Choice(name="Octubre", value=10),
        app_commands.Choice(name="Noviembre", value=11),
        app_commands.Choice(name="Diciembre", value=12),
    ])
    async def posibles_ganadores(self, interaction: discord.Interaction, mes: app_commands.Choice[int] = None, anio: int = None):
        await interaction.response.defer(ephemeral=True)
        try:
            registros = await self.db_list_registros()
            if not registros:
                await interaction.followup.send("❌ No hay datos registrados este mes.", ephemeral=True)
                return
            mes_actual, anio_actual = self.resolver_mes_y_anio_objetivo(registros, mes, anio)
            registros_filtrados = self.filtrar_registros_por_mes(registros, mes_actual, anio_actual)
            temp_ranking = {}
            for reg in registros_filtrados:
                try:
                    user_id = str(reg['ID_Usuario'])
                    if user_id not in temp_ranking:
                        temp_ranking[user_id] = {'nombre': reg['Usuario'], 'count': 0}
                    temp_ranking[user_id]['count'] += 1
                except: continue
            if not temp_ranking:
                embed = discord.Embed(title="📊 Posibles Ganadores del Mes", description=f"⚠️ **Aún no hay trabajos registrados en {self.obtener_mes_nombre(mes_actual)} de {anio_actual}.**", color=discord.Color.orange())
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            sorted_ranking = sorted(temp_ranking.items(), key=lambda x: -x[1]['count'])
            calificados = [(uid, data) for uid, data in sorted_ranking if data['count'] >= 25]
            no_calificados = [(uid, data) for uid, data in sorted_ranking if data['count'] < 25]
            embed = discord.Embed(title="🏆 POSIBLES GANADORES DEL MES 🏆", description=f"**Mes:** {self.obtener_mes_nombre(mes_actual)} {anio_actual}\n{'─' * 40}", color=0xffd700)
            if calificados:
                medallas = ["🥇", "🥈", "🥉"]
                ranking_text = "".join(f"{medallas[i] if i < 3 else '🎖️'} **{data['nombre']}** - `{data['count']}` caps\n" for i, (uid, data) in enumerate(calificados))
                embed.add_field(name="✅ CALIFICAN PARA PREMIO (25+ caps)", value=ranking_text, inline=False)
            else:
                embed.add_field(name="⚠️ NADIE CALIFICA AÚN", value="Ningún miembro ha alcanzado el mínimo de **25 capítulos** este mes.", inline=False)
            if no_calificados:
                no_calif_text = "".join(f"• **{data['nombre']}** - `{data['count']}` caps (faltan {25 - data['count']})\n" for uid, data in no_calificados[:10])
                embed.add_field(name="📌 CERCA DE CALIFICAR", value=no_calif_text or "Nadie más está trabajando.", inline=False)
            embed.add_field(name="💡 Recordatorio", value="Solo se premia a quienes completen **25 o más capítulos** al finalizar el mes.", inline=False)
            embed.set_footer(text="Bloom Scans • Motivación y Competencia Sana")
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"Error en posibles_ganadores: {e}")
            await interaction.followup.send(f"❌ Error al consultar: {e}", ephemeral=True)

    @app_commands.command(name="ticket", description="Crea un canal privado para hablar con un administrador")
    async def ticket(self, interaction: discord.Interaction, admin: discord.Member):
        if interaction.channel_id != CANAL_TICKET_COMANDO:
            await interaction.response.send_message(f"❌ Este comando solo puede usarse en <#{CANAL_TICKET_COMANDO}>.", ephemeral=True)
            return
        num_ticket = obtener_siguiente_ticket()
        guild = interaction.guild
        categoria = guild.get_channel(CATEGORIA_TICKETS)
        rol_staff = guild.get_role(STAFF_ROLE_ID)
        if not categoria:
            await interaction.response.send_message("❌ Error: No se encontró la categoría de tickets.", ephemeral=True)
            return
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            rol_staff: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            admin: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        nuevo_canal = await guild.create_text_channel(name=f"ticket-{num_ticket}", category=categoria, overwrites=overwrites)
        embed = discord.Embed(title=f"🌸 BLOOM SCANS - TICKET #{num_ticket}", description=f"Hola {interaction.user.mention}, este es tu espacio privado para hablar con {admin.mention}.", color=0xffb6c1)
        embed.add_field(name="📌 Consulta Privada", value="Este canal es invisible para el resto del staff. Por favor, deja tu duda aquí debajo.", inline=False)
        embed.set_footer(text="Privacidad garantizada por Bloom Bot.")
        await nuevo_canal.send(content=f"{interaction.user.mention} | {admin.mention}", embed=embed)
        await interaction.response.send_message(f"✅ Se ha creado tu ticket en {nuevo_canal.mention}", ephemeral=True)

    @app_commands.command(name="finalizar_mes", description="ADMIN: Genera ranking y limpia el registro de un mes")
    @app_commands.choices(mes=[
        app_commands.Choice(name="Enero", value=1),
        app_commands.Choice(name="Febrero", value=2),
        app_commands.Choice(name="Marzo", value=3),
        app_commands.Choice(name="Abril", value=4),
        app_commands.Choice(name="Mayo", value=5),
        app_commands.Choice(name="Junio", value=6),
        app_commands.Choice(name="Julio", value=7),
        app_commands.Choice(name="Agosto", value=8),
        app_commands.Choice(name="Septiembre", value=9),
        app_commands.Choice(name="Octubre", value=10),
        app_commands.Choice(name="Noviembre", value=11),
        app_commands.Choice(name="Diciembre", value=12),
    ])
    async def finalizar_mes(self, interaction: discord.Interaction, mes: app_commands.Choice[int] = None, anio: int = None):
        if interaction.user.id != 1154257480734490664:
            await interaction.response.send_message("🚫 **Acceso Denegado**\n\nEste comando está restringido exclusivamente al propietario del sistema.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        sheet_reg = await self.obtener_worksheet("Registro")
        registros = await self.sheets_call(sheet_reg.get_all_records)
        if not registros:
            await interaction.followup.send("❌ No hay datos para procesar.")
            return
        mes_objetivo, anio_objetivo = self.resolver_mes_y_anio_objetivo(registros, mes, anio)
        registros_mes = self.filtrar_registros_por_mes(registros, mes_objetivo, anio_objetivo)
        if not registros_mes:
            await interaction.followup.send(f"❌ No hay datos para {self.obtener_mes_nombre(mes_objetivo)} de {anio_objetivo}.")
            return
        temp_ranking = {}
        for reg in registros_mes:
            try:
                user_id = str(reg['ID_Usuario'])
                f_dt = datetime.strptime(reg['Fecha'], "%Y-%m-%d %H:%M:%S")
                if user_id not in temp_ranking:
                    temp_ranking[user_id] = {'nombre': reg['Usuario'], 'count': 0, 'last_time': f_dt}
                temp_ranking[user_id]['count'] += 1
                if f_dt > temp_ranking[user_id]['last_time']:
                    temp_ranking[user_id]['last_time'] = f_dt
            except: continue
        calificados = {uid: s for uid, s in temp_ranking.items() if s['count'] >= 25}
        sorted_rank = sorted(calificados.items(), key=lambda x: (-x[1]['count'], x[1]['last_time']))
        embed = discord.Embed(title="🌸 BLOOM SCANS - PREMIACIÓN MENSUAL 🌸", color=0xffb6c1)
        embed.description = f"**Mes cerrado:** {self.obtener_mes_nombre(mes_objetivo)} {anio_objetivo}\n\n¡Felicidades a los ganadores! Solo califican aquellos con **25+ trabajos**. ✨"
        podio_titulos = {0: "🥇 PRIMER LUGAR ($10)", 1: "🥈 SEGUNDO LUGAR ($5)", 2: "🥉 TERCER LUGAR ($3)"}
        menciones = ""
        if not sorted_rank:
            embed.description = f"**Mes cerrado:** {self.obtener_mes_nombre(mes_objetivo)} {anio_objetivo}\n\n⚠️ Este mes nadie alcanzó la meta mínima de 25 trabajos para el ranking."
        else:
            for i, (user_id, stats) in enumerate(sorted_rank):
                if i < 3:
                    embed.add_field(name=podio_titulos[i], value=f"👤 **{stats['nombre']}**\n📊 `{stats['count']}` caps completados.", inline=False)
                else:
                    menciones += f"• **{stats['nombre']}** ({stats['count']} caps) - $2 USD\n"
            if menciones:
                embed.add_field(name="🎖️ MENCIONES ESPECIALES (25+ caps)", value=menciones, inline=False)
        embed.set_footer(text="Los pagos se procesarán en las fechas habituales.")
        nombre_respaldo = f"Registro_{self.obtener_mes_nombre(mes_objetivo)[:3]}_{anio_objetivo}"
        headers = ["Fecha", "Usuario", "Proyecto", "Capítulo", "Tarea", "ID_Usuario"]
        try:
            await asyncio.to_thread(self.bot.spreadsheet.duplicate_sheet, sheet_reg.id, new_sheet_name=nombre_respaldo)
            hoja_respaldo = self.bot.spreadsheet.worksheet(nombre_respaldo)
            await asyncio.to_thread(hoja_respaldo.clear)
            respaldo_values = [headers] + [[reg.get(col, "") for col in headers] for reg in registros_mes]
            await asyncio.to_thread(hoja_respaldo.update, values=respaldo_values, range_name=f"A1:F{len(respaldo_values)}")

            registros_restantes = [reg for reg in registros if reg not in registros_mes]
            await asyncio.to_thread(replace_registros, registros_restantes)
            await asyncio.to_thread(sheet_reg.clear)
            valores_restantes = [headers] + [[reg.get(col, "") for col in headers] for reg in registros_restantes]
            await asyncio.to_thread(sheet_reg.update, values=valores_restantes, range_name=f"A1:F{len(valores_restantes)}")
        except Exception as e: print(f"Error archivando: {e}")
        avisos = self.bot.get_channel(AVISOS_CHANNEL_ID)
        admin_ch = self.bot.get_channel(ADMIN_CHANNEL_ID)
        if avisos: await avisos.send(content="@everyone", embed=embed)
        if admin_ch: await admin_ch.send(embed=embed)
        await interaction.followup.send(f"✅ Ranking publicado y mes cerrado exitosamente: **{self.obtener_mes_nombre(mes_objetivo)} {anio_objetivo}**.")

    @app_commands.command(name="helps", description="Mira los comandos disponibles para el staff")
    async def helps(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🌸 Bloom Scans - Guía de Comandos", color=0xffb6c1)
        embed.description = "Aquí tienes los comandos que puedes usar para gestionar tu trabajo:"
        embed.add_field(name="✅ `/terminado`", value="Registra tus capítulos finalizados.", inline=False)
        embed.add_field(name="🏃 `/abandonar`", value="Libera un capítulo si no puedes terminarlo.", inline=False)
        embed.add_field(name="📊 `/trabajos`", value="Consulta tu acumulado mensual.", inline=False)
        embed.add_field(name="💤 `/ausente`", value="Pide vacaciones/ausencia (Máx 30 días).", inline=False)
        embed.add_field(name="🔄 `/cancelar_ausencia`", value="Informa que has regresado.", inline=False)
        embed.add_field(name="🎟️ `/ticket`", value="Crea un canal privado con un administrador.", inline=False)
        embed.add_field(name="🎨 `/apodo`", value="Elige tu nombre artístico para los créditos.", inline=False)
        embed.add_field(name="🙋 `/asignarme`", value="Asígnate automáticamente a un capítulo disponible.", inline=False)
        embed.add_field(name="🏆 `/posibles_ganadores`", value="Mira el ranking actual del mes.", inline=False)
        embed.set_footer(text="Bloom Scans • Si tienes dudas, contacta a un admin.")
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(name="help_admins", description="COMANDO ADMIN: Guía avanzada para administradores")
    @app_commands.checks.has_permissions(administrator=True)
    async def help_admins(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🛠️ Panel de Control - Administración", color=discord.Color.dark_red())
        embed.description = "Comandos exclusivos para la gestión de Bloom Scans:"
        embed.add_field(name="📋 `/vertrabajos`", value="Revisa el progreso de cualquier miembro por mes.", inline=False)
        embed.add_field(name="🏆 `/posibles_ganadores`", value="Muestra el ranking actual del mes en curso.", inline=False)
        embed.add_field(name="🏁 `/finalizar_mes`", value="Genera ranking (Solo 25+ caps), archiva y limpia el Excel.", inline=False)
        embed.add_field(name="👋 `/dar_bienvenida`", value="Procesa manualmente el ingreso de un nuevo staff.", inline=False)
        embed.add_field(name="📌 `/asignar`", value="Asigna un miembro a un capítulo (Tradu, Clean o Edit).", inline=False)
        embed.add_field(name="🚫 `/cancelar_asignacion`", value="Quita una tarea asignada a alguien (uso de fuerza).", inline=False)
        embed.add_field(name="🔍 `/ver_asignacion`", value="Mira quién está trabajando en un capítulo y si ya terminó.", inline=False)
        embed.set_footer(text="Acceso Restringido • Administración Bloom Scans")
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @tasks.loop(hours=24)
    async def check_inactividad(self):
        chan = self.bot.get_channel(ADMIN_CHANNEL_ID)
        if not chan: return
        ahora = datetime.now()
        limite = ahora - timedelta(days=7)
        conn = sqlite3.connect("actividad.db")
        c = conn.cursor()
        rol_staff = chan.guild.get_role(STAFF_ROLE_ID)
        if not rol_staff: return
        for member in rol_staff.members:
            if member.bot: continue
            c.execute("SELECT last_msg, ausencia_hasta FROM usuarios WHERE user_id = ?", (member.id,))
            res = c.fetchone()
            last_msg_str = res[0] if res and res[0] else None
            ausencia_str = res[1] if res and res[1] else None
            if ausencia_str:
                aus_dt = datetime.fromisoformat(ausencia_str)
                if ahora < aus_dt: continue
            if not last_msg_str:
                embed = discord.Embed(title="🚨 Staff sin actividad", description=f"{member.mention} nunca ha registrado actividad.", color=discord.Color.red())
                await chan.send(embed=embed)
            else:
                last_dt = datetime.fromisoformat(last_msg_str)
                if last_dt < limite:
                    embed = discord.Embed(title="🚨 Alerta de Inactividad (7 días)", color=discord.Color.red())
                    embed.description = f"El staff {member.mention} lleva más de 7 días inactivo."
                    embed.add_field(name="Visto por última vez", value=f"<t:{int(last_dt.timestamp())}:R>")
                    await chan.send(embed=embed)
        conn.close()
    
    async def borrar_mensajes_asignacion(self, serie_channel, capitulo, usuario_id, tarea_name):
        canales_a_limpiar = [serie_channel, self.bot.get_channel(CANAL_ASIGNACIONES_LOG)]
        for canal in canales_a_limpiar:
            if not canal: continue
            async for message in canal.history(limit=None):
                if message.author == self.bot.user and message.embeds:
                    contenido_total = str(message.embeds[0].to_dict())
                    match_usuario = str(usuario_id) in message.content or str(usuario_id) in contenido_total
                    match_cap = str(capitulo) in contenido_total
                    if match_usuario and match_cap:
                        try:
                            await message.delete()
                            print(f"✅ Mensaje eliminado en {canal.name}")
                        except Exception as e:
                            print(f"❌ No se pudo borrar en {canal.name}: {e}")


async def setup(bot):
    await bot.add_cog(ComandosBloom(bot))
