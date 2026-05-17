# -*- coding: utf-8 -*-
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import asyncio
import gspread
import re
import random
import unicodedata
from database import (
    list_series,
    get_serie_by_name,
    get_serie_by_channel,
    upsert_series,
    list_asignaciones,
    add_asignacion,
    replace_series,
)

# ==========================================
#         IDs DE CONFIGURACIÓN
# ==========================================
COORDINADOR_ROLE_ID = 1460674417460777138
CANAL_COORDINADORES_ID = 1483864769239978064
ADMIN_CHANNEL_ID = 1432254360666247168
CANAL_ASIGNACIONES_LOG = 1460771399999160442
ITSUKI_ID = 1154257480734490664

CARPETAS_DRIVE = {
    "RAW": "1_RAW",
    "Clean": "2_CLRD",
    "Traduccion": "3_TRADUCCION",
    "Edicion": "4_TYPE",
    "Recorte": "5_RECORTES"
}
SERIE_HEADERS = ["Cap", "Idioma", "RAW", "Clean", "Traduccion", "Edicion", "Recorte", "Subido_Web", "Fecha_RAW"]
BLOCK_WIDTH = 11
OWNER_SHEET_TITLES = {
    "1154257480734490664": "Itsuki",
    "643559580990701596": "Kato",
    "1203552106041180220": "Celeste",
    "1123475061664387093": "El pirateador",
}

