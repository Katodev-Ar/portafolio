# -*- coding: utf-8 -*-
import discord
from discord.ext import commands
import os
import asyncio
import gspread
import traceback
from dotenv import load_dotenv
from database import setup_db, replace_series, replace_asignaciones, replace_registros

load_dotenv()

class BloomBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="/", intents=intents)
        self.gc = None
        self.spreadsheet = None

    async def sincronizar_sqlite_desde_sheets(self):
        hoja_series = await asyncio.to_thread(self.spreadsheet.worksheet, "Series")
        hoja_asig = await asyncio.to_thread(self.spreadsheet.worksheet, "Asignaciones")
        hoja_reg = await asyncio.to_thread(self.spreadsheet.worksheet, "Registro")

        series = await asyncio.to_thread(hoja_series.get_all_records)
        asignaciones = await asyncio.to_thread(hoja_asig.get_all_records)
        registros = await asyncio.to_thread(hoja_reg.get_all_records)

        replace_series(series)
        replace_asignaciones(asignaciones)
        replace_registros(registros)
        print("SQLite sincronizado desde Google Sheets.")
    
    async def setup_hook(self):
        setup_db()
        try:
            print("🔄 Conectando a Google Sheets...")
            self.gc = gspread.service_account("credentials.json")
            print("✅ Autenticación exitosa.")
            
            # Mostrar todas las hojas disponibles
            hojas = self.gc.list_spreadsheet_files()
            print(f"📋 Hojas disponibles: {hojas}")
            
            self.spreadsheet = self.gc.open_by_key("1U_28Ggvm_ulCnpXASBkhzXH3VTBt79dCUS8gxRgWINk")
            print("✅ Conexión con Google Sheets exitosa.")
            await self.sincronizar_sqlite_desde_sheets()
        except Exception as e:
            print(f"❌ Tipo de error: {type(e)}")
            print(f"❌ Error: {e}")
            traceback.print_exc()
            raise RuntimeError("No se pudo conectar a Google Sheets. Abortando inicio del bot.") from e
        
        # Cargar cogs
        await self.load_extension('cogs.comandos')
        await self.load_extension('cogs.naver_playwright')
        await self.load_extension('cogs.coordinador')
        
        await self.tree.sync()
        print("✅ Comandos Slash sincronizados con Discord.")

bot = BloomBot()

@bot.event
async def on_ready():
    print(f'🌸 Bloom Scans Bot encendido como {bot.user}')
    print('--- Sistema de Vigilancia y Premios Activo ---')

# ============================================================================
# COMANDO !sync (Manual) - SOLO ADMINISTRADORES
# ============================================================================
@bot.command(name='sync')
@commands.has_permissions(administrator=True)
async def sync(ctx):
    """Sincroniza manualmente los comandos slash"""
    try:
        await ctx.send("🔄 Sincronizando comandos...")
        synced = await bot.tree.sync()
        await ctx.send(f"✅ {len(synced)} comandos sincronizados exitosamente!")
        print(f"✅ Sincronizados {len(synced)} comandos: {[cmd.name for cmd in synced]}")
    except Exception as e:
        await ctx.send(f"❌ Error sincronizando: {e}")
        print(f"❌ Error en sync: {e}")

@sync.error
async def sync_error(ctx, error):
    """Maneja errores del comando sync"""
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ **No tienes permisos para usar este comando.** Se requiere rol de Administrador.")
    else:
        await ctx.send(f"❌ Error: {error}")

async def main():
    async with bot:
        await bot.start(os.getenv("DISCORD_BOT_TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())
