# -*- coding: utf-8 -*-
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import asyncio
from database_staff import update_activity, set_absence, get_absence, set_apodo, get_apodo

# CONFIGURACIÓN DE IDs (Extraídos de tu bot original)
ADMIN_CHANNEL_ID = 1432254360666247168
STAFF_ROLE_ID = 1132158706851786854
CANAL_JUSTIFICACION_ID = 1458363364727328903
CANAL_ASIGNACIONES_LOG = 1460771399999160442
CANAL_CREDITOS_APODO = 1458363518725390452
CANALES_TERMINADOS = [1458345407959797902, 1458345512624459951, 1458345602151878767]

class StaffLite(commands.Cog):
    def __init__(self, bot, excel_manager):
        self.bot = bot
        self.excel = excel_manager

    # EVENTO DE ACTIVIDAD
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return
        update_activity(message.author.id, message.author.name)
        
        # Escudo de ausencia
        if message.mentions:
            for member in message.mentions:
                absence = get_absence(member.id)
                if absence:
                    date_fin = datetime.fromisoformat(absence)
                    if datetime.now() < date_fin:
                        embed = discord.Embed(
                            title="🛡️ Escudo de Ausencia",
                            description=f"{member.mention} está ausente hasta <t:{int(date_fin.timestamp())}:D>.",
                            color=discord.Color.orange()
                        )
                        await message.channel.send(embed=embed, delete_after=15)

    # COMANDO: ASIGNAR
    @app_commands.command(name="asignar", description="Asigna una tarea de un capítulo")
    @app_commands.choices(tarea=[
        app_commands.Choice(name="Traductor", value="Traductor"),
        app_commands.Choice(name="Editor", value="Editor"),
        app_commands.Choice(name="Cleaner", value="Cleaner"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def asignar(self, interaction: discord.Interaction, usuario: discord.Member, tarea: app_commands.Choice[str], serie: discord.TextChannel, capitulo: str):
        await interaction.response.defer()
        try:
            # Registrar en Excel
            await self.excel.add_assignment(serie.name, capitulo, tarea.value, usuario.name, usuario.id)
            
            # Embed de Log
            log_chan = self.bot.get_channel(CANAL_ASIGNACIONES_LOG)
            if log_chan:
                embed = discord.Embed(title="✨ Nueva Asignación", color=0x3498db)
                embed.add_field(name="Proyecto", value=serie.mention, inline=True)
                embed.add_field(name="Capítulo", value=f"`{capitulo}`", inline=True)
                embed.add_field(name="Staff", value=usuario.mention, inline=True)
                embed.add_field(name="Tarea", value=tarea.name, inline=False)
                await log_chan.send(embed=embed)
            
            await interaction.followup.send(f"✅ **{usuario.name}** asignado a **{serie.name} {capitulo}** como {tarea.name}.")
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}")

    # COMANDO: TERMINADO
    @app_commands.command(name="terminado", description="Marca una tarea como finalizada")
    @app_commands.choices(tarea=[
        app_commands.Choice(name="Traductor", value="Traductor"),
        app_commands.Choice(name="Editor", value="Editor"),
        app_commands.Choice(name="Cleaner", value="Cleaner"),
    ])
    async def terminado(self, interaction: discord.Interaction, tarea: app_commands.Choice[str], serie: discord.TextChannel, capitulo: str):
        if interaction.channel_id not in CANALES_TERMINADOS:
            await interaction.response.send_message("❌ Usa este comando en los canales de terminados.", ephemeral=True)
            return

        await interaction.response.defer()
        success = await self.excel.mark_as_finished(serie.name, capitulo, tarea.value, interaction.user.id)
        
        if success:
            update_activity(interaction.user.id, interaction.user.name)
            embed = discord.Embed(title="✅ Trabajo Registrado", color=discord.Color.green())
            embed.add_field(name="Proyecto", value=serie.mention, inline=True)
            embed.add_field(name="Capítulo", value=f"`{capitulo}`", inline=True)
            embed.set_footer(text=f"Staff: {interaction.user.name}")
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("❌ No se encontró una asignación activa para ti con esos datos.", ephemeral=True)

    # COMANDO: ESTATUS EQUIPO
    @app_commands.command(name="estatus_equipo", description="Muestra la actividad actual de un rol")
    async def estatus_equipo(self, interaction: discord.Interaction, rol: discord.Role):
        await interaction.response.defer()
        active_tasks = await self.excel.get_staff_status()
        
        embed = discord.Embed(title=f"👥 Estatus: {rol.name}", color=rol.color or 0xffb6c1)
        
        for member in rol.members:
            if member.bot: continue
            tasks = [t for t in active_tasks if str(t['ID_Usuario']) == str(member.id)]
            
            info = ""
            if tasks:
                for t in tasks:
                    info += f"🔹 **{t['Tarea']}** en #{t['Proyecto']} (`{t['Capítulo']}`)\n"
            else:
                info = "✅ *Disponible*"
            
            embed.add_field(name=f"👤 {member.display_name}", value=info + "\n\u200b", inline=False)
        
        await interaction.followup.send(embed=embed)

    # COMANDO: AUSENCIA
    @app_commands.command(name="ausente", description="Registra tu ausencia")
    async def ausente(self, interaction: discord.Interaction, dias: int, motivo: str):
        if interaction.channel_id != CANAL_JUSTIFICACION_ID:
            await interaction.response.send_message(f"❌ Usa <#{CANAL_JUSTIFICACION_ID}>.", ephemeral=True)
            return
            
        until = datetime.now() + timedelta(days=dias)
        set_absence(interaction.user.id, until.isoformat())
        
        embed = discord.Embed(title="💤 Ausencia Registrada", color=discord.Color.blue())
        embed.add_field(name="Staff", value=interaction.user.mention)
        embed.add_field(name="Regresa", value=f"<t:{int(until.timestamp())}:D>")
        embed.add_field(name="Motivo", value=motivo)
        
        await interaction.response.send_message(embed=embed)

async def setup_staff(bot, excel):
    await bot.add_cog(StaffLite(bot, excel))
