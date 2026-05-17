# main.py — Punto de entrada para ESP32-S3 con MicroPython
# Arquitectura: polling de interacciones Discord via Gateway HTTP (no WebSocket).
# El ESP32 recibe slash commands mediante un Gateway intermedio o via webhook.
#
# NOTA: Discord no permite polling REST para slash commands directamente.
# Este main.py implementa dos estrategias:
#   1. Modo WEBHOOK: El GAS recibe el webhook de Discord y lo re-enruta al ESP32.
#   2. Modo POLLING GAS: El ESP32 consulta al GAS cada N segundos si hay
#      comandos pendientes (el GAS actúa como cola de mensajes).
# Se usa la estrategia 2 por simplicidad en ESP32 sin servidor público.

import utime
import gc
import ujson

import wifi_manager as wifi
import gas_client as gas
from discord_http import respond_interaction, send_followup, make_embed, send_embed
from config import (
    WIFI_SSID, WIFI_PASSWORD,
    HEARTBEAT_S, REVISION_DRIVE_S, REPORTE_SEMANAL_S, INACTIVIDAD_LOOP_S,
    RELAY_PIN, ADMIN_CHANNEL_ID,
)

# Módulos de comandos
import comandos
import coordinador

# ──────────────────────────────────────────────
# CONSTANTES DE TIMING
# ──────────────────────────────────────────────
POLL_INTERVAL_S    = 1    # Cada cuántos segundos preguntar al GAS por comandos
import time
_now = int(time.time())
_last_drive_check  = _now
_last_reporte      = _now
_last_inactividad  = _now

# ──────────────────────────────────────────────
# RELAY (control de PC, opcional)
# ──────────────────────────────────────────────
try:
    from machine import Pin
    relay = Pin(RELAY_PIN, Pin.OUT)
    relay.value(0)
    HAS_RELAY = True
except Exception:
    HAS_RELAY = False
    relay = None


def pulse_relay(ms: int = 500):
    """Activa el relay por ms milisegundos (simula presión de botón de encendido)."""
    if relay:
        relay.value(1)
        utime.sleep_ms(ms)
        relay.value(0)