# ==========================================
#         COG PRINCIPAL
# ==========================================
class CoordinadorCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.revision_automatica.start()
        self.reporte_semanal.start()
        self.asignarme_locks = {}

    def cog_unload(self):
        self.revision_automatica.cancel()
        self.reporte_semanal.cancel()

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

    async def db_list_series(self):
        return await asyncio.to_thread(list_series)

    async def db_get_serie_by_name(self, nombre):
        return await asyncio.to_thread(get_serie_by_name, nombre)

    async def db_get_serie_by_channel(self, canal_id):
        return await asyncio.to_thread(get_serie_by_channel, canal_id)

    async def db_upsert_series(self, serie):
        return await asyncio.to_thread(upsert_series, serie)

    async def db_list_asignaciones(self):
        return await asyncio.to_thread(list_asignaciones)

    async def db_add_asignacion(self, proyecto, capitulo, tarea, usuario, estado, id_usuario):
        return await asyncio.to_thread(add_asignacion, proyecto, capitulo, tarea, usuario, estado, id_usuario)

    async def sync_asignaciones_sheet(self):
        hoja = await self.sheets_call(self.bot.spreadsheet.worksheet, "Asignaciones")
        filas = await self.db_list_asignaciones()
        headers = ["Proyecto", "Capítulo", "Tarea", "Usuario", "Estado", "ID_Usuario"]
        values = [headers] + [
            [fila.get("Proyecto", ""), fila.get("Capítulo", ""), fila.get("Tarea", ""), fila.get("Usuario", ""), fila.get("Estado", ""), fila.get("ID_Usuario", "")]
            for fila in filas
        ]
        await self.sheets_call(hoja.clear)
        await self.sheets_call(hoja.update, values=values, range_name=f"A1:F{len(values)}")

    def es_coordinador_o_admin(self, interaction: discord.Interaction) -> bool:
        roles_ids = [r.id for r in interaction.user.roles]
        return COORDINADOR_ROLE_ID in roles_ids or interaction.user.guild_permissions.administrator

    def puede_gestionar_serie(self, interaction: discord.Interaction, serie_info: dict) -> bool:
        admin_id = str(serie_info.get("Admin_ID", "")).strip()
        return str(interaction.user.id) == str(ITSUKI_ID) or str(interaction.user.id) == admin_id

    def normalizar_categoria(self, valor) -> str:
        texto = str(valor or "").strip()
        if texto in {"15", "+15"}:
            return "+15"
        if texto in {"19", "+19"}:
            return "+19"
        return texto

    def normalizar_idioma(self, valor) -> str:
        texto = str(valor or "").strip().lower()
        equivalencias = {
            "ingles": "Ingles",
            "inglés": "Ingles",
            "coreano": "Coreano",
            "ambos": "Ambos",
        }
        return equivalencias.get(texto, str(valor or "").strip())

    def obtener_admin_responsable(self, serie_info, guild: discord.Guild = None) -> str:
        admin_id = str(serie_info.get("Admin_ID", "")).strip()
        admin_nombre = str(serie_info.get("Admin_Nombre", "")).strip()
        if not admin_id:
            return admin_nombre

        if guild:
            miembro = guild.get_member(int(admin_id))
            if miembro:
                return miembro.mention

        return admin_nombre or f"Admin ({admin_id})"

    def obtener_lock_asignarme(self, tarea: str, categoria: str, idioma: str) -> asyncio.Lock:
        key = (tarea, categoria, idioma or "cualquiera")
        if key not in self.asignarme_locks:
            self.asignarme_locks[key] = asyncio.Lock()
        return self.asignarme_locks[key]

    # ==========================================
    #     HELPERS DE GOOGLE SHEETS
    # ==========================================
    async def obtener_hoja_series(self):
        try:
            return await self.sheets_call(self.bot.spreadsheet.worksheet, "Series")
        except Exception:
            hoja = await self.sheets_call(
                self.bot.spreadsheet.add_worksheet,
                title="Series",
                rows=100,
                cols=9
            )
            encabezados = ["Nombre", "Canal_ID", "Link_Drive", "Folder_ID",
                          "Categoria", "Idioma", "Fecha_Agregada", "Admin_ID", "Admin_Nombre"]
            await self.sheets_call(hoja.append_row, encabezados)
            return hoja

    async def refrescar_series_db_desde_sheet(self):
        hoja_series = await self.obtener_hoja_series()
        series = await self.sheets_call(hoja_series.get_all_records)
        await asyncio.to_thread(replace_series, series)
        return series

    async def obtener_info_serie(self, nombre_serie: str):
        return await self.db_get_serie_by_name(nombre_serie)

    def resolver_titulo_responsable(self, admin_id: str, admin_nombre: str) -> str:
        admin_id = str(admin_id or "").strip()
        admin_nombre = str(admin_nombre or "").strip()
        return OWNER_SHEET_TITLES.get(admin_id) or admin_nombre or "Sin responsable"

    async def obtener_hoja_responsable(self, nombre_responsable: str):
        titulo = str(nombre_responsable or "Sin responsable").strip() or "Sin responsable"
        try:
            return await self.sheets_call(self.bot.spreadsheet.worksheet, titulo)
        except Exception:
            hojas = await self.sheets_call(self.bot.spreadsheet.worksheets)
            existente = next((ws for ws in hojas if str(ws.title).strip().lower() == titulo.lower()), None)
            if existente:
                return existente
            hoja = await self.sheets_call(
                self.bot.spreadsheet.add_worksheet,
                title=titulo,
                rows=500,
                cols=BLOCK_WIDTH
            )
            return hoja

    async def obtener_bloque_serie(self, nombre_serie: str, crear_si_no_existe: bool = True):
        serie_info = await self.obtener_info_serie(nombre_serie)
        if not serie_info:
            return None, None, None

        nombre_responsable = self.resolver_titulo_responsable(
            serie_info.get("Admin_ID", ""),
            serie_info.get("Admin_Nombre", ""),
        )
        hoja = await self.obtener_hoja_responsable(nombre_responsable)
        valores = await self.sheets_call(hoja.get_all_values)
        fila_titulos = valores[0] if valores else []

        for idx, titulo in enumerate(fila_titulos, start=1):
            if self.series_coinciden(titulo, nombre_serie):
                return hoja, idx, serie_info

        if not crear_si_no_existe:
            return hoja, None, serie_info

        columnas_ocupadas = [idx for idx, titulo in enumerate(fila_titulos, start=1) if str(titulo).strip()]
        start_col = (max(columnas_ocupadas) + BLOCK_WIDTH) if columnas_ocupadas else 1

        end_needed = start_col + len(SERIE_HEADERS) - 1
        if hoja.col_count < end_needed:
            await self.sheets_call(hoja.resize, rows=hoja.row_count, cols=end_needed)

        bloque = [
            [serie_info["Nombre"]],
            [f"Categoria: {serie_info.get('Categoria', '')} | Idioma: {serie_info.get('Idioma', '')}"],
            [f"Canal: {serie_info.get('Canal_ID', '')} | Folder: {serie_info.get('Folder_ID', '')}"],
            SERIE_HEADERS,
        ]
        ancho = len(SERIE_HEADERS)
        padded = [fila + [""] * (ancho - len(fila)) for fila in bloque]
        start_a1 = gspread.utils.rowcol_to_a1(1, start_col)
        end_a1 = gspread.utils.rowcol_to_a1(len(padded), start_col + ancho - 1)
        await self.sheets_call(hoja.update, values=padded, range_name=f"{start_a1}:{end_a1}")
        return hoja, start_col, serie_info

    async def asegurar_bloque_serie(self, nombre_serie: str):
        hoja, start_col, serie_info = await self.obtener_bloque_serie(nombre_serie, crear_si_no_existe=True)
        if not hoja or not start_col or not serie_info:
            raise RuntimeError(f"No se pudo crear el bloque para {nombre_serie}.")

        valores = await self.sheets_call(hoja.get_all_values)
        fila_titulos = valores[0] if valores else []
        idx = start_col - 1
        titulo = fila_titulos[idx] if idx < len(fila_titulos) else ""
        if not self.series_coinciden(titulo, nombre_serie):
            raise RuntimeError(f"El bloque de {nombre_serie} no quedó escrito correctamente.")
        return hoja, start_col, serie_info

    async def leer_tabla_serie(self, nombre_serie: str):
        hoja, start_col, _ = await self.obtener_bloque_serie(nombre_serie, crear_si_no_existe=False)
        if not hoja or not start_col:
            return []

        valores = await self.sheets_call(hoja.get_all_values)
        filas = []
        for row_idx in range(4, len(valores)):
            fila = valores[row_idx]
            datos = []
            for offset in range(len(SERIE_HEADERS)):
                col_idx = start_col - 1 + offset
                datos.append(fila[col_idx] if col_idx < len(fila) else "")
            if not str(datos[0]).strip():
                break
            filas.append(dict(zip(SERIE_HEADERS, datos)))
        return filas

    async def escribir_tabla_serie(self, nombre_serie: str, filas: list):
        hoja, start_col, serie_info = await self.obtener_bloque_serie(nombre_serie, crear_si_no_existe=True)
        if not hoja or not start_col or not serie_info:
            return False

        bloque = [
            [serie_info["Nombre"]],
            [f"Categoria: {serie_info.get('Categoria', '')} | Idioma: {serie_info.get('Idioma', '')}"],
            [f"Canal: {serie_info.get('Canal_ID', '')} | Folder: {serie_info.get('Folder_ID', '')}"],
            SERIE_HEADERS,
        ]

        for fila in filas:
            bloque.append([
                str(fila.get("Cap", "")).strip(),
                str(fila.get("Idioma", "")).strip(),
                str(fila.get("RAW", "❌")).strip() or "❌",
                str(fila.get("Clean", "❌")).strip() or "❌",
                str(fila.get("Traduccion", "❌")).strip() or "❌",
                str(fila.get("Edicion", "❌")).strip() or "❌",
                str(fila.get("Recorte", "❌")).strip() or "❌",
                str(fila.get("Subido_Web", "❌")).strip() or "❌",
                str(fila.get("Fecha_RAW", "")).strip(),
            ])

        ancho = len(SERIE_HEADERS)
        padded = [fila + [""] * (ancho - len(fila)) for fila in bloque]
        start_a1 = gspread.utils.rowcol_to_a1(1, start_col)
        end_clear = gspread.utils.rowcol_to_a1(hoja.row_count, start_col + ancho - 1)
        end_a1 = gspread.utils.rowcol_to_a1(len(padded), start_col + ancho - 1)
        await self.sheets_call(hoja.batch_clear, [f"{start_a1}:{end_clear}"])
        await self.sheets_call(hoja.update, values=padded, range_name=f"{start_a1}:{end_a1}")
        return True

    async def actualizar_estado_tarea_serie(self, nombre_serie: str, capitulo: str, tarea: str, valor: str):
        filas = await self.leer_tabla_serie(nombre_serie)
        if not filas:
            return False

        columna = {
            "Clean": "Clean",
            "Traduccion": "Traduccion",
            "Edicion": "Edicion",
        }.get(tarea)

        if not columna:
            return False

        actualizado = False
        for fila in filas:
            if self.caps_coinciden(fila.get("Cap", ""), capitulo):
                fila[columna] = valor
                actualizado = True
                break

        if actualizado:
            return await self.escribir_tabla_serie(nombre_serie, filas)
        return False

    def extraer_folder_id(self, link: str) -> str:
        patrones = [
            r'folders/([a-zA-Z0-9_-]+)',
            r'id=([a-zA-Z0-9_-]+)',
        ]
        for patron in patrones:
            match = re.search(patron, link)
            if match:
                return match.group(1)
        return None

    def normalizar_nombre_drive(self, nombre: str) -> str:
        texto = unicodedata.normalize("NFKD", str(nombre or ""))
        texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
        return texto.lower().strip()

    def carpeta_drive_coincide(self, etapa: str, nombre_carpeta: str) -> bool:
        nombre_normalizado = self.normalizar_nombre_drive(nombre_carpeta)
        aliases = {
            "RAW": ["1_raw"],
            "Clean": ["2_clrd", "2_clean"],
            "Traduccion": ["3_traduccion", "3_tl", "tl"],
            "Edicion": ["4_type", "4_ts", "ts"],
            "Recorte": ["5_recortes"],
        }
        return any(alias in nombre_normalizado for alias in aliases.get(etapa, []))

    def extraer_numero_cap(self, nombre: str) -> str:
        """Extrae el número de capítulo de un nombre de archivo o carpeta
        Ejemplos: Chapter_40-5 -> 40-5, Traduccion_34 -> 34, 15 -> 15
        """
        nombre = re.sub(r'\.[a-zA-Z0-9]+$', '', str(nombre)).strip()
        nombre_normalizado = nombre.lower().replace('_', ' ')

        patrones_prioritarios = [
            r'(?:cap(?:itulo)?|chapter|ch|episodio|ep)\s*[:#-]?\s*(\d+(?:[.-]\d+)?)',
            r'(?:traduccion|traducción|trad|clean|clrd|edicion|edición|type|recorte|raw)\s*[:#-]?\s*(\d+(?:[.-]\d+)?)',
        ]

        for patron in patrones_prioritarios:
            match = re.search(patron, nombre_normalizado, re.IGNORECASE)
            if match:
                return match.group(1).replace('.', '-')

        match = re.search(r'(\d+(?:[.-]\d+)?)', nombre_normalizado)
        return match.group(1).replace('.', '-') if match else nombre.strip()

    def series_coinciden(self, serie_a: str, serie_b: str) -> bool:
        return str(serie_a or "").strip().lower() == str(serie_b or "").strip().lower()

    def caps_coinciden(self, cap_a: str, cap_b: str) -> bool:
        return self.extraer_numero_cap(str(cap_a)) == self.extraer_numero_cap(str(cap_b))

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

    def cap_esta_terminado(self, fila: dict, columna: str) -> bool:
        return str(fila.get(columna, "")).strip() == "✅"

    def icono_estado(self, fila: dict, columna: str) -> str:
        valor = str(fila.get(columna, "")).strip()
        if valor in {"✅", "⏳", "❌"}:
            return valor
        return "❌"

    def fila_asignacion_coincide(self, fila, proyecto: str, capitulo: str, tarea: str = None, estado: str = None) -> bool:
        if not self.series_coinciden(fila.get('Proyecto', ''), proyecto):
            return False
        if not self.caps_coinciden(fila.get('Capítulo', ''), capitulo):
            return False
        if tarea is not None and self.normalizar_tarea_asignacion(fila.get('Tarea')) != self.normalizar_tarea_asignacion(tarea):
            return False
        if estado is not None and fila.get('Estado') != estado:
            return False
        return True

    def ordenar_cap(self, cap: str):
        """Función para ordenar caps correctamente: 14, 15, 40, 40-5, 41"""
        partes = cap.split('-')
        try:
            return (int(partes[0]), int(partes[1]) if len(partes) > 1 else 0)
        except:
            return (0, 0)

    def obtener_drive_service(self):
        """Crea y retorna el servicio de Google Drive autenticado"""
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        creds = service_account.Credentials.from_service_account_file(
            "credentials.json",
            scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
        return build('drive', 'v3', credentials=creds)

    async def listar_subcarpetas_drive(self, folder_id: str) -> list:
        """Lista las CARPETAS dentro de una carpeta de Drive"""
        try:
            service = self.obtener_drive_service()
            resultados = await asyncio.to_thread(
                lambda: service.files().list(
                    q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                    fields="files(id, name)",
                    orderBy="name"
                ).execute()
            )
            return resultados.get('files', [])
        except Exception as e:
            print(f"Error al listar carpetas Drive: {e}")
            return []

    async def listar_archivos_drive(self, folder_id: str) -> list:
        """Lista los ARCHIVOS (no carpetas) dentro de una carpeta de Drive"""
        try:
            service = self.obtener_drive_service()
            resultados = await asyncio.to_thread(
                lambda: service.files().list(
                    q=f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed=false",
                    fields="files(id, name)",
                    orderBy="name"
                ).execute()
            )
            return resultados.get('files', [])
        except Exception as e:
            print(f"Error al listar archivos Drive: {e}")
            return []

    async def obtener_caps_por_etapa_desde_drive(self, folder_id_principal: str):
        """Lee el estado real de una serie directamente desde Drive."""
        caps_por_etapa = {etapa: set() for etapa in CARPETAS_DRIVE}

        carpetas_principales = await self.listar_subcarpetas_drive(folder_id_principal)

        for etapa, nombre_carpeta in CARPETAS_DRIVE.items():
            folder_etapa = None
            for carpeta in carpetas_principales:
                if self.carpeta_drive_coincide(etapa, carpeta['name']):
                    folder_etapa = carpeta['id']
                    break

            if not folder_etapa:
                continue

            if etapa == "Traduccion":
                archivos = await self.listar_archivos_drive(folder_etapa)
                caps_por_etapa[etapa] = {
                    self.extraer_numero_cap(a['name'])
                    for a in archivos
                    if self.extraer_numero_cap(a['name'])
                }
            else:
                subcarpetas = await self.listar_subcarpetas_drive(folder_etapa)
                caps_por_etapa[etapa] = {
                    self.extraer_numero_cap(c['name'])
                    for c in subcarpetas
                    if self.extraer_numero_cap(c['name'])
                }

        return caps_por_etapa

    async def actualizar_serie_desde_drive(self, nombre_serie: str, folder_id_principal: str, incluir_filas: bool = False):
        """Actualiza el Excel con los caps encontrados en el Drive"""
        try:
            caps_por_etapa = await self.obtener_caps_por_etapa_desde_drive(folder_id_principal)

            # Basarse SOLO en RAW para saber qué caps existen
            todos_caps = set(caps_por_etapa.get("RAW", []))

            if not todos_caps:
                return (0, []) if incluir_filas else 0

            datos = await self.leer_tabla_serie(nombre_serie)
            existentes = {}

            for fila in datos:
                cap_original = str(fila.get('Cap', '')).strip()
                if not cap_original:
                    continue
                cap_normalizado = self.extraer_numero_cap(cap_original)
                if cap_normalizado not in existentes:
                    existentes[cap_normalizado] = {
                        "Cap": cap_normalizado,
                        "Idioma": str(fila.get("Idioma", "")).strip(),
                        "RAW": str(fila.get("RAW", "❌")).strip() or "❌",
                        "Clean": str(fila.get("Clean", "❌")).strip() or "❌",
                        "Traduccion": str(fila.get("Traduccion", "❌")).strip() or "❌",
                        "Edicion": str(fila.get("Edicion", "❌")).strip() or "❌",
                        "Recorte": str(fila.get("Recorte", "❌")).strip() or "❌",
                        "Subido_Web": str(fila.get("Subido_Web", "❌")).strip() or "❌",
                        "Fecha_RAW": str(fila.get("Fecha_RAW", "")).strip(),
                    }

            caps_nuevos = sum(1 for cap in todos_caps if cap not in existentes)
            filas_finales = []

            for cap in sorted(todos_caps, key=lambda x: self.ordenar_cap(x)):
                actual = existentes.get(cap, {})
                estado_clean_actual = actual.get("Clean", "❌")
                estado_trad_actual = actual.get("Traduccion", "❌")
                estado_edicion_actual = actual.get("Edicion", "❌")
                estado_recorte_actual = actual.get("Recorte", "❌")
                filas_finales.append({
                    "Cap": cap,
                    "Idioma": actual.get("Idioma", ""),
                    "RAW": "✅",
                    "Clean": "✅" if cap in caps_por_etapa.get("Clean", set()) or estado_clean_actual == "✅" else ("⏳" if estado_clean_actual == "⏳" else "❌"),
                    "Traduccion": "✅" if cap in caps_por_etapa.get("Traduccion", set()) or estado_trad_actual == "✅" else ("⏳" if estado_trad_actual == "⏳" else "❌"),
                    "Edicion": "✅" if cap in caps_por_etapa.get("Edicion", set()) or estado_edicion_actual == "✅" else ("⏳" if estado_edicion_actual == "⏳" else "❌"),
                    "Recorte": "✅" if cap in caps_por_etapa.get("Recorte", set()) or estado_recorte_actual == "✅" else "❌",
                    "Subido_Web": "✅" if actual.get("Subido_Web") == "✅" else "❌",
                    "Fecha_RAW": actual.get("Fecha_RAW") or datetime.now().strftime("%Y-%m-%d"),
                })

            await self.escribir_tabla_serie(nombre_serie, filas_finales)
            if incluir_filas:
                return caps_nuevos, filas_finales
            return caps_nuevos

        except Exception as e:
            print(f"Error actualizando serie desde Drive: {e}")
            return (-1, []) if incluir_filas else -1

    # ==========================================
    #         TAREAS AUTOMÁTICAS
    # ==========================================
    @tasks.loop(hours=12)
    async def revision_automatica(self):
        canal_coord = self.bot.get_channel(CANAL_COORDINADORES_ID)
        if not canal_coord:
            return

        try:
            series = await self.db_list_series()

            for serie in series:
                nombre = serie['Nombre']
                folder_id = serie.get('Folder_ID', '')
                canal_id = serie.get('Canal_ID', '')

                if not nombre or not folder_id:
                    continue

                try:
                    _, datos = await self.actualizar_serie_desde_drive(nombre, folder_id, incluir_filas=True)
                except gspread.exceptions.APIError as e:
                    if "429" in str(e):
                        print(f"Revision automatica pausada por cuota en {nombre}: {e}")
                        await asyncio.sleep(20)
                        continue
                    raise

                for fila in datos:
                    cap = fila.get('Cap', '')
                    if not cap:
                        continue

                canal_serie = self.bot.get_channel(int(canal_id)) if canal_id else None
                if canal_serie:
                    for fila in datos:
                        if self.cap_esta_terminado(fila, 'Recorte') and not self.cap_esta_terminado(fila, 'Subido_Web'):
                            cap = fila.get('Cap', '')
                            embed = discord.Embed(
                                title="✂️ ¡Capítulo listo para subir!",
                                description=f"El **Cap {cap}** de **{nombre}** ya tiene recorte y está listo para subir a la web.",
                                color=discord.Color.green()
                            )
                            embed.set_footer(text="Bloom Scans • Sistema de producción")
                            menciones = self.obtener_admin_responsable(serie, canal_serie.guild)
                            await canal_serie.send(content=menciones, embed=embed)

                await asyncio.sleep(2)

        except Exception as e:
            print(f"Error en revisión automática: {e}")

    @revision_automatica.before_loop
    async def before_revision(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=168)
    async def reporte_semanal(self):
        if datetime.now().weekday() != 0:
            return

        canal_coord = self.bot.get_channel(CANAL_COORDINADORES_ID)
        if not canal_coord:
            return

        try:
            series = await self.db_list_series()

            embed = discord.Embed(
                title="📊 Reporte Semanal de Producción",
                description=f"Semana del {(datetime.now() - timedelta(days=7)).strftime('%d/%m')} al {datetime.now().strftime('%d/%m/%Y')}",
                color=0xffb6c1
            )

            for serie in series:
                nombre = serie['Nombre']
                if not nombre:
                    continue

                datos = await self.leer_tabla_serie(nombre)

                total = len(datos)
                listos = sum(1 for f in datos if f.get('Subido_Web') == '✅')
                en_proceso = total - listos
                atascados_clean = sum(1 for f in datos if f.get('RAW') == '✅' and f.get('Clean') == '❌' and f.get('Subido_Web') != '✅')
                atascados_traduc = sum(1 for f in datos if f.get('RAW') == '✅' and f.get('Traduccion') == '❌' and f.get('Subido_Web') != '✅')
                atascados_edicion = sum(1 for f in datos if f.get('Clean') == '✅' and f.get('Traduccion') == '✅' and f.get('Edicion') == '❌' and f.get('Subido_Web') != '✅')

                info = f"📁 En proceso: **{en_proceso}** | ✅ Subidos: **{listos}**\n"
                if atascados_clean: info += f"⚠️ Atascados en Clean: **{atascados_clean}**\n"
                if atascados_traduc: info += f"⚠️ Atascados en Traducción: **{atascados_traduc}**\n"
                if atascados_edicion: info += f"⚠️ Atascados en Edición: **{atascados_edicion}**\n"

                embed.add_field(name=f"📚 {nombre}", value=info, inline=False)

            embed.set_footer(text="Bloom Scans • Reporte automático semanal")
            await canal_coord.send(embed=embed)

        except Exception as e:
            print(f"Error en reporte semanal: {e}")

    @reporte_semanal.before_loop
    async def before_reporte(self):
        await self.bot.wait_until_ready()

    # ==========================================
    #         COMANDOS
    # ==========================================

    @app_commands.command(name="agregar_serie", description="ADMIN: Agrega una nueva serie al sistema de producción")
    @app_commands.choices(
        categoria=[
            app_commands.Choice(name="+15", value="+15"),
            app_commands.Choice(name="+19", value="+19"),
            app_commands.Choice(name="BL", value="BL"),
        ],
        idioma=[
            app_commands.Choice(name="Inglés", value="Ingles"),
            app_commands.Choice(name="Coreano", value="Coreano"),
            app_commands.Choice(name="Ambos", value="Ambos"),
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def agregar_serie(self, interaction: discord.Interaction, canal: discord.TextChannel, link_drive: str, categoria: app_commands.Choice[str], idioma: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)

        try:
            folder_id = self.extraer_folder_id(link_drive)
            if not folder_id:
                await interaction.followup.send("❌ No pude extraer el ID del Drive. Verifica el link.", ephemeral=True)
                return

            nombre_serie = canal.name

            series_existentes = await self.refrescar_series_db_desde_sheet()

            for s in series_existentes:
                if str(s.get('Canal_ID')) == str(canal.id):
                    await interaction.followup.send(f"⚠️ La serie **{nombre_serie}** ya está registrada.", ephemeral=True)
                    return

            nueva_fila = [
                nombre_serie,
                str(canal.id),
                link_drive,
                folder_id,
                categoria.value,
                idioma.value,
                datetime.now().strftime("%Y-%m-%d"),
                str(interaction.user.id),
                interaction.user.name
            ]
            await self.db_upsert_series({
                "Nombre": nombre_serie,
                "Canal_ID": str(canal.id),
                "Link_Drive": link_drive,
                "Folder_ID": folder_id,
                "Categoria": categoria.value,
                "Idioma": idioma.value,
                "Fecha_Agregada": datetime.now().strftime("%Y-%m-%d"),
                "Admin_ID": str(interaction.user.id),
                "Admin_Nombre": interaction.user.name,
            })
            hoja_series = await self.obtener_hoja_series()
            await self.sheets_call(hoja_series.append_row, nueva_fila)
            await self.asegurar_bloque_serie(nombre_serie)

            caps_encontrados = await self.actualizar_serie_desde_drive(nombre_serie, folder_id)

            embed = discord.Embed(title="✅ Serie Agregada al Sistema", color=0xffb6c1)
            embed.add_field(name="📚 Serie", value=canal.mention, inline=True)
            embed.add_field(name="🏷️ Categoría", value=categoria.value, inline=True)
            embed.add_field(name="🌐 Idioma", value=idioma.value, inline=True)
            embed.add_field(name="👤 Admin a cargo", value=interaction.user.mention, inline=True)
            embed.add_field(name="📁 Caps encontrados en Drive", value=f"**{caps_encontrados}** caps cargados automáticamente", inline=False)
            embed.add_field(name="📋 Nota", value="Los caps que ya estaban listos antes de agregar la serie, márcalos manualmente con ✅ en el Excel.", inline=False)
            embed.set_footer(text="Bloom Scans • Sistema de producción")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            print(f"Error en agregar_serie: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="crear_tabla_serie", description="ADMIN DUEÑO/ITSUKI: Crea el bloque de una serie ya registrada si faltó")
    async def crear_tabla_serie(self, interaction: discord.Interaction, serie: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)

        try:
            await self.refrescar_series_db_desde_sheet()
            serie_info = await self.db_get_serie_by_channel(serie.id)
            if not serie_info:
                await interaction.followup.send("❌ Esa serie no está registrada en `Series`.", ephemeral=True)
                return

            if not self.puede_gestionar_serie(interaction, serie_info):
                await interaction.followup.send("❌ Solo el admin a cargo de la serie o Itsuki puede usar este comando.", ephemeral=True)
                return

            hoja, start_col, _ = await self.obtener_bloque_serie(serie_info["Nombre"], crear_si_no_existe=False)
            if hoja and start_col:
                await interaction.followup.send("⚠️ Esa serie ya tiene bloque en la hoja del responsable.", ephemeral=True)
                return

            _, start_col, _ = await self.asegurar_bloque_serie(serie_info["Nombre"])
            caps_encontrados = await self.actualizar_serie_desde_drive(serie_info["Nombre"], serie_info.get("Folder_ID", ""))

            embed = discord.Embed(title="✅ Tabla de Serie Creada", color=discord.Color.green())
            embed.add_field(name="Serie", value=serie.mention, inline=True)
            embed.add_field(name="Hoja", value=self.resolver_titulo_responsable(serie_info.get("Admin_ID", ""), serie_info.get("Admin_Nombre", "")), inline=True)
            embed.add_field(name="Inicio del bloque", value=f"Columna {start_col}", inline=True)
            embed.add_field(name="Caps detectados", value=str(caps_encontrados), inline=True)
            embed.set_footer(text="Bloom Scans • Reparación de estructura")
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"Error en crear_tabla_serie: {e}")
            await interaction.followup.send(f"❌ Error al crear la tabla: {e}", ephemeral=True)

    @app_commands.command(name="estado_serie", description="Ver el estado de producción de una serie")
    async def estado_serie(self, interaction: discord.Interaction, serie: discord.TextChannel):
        if not self.es_coordinador_o_admin(interaction):
            await interaction.response.send_message("❌ No tienes permisos.", ephemeral=True)
            return

        await interaction.response.defer()

        try:
            serie_info = await self.db_get_serie_by_channel(serie.id)

            if not serie_info:
                await interaction.followup.send("❌ Esta serie no está registrada. Usa `/agregar_serie` primero.", ephemeral=True)
                return

            nombre_serie = serie_info['Nombre']
            datos = await self.leer_tabla_serie(nombre_serie)

            caps_activos = [f for f in datos if f.get('Subido_Web') != '✅' and f.get('Cap')]

            if not caps_activos:
                await interaction.followup.send(f"✅ ¡Todos los caps de **{nombre_serie}** están subidos a la web!")
                return

            lineas = []

            for fila in caps_activos:
                cap = fila.get('Cap', '')
                raw = self.icono_estado(fila, 'RAW')
                clean = self.icono_estado(fila, 'Clean')
                traduc = self.icono_estado(fila, 'Traduccion')
                edicion = self.icono_estado(fila, 'Edicion')
                recorte = self.icono_estado(fila, 'Recorte')

                lineas.append(f"Cap {cap:<6} │ RAW {raw} │ Clean {clean} │ Traduc {traduc} │ Edición {edicion} │ Recorte {recorte}")

            tabla = "```\n"
            tabla += f"Serie: {nombre_serie}\n"
            tabla += "━" * 65 + "\n"
            tabla += "Cap    │ RAW  │ Clean │ Traduc │ Edición │ Recorte\n"
            tabla += "━" * 65 + "\n"
            tabla += "\n".join(lineas[:20])
            tabla += "\n" + "━" * 65
            tabla += "\n```"

            embed = discord.Embed(
                title=f"📋 Estado de Producción — {nombre_serie}",
                description=tabla,
                color=0xffb6c1
            )

            if len(caps_activos) > 20:
                embed.set_footer(text=f"Mostrando 20 de {len(caps_activos)} caps activos • Bloom Scans")
            else:
                embed.set_footer(text="Bloom Scans • Sistema de producción")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"Error en estado_serie: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="actualizar_drive", description="Fuerza la actualización del Drive de una serie ahora mismo")
    async def actualizar_drive(self, interaction: discord.Interaction, serie: discord.TextChannel):
        if not self.es_coordinador_o_admin(interaction):
            await interaction.response.send_message("❌ No tienes permisos.", ephemeral=True)
            return

        await interaction.response.defer()

        try:
            serie_info = await self.db_get_serie_by_channel(serie.id)

            if not serie_info:
                await interaction.followup.send("❌ Esta serie no está registrada.", ephemeral=True)
                return

            caps = await self.actualizar_serie_desde_drive(serie_info['Nombre'], serie_info['Folder_ID'])

            embed = discord.Embed(
                title="🔄 Drive Actualizado",
                description=f"Se actualizó **{serie_info['Nombre']}** desde el Drive.\n📁 Caps nuevos encontrados: **{caps}**",
                color=discord.Color.green()
            )
            embed.set_footer(text="Bloom Scans • Sistema de producción")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="asignarme", description="Asígnate automáticamente a un capítulo disponible")
    @app_commands.choices(
        tarea=[
            app_commands.Choice(name="🧹 Clean", value="Clean"),
            app_commands.Choice(name="📝 Traducción", value="Traduccion"),
            app_commands.Choice(name="✏️ Edición", value="Edicion"),
        ],
        categoria=[
            app_commands.Choice(name="+15", value="+15"),
            app_commands.Choice(name="+19", value="+19"),
            app_commands.Choice(name="BL", value="BL"),
        ],
        idioma=[
            app_commands.Choice(name="Inglés", value="Ingles"),
            app_commands.Choice(name="Coreano", value="Coreano"),
            app_commands.Choice(name="Sin preferencia", value="cualquiera"),
        ]
    )
    async def asignarme(self, interaction: discord.Interaction, tarea: app_commands.Choice[str], categoria: app_commands.Choice[str], idioma: app_commands.Choice[str] = None):
        await interaction.response.defer()

        try:
            idioma_lock = idioma.value if idioma else "cualquiera"
            lock = self.obtener_lock_asignarme(tarea.value, categoria.value, idioma_lock)

            async with lock:
                series = await self.db_list_series()
                asig_datos = await self.db_list_asignaciones()

                series_candidatas = []
                for s in series:
                    if self.normalizar_categoria(s.get('Categoria')) != categoria.value:
                        continue
                    if idioma and idioma.value != "cualquiera":
                        if self.normalizar_idioma(s.get('Idioma')) not in [idioma.value, "Ambos"]:
                            continue
                    series_candidatas.append(s)

                if not series_candidatas:
                    await interaction.followup.send(f"❌ No hay series disponibles con categoría **{categoria.value}**.", ephemeral=True)
                    return

                random.shuffle(series_candidatas)

                cap_encontrado = None
                serie_encontrada = None

                columnas_tarea = {
                    "Clean": "Clean",
                    "Traduccion": "Traduccion",
                    "Edicion": "Edicion"
                }

                for serie in series_candidatas:
                    nombre = serie['Nombre']
                    folder_id = serie.get('Folder_ID', '')
                    caps_drive = None
                    if folder_id:
                        _, datos = await self.actualizar_serie_desde_drive(nombre, folder_id, incluir_filas=True)
                        caps_drive = await self.obtener_caps_por_etapa_desde_drive(folder_id)
                    else:
                        datos = await self.leer_tabla_serie(nombre)

                    for fila in datos:
                        cap = fila.get('Cap', '')
                        if not cap or self.cap_esta_terminado(fila, 'Subido_Web'):
                            continue
                        if not self.cap_esta_terminado(fila, 'RAW'):
                            continue

                        cap_normalizado = self.extraer_numero_cap(str(cap))
                        if caps_drive is not None and cap_normalizado not in caps_drive.get("RAW", set()):
                            continue

                        col_tarea = columnas_tarea[tarea.value]
                        if self.cap_esta_terminado(fila, col_tarea):
                            continue

                        if caps_drive is not None and cap_normalizado in caps_drive.get(tarea.value, set()):
                            continue

                        if tarea.value == "Edicion":
                            clean_ok = self.cap_esta_terminado(fila, 'Clean')
                            traduc_ok = self.cap_esta_terminado(fila, 'Traduccion')
                            if caps_drive is not None:
                                clean_ok = clean_ok or cap_normalizado in caps_drive.get("Clean", set())
                                traduc_ok = traduc_ok or cap_normalizado in caps_drive.get("Traduccion", set())
                            if not clean_ok or not traduc_ok:
                                continue

                        ya_asignado = any(
                            self.fila_asignacion_coincide(a, nombre, cap_normalizado, tarea=tarea.value, estado="En Proceso")
                            for a in asig_datos
                        )

                        if not ya_asignado:
                            cap_encontrado = cap
                            serie_encontrada = serie
                            break

                    if cap_encontrado:
                        break

                if not cap_encontrado:
                    await interaction.followup.send(
                        f"😔 No hay caps disponibles para **{tarea.name}** en la categoría **{categoria.value}** en este momento.",
                        ephemeral=True
                    )
                    return

                cap_normalizado = self.extraer_numero_cap(str(cap_encontrado))
                asig_datos = await self.db_list_asignaciones()
                sigue_libre = not any(
                    self.fila_asignacion_coincide(a, serie_encontrada['Nombre'], cap_normalizado, tarea=tarea.value, estado="En Proceso")
                    for a in asig_datos
                )

                if not sigue_libre:
                    await interaction.followup.send(
                        "⚠️ Ese capítulo se tomó justo antes que tú. Intenta de nuevo con `/asignarme`.",
                        ephemeral=True
                    )
                    return

                nueva_fila = [
                    serie_encontrada['Nombre'],
                    cap_encontrado,
                    self.normalizar_tarea_asignacion(tarea.value),
                    interaction.user.name,
                    "En Proceso",
                    str(interaction.user.id)
                ]
                await self.db_add_asignacion(
                    serie_encontrada['Nombre'],
                    cap_encontrado,
                    tarea.value,
                    interaction.user.name,
                    "En Proceso",
                    str(interaction.user.id)
                )
                await self.sync_asignaciones_sheet()
                await self.actualizar_estado_tarea_serie(serie_encontrada['Nombre'], cap_encontrado, tarea.value, "⏳")

            canal_serie = self.bot.get_channel(int(serie_encontrada['Canal_ID']))
            if canal_serie:
                try:
                    await canal_serie.set_permissions(
                        interaction.user,
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        attach_files=True,
                        embed_links=True
                    )
                except:
                    pass

                embed_serie = discord.Embed(
                    title="🌸 Nueva Autoasignación",
                    description=f"¡{interaction.user.mention} se ha asignado a un nuevo capítulo!",
                    color=0xffb6c1
                )
                embed_serie.add_field(name="🛠️ Tarea", value=tarea.name, inline=True)
                embed_serie.add_field(name="📌 Capítulo", value=f"`{cap_encontrado}`", inline=True)
                embed_serie.set_footer(text="Bloom Scans • Autoasignación")
                await canal_serie.send(content=interaction.user.mention, embed=embed_serie)

            canal_asig = self.bot.get_channel(CANAL_ASIGNACIONES_LOG)
            if canal_asig:
                embed_log = discord.Embed(title="✨ Asignación Registrada", color=0x3498db)
                embed_log.add_field(
                    name="Proyecto",
                    value=canal_serie.mention if canal_serie else serie_encontrada['Nombre'],
                    inline=True
                )
                embed_log.add_field(name="Capítulo", value=f"`{cap_encontrado}`", inline=True)
                embed_log.add_field(name="Staff", value=interaction.user.mention, inline=True)
                embed_log.add_field(name="Tarea", value=tarea.name, inline=False)
                embed_log.set_footer(text=f"ID:{interaction.user.id} | Cap:{cap_encontrado}")
                await canal_asig.send(embed=embed_log)

            embed = discord.Embed(title="✅ ¡Te has asignado exitosamente!", color=discord.Color.green())
            embed.add_field(name="📚 Serie", value=serie_encontrada['Nombre'], inline=True)
            embed.add_field(name="📌 Capítulo", value=f"`{cap_encontrado}`", inline=True)
            embed.add_field(name="🛠️ Tarea", value=tarea.name, inline=True)
            embed.set_footer(text="Cuando termines usa /terminado • Bloom Scans")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"Error en asignarme: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="helps_coordinador", description="Guía de comandos para coordinadores")
    async def helps_coordinador(self, interaction: discord.Interaction):
        if not self.es_coordinador_o_admin(interaction):
            await interaction.response.send_message("❌ No tienes permisos.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎯 Panel de Coordinación — Bloom Scans",
            description="Comandos disponibles para coordinadores y administradores:",
            color=0xffb6c1
        )
        embed.add_field(name="📋 `/estado_serie`", value="Ver el estado de producción de una serie por capítulos.", inline=False)
        embed.add_field(name="🔄 `/actualizar_drive`", value="Fuerza la actualización del Drive de una serie ahora mismo.", inline=False)
        embed.add_field(name="📊 Reporte semanal", value="Cada lunes el bot te manda automáticamente el resumen de producción.", inline=False)
        embed.set_footer(text="Bloom Scans • Coordinación y Producción")
        await interaction.response.send_message(embed=embed, ephemeral=False)


async def setup(bot):
    await bot.add_cog(CoordinadorCog(bot))