# ──────────────────────────────────────────────
# DISPATCHER DE COMANDOS
# ──────────────────────────────────────────────
def dispatch(cmd: dict) -> dict:
    """
    Recibe un dict con la interacción procesada por el GAS y devuelve la respuesta.

    Estructura esperada del GAS:
    {
        "command": "terminado",
        "interaction_id": "...",
        "interaction_token": "...",
        "user_id": "...",
        "user_name": "...",
        "channel_id": "...",
        "guild_id": "...",
        "roles": ["roleId1", ...],
        "is_admin": false,
        "options": { "rol": "Cleaner", "serie_name": "...", "serie_channel_id": "...", "capitulo": "..." }
    }
    """
    name    = cmd.get("command", "")
    user_id = cmd.get("user_id", "")
    user_name = cmd.get("user_name", "")
    channel_id = cmd.get("channel_id", "")
    guild_id   = cmd.get("guild_id", "")
    roles      = cmd.get("roles", [])
    es_admin   = bool(cmd.get("is_admin", False))
    opts       = cmd.get("options", {})

    # ── Normalizar nombres de opciones resueltas por GAS ──
    # Discord envía "usuario" (type:6/USER) → GAS genera: usuario, usuario_user_id, usuario_user_name
    # Discord envía "serie"  (type:7/CHANNEL) → GAS genera: serie, serie_name, serie_id
    # Discord envía "canal"  (type:7/CHANNEL) → GAS genera: canal, canal_name, canal_id
    serie_name       = opts.get("serie_name") or ""
    serie_channel_id = opts.get("serie_id") or opts.get("serie") or ""
    target_user_id   = opts.get("usuario_user_id") or opts.get("usuario") or ""
    target_user_name = opts.get("usuario_user_name") or ""
    canal_id         = opts.get("canal_id") or opts.get("canal") or ""
    canal_name       = opts.get("canal_name") or ""



    # Fallbacks: si el nombre no se resolvió, usar mención de Discord
    if not target_user_name and target_user_id:
        target_user_name = f"<@{target_user_id}>"
    if not serie_name and serie_channel_id:
        serie_name = f"<#{serie_channel_id}>"

    # Construir avatar URL para comandos personales
    user_avatar = opts.get("_user_avatar", "")
    if not user_avatar and user_id:
        user_avatar = f"https://cdn.discordapp.com/embed/avatars/{int(user_id) % 5}.png"

    try:
        if name == "apodo":
            return comandos.cmd_apodo(user_id, channel_id, opts.get("nombre", ""))

        elif name == "asignar":
            return comandos.cmd_asignar(
                user_id, roles, es_admin,
                target_user_id, target_user_name,
                opts.get("tarea"), serie_name,
                serie_channel_id, opts.get("capitulo"), guild_id
            )

        elif name == "terminado":
            return comandos.cmd_terminado(
                user_id, user_name, channel_id,
                opts.get("rol"), serie_name,
                serie_channel_id, opts.get("capitulo")
            )

        elif name == "ver_asignacion":
            return comandos.cmd_ver_asignacion(
                serie_name, serie_channel_id, opts.get("capitulo")
            )

        elif name == "creditos":
            return comandos.cmd_creditos(serie_name, opts.get("capitulo"))

        elif name == "trabajos":
            return comandos.cmd_trabajos(user_id, opts.get("mes"))

        elif name == "ausente":
            return comandos.cmd_ausente(
                user_id, user_name, channel_id, es_admin,
                int(opts.get("dias", 1)), opts.get("motivo", "")
            )

        elif name == "cancelar_ausencia":
            return comandos.cmd_cancelar_ausencia(user_id, channel_id, es_admin)

        elif name == "abandonar":
            return comandos.cmd_abandonar(
                user_id, serie_name, opts.get("capitulo"), opts.get("tarea")
            )

        elif name == "cancelar_asignacion":
            return comandos.cmd_cancelar_asignacion(
                roles, es_admin, serie_name, opts.get("capitulo"), opts.get("tarea")
            )

        elif name == "quitar_staff":
            return comandos.cmd_quitar_staff(
                roles, es_admin, opts.get("usuario")
            )

        elif name == "registrar_correo":
            return comandos.cmd_registrar_correo(
                user_id, user_name, opts.get("correo")
            )

        elif name == "posibles_ganadores":
            return comandos.cmd_posibles_ganadores(opts.get("mes"), opts.get("anio"))

        elif name == "refrescar_asignaciones":
            return comandos.cmd_refrescar_asignaciones(roles, es_admin)

        elif name == "helps":
            return comandos.cmd_helps()

        elif name == "agregar_serie":
            return coordinador.cmd_agregar_serie(
                user_id, user_name, es_admin,
                canal_id, canal_name,
                opts.get("link_drive"), opts.get("categoria"), opts.get("idioma")
            )

        elif name == "estado_serie":
            return coordinador.cmd_estado_serie(roles, es_admin, serie_channel_id)

        elif name == "actualizar_drive":
            return coordinador.cmd_actualizar_drive(roles, es_admin, serie_channel_id)

        elif name == "asignarme":
            return coordinador.cmd_asignarme(
                user_id, user_name, guild_id,
                opts.get("tarea"), opts.get("categoria"),
                opts.get("idioma", "cualquiera")
            )

        elif name == "mis_asignaciones":
            return comandos.cmd_mis_asignaciones(user_id, user_name, user_avatar)

        elif name == "relay_pc":
            if not es_admin:
                return {"content": "❌ Solo administradores.", "ephemeral": True}
            pulse_relay(int(opts.get("ms", 500)))
            return {"content": "✅ Relay activado (PC encendida/apagada)."}

        else:
            return {"content": f"❓ Comando desconocido: `{name}`", "ephemeral": True}

    except Exception as e:
        print(f"[dispatch] Error en '{name}': {e}")
        return {"content": f"❌ Error interno: {e}", "ephemeral": True}


# ──────────────────────────────────────────────
# ENVIAR RESPUESTA AL INTERACTION
# ──────────────────────────────────────────────
def send_response(cmd: dict, result: dict):
    iid   = cmd.get("interaction_id")
    token = cmd.get("interaction_token")
    content  = result.get("content", "")
    embed    = result.get("embed")
    ephemeral= result.get("ephemeral", False)

    if iid and token:
        send_followup(token, content=content, embed=embed, ephemeral=ephemeral)
    else:
        # Sin token, publicar directo al canal
        channel_id = cmd.get("channel_id")
        if channel_id:
            from discord_http import send_message
            send_message(channel_id, content=content, embed=embed)


import _thread

# ──────────────────────────────────────────────
# POLLING DE COMANDOS DESDE GAS
# ──────────────────────────────────────────────
def _process_cmd_worker(cmd):
    """Función de hilo para procesar un comando sin bloquear el hilo principal."""
    try:
        print(f"[_thread] ⚡ Procesando: {cmd.get('command')}")
        result = dispatch(cmd)
        send_response(cmd, result)
        gas._post({"action": "ackCommand", "cmdId": cmd.get("_id")})
    except Exception as e:
        print(f"[_thread] Error procesando {cmd.get('command')}: {e}")
    finally:
        gc.collect()

def poll_commands():
    """Pregunta al GAS si hay comandos pendientes y los procesa."""
    gc.collect()
    r = gas._get({"action": "getPendingCommands"})
    if not r.get("ok"):
        return
    cmds = r.get("data", [])
    
    if not cmds:
        return
        
    # Si hay un solo comando, lo procesamos en el hilo principal para evitar overhead
    if len(cmds) == 1:
        _process_cmd_worker(cmds[0])
        return

    # Si hay múltiples comandos, procesamos el primero en el hilo principal
    # y los demás en un hilo de fondo (aprovechando el doble núcleo del ESP32).
    # ESP32-S3 maneja bien 1-2 hilos extra, no saturamos creando 10 hilos a la vez.
    print(f"[main] 🚀 Recibidos {len(cmds)} comandos. Usando multiprocesamiento (_thread).")
    
    # Procesar el resto en hilos secundarios
    for i in range(1, len(cmds)):
        try:
            _thread.start_new_thread(_process_cmd_worker, (cmds[i],))
        except Exception as e:
            print(f"[main] No se pudo crear hilo para comando: {e}")
            # Fallback a secuencial si nos quedamos sin recursos
            _process_cmd_worker(cmds[i])
            
    # Procesar el primero en el hilo principal
    _process_cmd_worker(cmds[0])


# ──────────────────────────────────────────────
# TAREAS PERIÓDICAS
# ──────────────────────────────────────────────
def run_periodic_tasks():
    global _last_drive_check, _last_reporte, _last_inactividad
    now = utime.time()

    if now - _last_drive_check >= REVISION_DRIVE_S:
        print("[main] Ejecutando revisión automática de Drive...")
        coordinador.tarea_revision_automatica()
        _last_drive_check = now

    if now - _last_reporte >= REPORTE_SEMANAL_S:
        print("[main] Ejecutando reporte semanal...")
        coordinador.tarea_reporte_semanal()
        _last_reporte = now

    if now - _last_inactividad >= INACTIVIDAD_LOOP_S:
        print("[main] Verificando inactividad del staff...")
        _check_inactividad()
        _last_inactividad = now


def _check_inactividad():
    """Alerta al canal admin si algún staff lleva 7+ días sin actividad."""
    try:
        series = gas.get_series()  # reusar conexión activa
        # El GAS expone un endpoint específico para esto
        r = gas._get({"action": "getStaffInactividad", "diasLimite": "7"})
        if not r.get("ok"):
            return
        inactivos = r.get("data", [])
        for m in inactivos:
            embed = make_embed(
                title="🚨 Alerta de Inactividad (7 días)",
                description=f"<@{m['user_id']}> lleva más de 7 días inactivo.",
                color=0xe74c3c,
                fields=[{"name": "Último visto", "value": str(m.get('last_msg', 'Nunca')), "inline": True}]
            )
            send_embed(ADMIN_CHANNEL_ID, embed)
    except Exception as e:
        print(f"[inactividad] Error: {e}")


# ──────────────────────────────────────────────
# MAIN LOOP
# ──────────────────────────────────────────────
def main():
    print("=" * 40)
    print("  SerenityStaff Lite — ESP32-S3")
    print("  MicroPython + GAS Bridge")
    print("=" * 40)

    # 1. Conectar WiFi
    if not wifi.connect(WIFI_SSID, WIFI_PASSWORD):
        print("[main] FATAL: No se pudo conectar al WiFi.")
        return

    print("[main] Sistema listo. Iniciando polling...")

    while True:
        try:
            # Reconectar si se perdió WiFi
            wifi.ensure_connected(WIFI_SSID, WIFI_PASSWORD)

            # Procesar comandos pendientes
            poll_commands()

            # Tareas periódicas (Drive, reporte semanal, inactividad)
            run_periodic_tasks()

        except MemoryError:
            print("[main] MemoryError — Ejecutando gc.collect()")
            gc.collect()
        except Exception as e:
            print(f"[main] Error en loop principal: {e}")

        utime.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    main()
