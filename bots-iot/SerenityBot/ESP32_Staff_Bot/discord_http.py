# discord_http.py — Envía mensajes a Discord usando la HTTP API directamente
# Compatible con MicroPython (urequests)
# El ESP32 actúa como bot cliente REST: no recibe eventos WebSocket.
# ============================================================

import ujson
import gc
try:
    import urequests as requests
except ImportError:
    import requests

from config import DISCORD_BOT_TOKEN

BASE = "https://discord.com/api/v10"
_HEADERS = {
    "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
    "Content-Type": "application/json",
    "User-Agent": "SerenityBot/1.0 (ESP32-S3; MicroPython)",
}
_TIMEOUT = 15


def _req(method: str, endpoint: str, payload: dict = None) -> dict:
    gc.collect()
    url = BASE + endpoint
    body = ujson.dumps(payload) if payload else None
    try:
        if method == "GET":
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        elif method == "POST":
            resp = requests.post(url, headers=_HEADERS, data=body, timeout=_TIMEOUT)
        elif method == "PATCH":
            resp = requests.patch(url, headers=_HEADERS, data=body, timeout=_TIMEOUT)
        elif method == "DELETE":
            resp = requests.delete(url, headers=_HEADERS, timeout=_TIMEOUT)
        else:
            return {"ok": False, "error": f"Unknown method {method}"}
        
        status = resp.status_code
        try:
            data = ujson.loads(resp.text)
        except Exception:
            data = {}
        resp.close()
        return {"ok": status in (200, 201, 204), "status": status, "data": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─────────────────────────────────────────
#  MENSAJES
# ─────────────────────────────────────────

def send_message(channel_id: str, content: str = "", embed: dict = None) -> dict:
    """Envía un mensaje de texto (y/o embed) a un canal."""
    payload = {}
    if content:
        payload["content"] = content
    if embed:
        payload["embeds"] = [embed]
    return _req("POST", f"/channels/{channel_id}/messages", payload)


def send_embed(channel_id: str, embed: dict, content: str = "") -> dict:
    """Alias semántico para enviar un embed."""
    return send_message(channel_id, content=content, embed=embed)


def delete_message(channel_id: str, message_id: str) -> dict:
    return _req("DELETE", f"/channels/{channel_id}/messages/{message_id}")


def get_channel_messages(channel_id: str, limit: int = 100) -> list:
    """Obtiene los últimos N mensajes de un canal."""
    r = _req("GET", f"/channels/{channel_id}/messages?limit={limit}")
    return r.get("data", []) if r.get("ok") else []


# ─────────────────────────────────────────
#  RESPUESTA A INTERACCIONES (Slash Commands)
# ─────────────────────────────────────────

def respond_interaction(interaction_id: str, interaction_token: str,
                        content: str = "", embed: dict = None, ephemeral: bool = False) -> dict:
    """Responde a una interacción de slash command (tipo 4 = CHANNEL_MESSAGE_WITH_SOURCE)."""
    data = {"tts": False}
    if content:
        data["content"] = content
    if embed:
        data["embeds"] = [embed]
    if ephemeral:
        data["flags"] = 64
    payload = {"type": 4, "data": data}
    return _req("POST", f"/interactions/{interaction_id}/{interaction_token}/callback", payload)


def send_followup(interaction_token: str, content: str = "",
                  embed: dict = None, ephemeral: bool = False) -> dict:
    """Envía un followup a una interacción ya respondida, vía GAS proxy.
    
    El ESP32 no puede hacer PATCH directo a discord.com (limitación TLS de urequests).
    En su lugar, enviamos el payload al GAS y éste hace el PATCH por nosotros.
    """
    import gas_client as gas
    payload = {}
    if content:
        payload["content"] = content
    if embed:
        payload["embeds"] = [embed]
    if ephemeral:
        payload["flags"] = 64
    return gas._post({
        "action": "sendFollowup",
        "token": interaction_token,
        "payload": payload,
    })


def defer_interaction(interaction_id: str, interaction_token: str, ephemeral: bool = False) -> dict:
    """Difiere una interacción (tipo 5 = DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE)."""
    flags = 64 if ephemeral else 0
    payload = {"type": 5, "data": {"flags": flags}}
    return _req("POST", f"/interactions/{interaction_id}/{interaction_token}/callback", payload)


# ─────────────────────────────────────────
#  ROLES Y PERMISOS
# ─────────────────────────────────────────

def add_role(guild_id: str, user_id: str, role_id: str) -> bool:
    r = _req("PUT", f"/guilds/{guild_id}/members/{user_id}/roles/{role_id}")
    return r.get("ok") or r.get("status") == 204


def remove_role(guild_id: str, user_id: str, role_id: str) -> bool:
    r = _req("DELETE", f"/guilds/{guild_id}/members/{user_id}/roles/{role_id}")
    return r.get("ok") or r.get("status") == 204


def get_guild_member(guild_id: str, user_id: str) -> dict:
    r = _req("GET", f"/guilds/{guild_id}/members/{user_id}")
    return r.get("data", {}) if r.get("ok") else {}


# ─────────────────────────────────────────
#  CANALES
# ─────────────────────────────────────────

def create_channel(guild_id: str, name: str, parent_id: str = None,
                   permission_overwrites: list = None) -> dict:
    payload = {"name": name, "type": 0}
    if parent_id:
        payload["parent_id"] = parent_id
    if permission_overwrites:
        payload["permission_overwrites"] = permission_overwrites
    r = _req("POST", f"/guilds/{guild_id}/channels", payload)
    return r.get("data", {}) if r.get("ok") else {}


def edit_channel_permissions(channel_id: str, overwrite_id: str,
                              allow: str = "0", deny: str = "0",
                              overwrite_type: int = 1) -> bool:
    """type=1 → miembro, type=0 → rol."""
    r = _req("PUT", f"/channels/{channel_id}/permissions/{overwrite_id}",
             {"allow": allow, "deny": deny, "type": overwrite_type})
    return r.get("ok") or r.get("status") == 204


# ─────────────────────────────────────────
#  MENSAJES FIJADOS Y CANALES
# ─────────────────────────────────────────

def get_pinned_messages(channel_id: str) -> list:
    """Obtiene los mensajes fijados de un canal."""
    r = _req("GET", f"/channels/{channel_id}/pins")
    return r.get("data", []) if r.get("ok") else []


def get_channel_info(channel_id: str) -> dict:
    """Obtiene información de un canal (nombre, categoría, etc.)."""
    r = _req("GET", f"/channels/{channel_id}")
    return r.get("data", {}) if r.get("ok") else {}


# ─────────────────────────────────────────
#  ROLES DEL SERVIDOR
# ─────────────────────────────────────────

def get_guild_roles(guild_id: str) -> list:
    """Obtiene todos los roles del servidor."""
    r = _req("GET", f"/guilds/{guild_id}/roles")
    return r.get("data", []) if r.get("ok") else []


def create_guild_role(guild_id: str, name: str, color: int = 0xff7eb3,
                      mentionable: bool = True) -> dict:
    """Crea un nuevo rol en el servidor."""
    payload = {"name": name, "color": color, "mentionable": mentionable}
    r = _req("POST", f"/guilds/{guild_id}/roles", payload)
    return r.get("data", {}) if r.get("ok") else {}


# ─────────────────────────────────────────
#  EMBEDS (constructores de dicts)
# ─────────────────────────────────────────

def make_embed(title: str = "", description: str = "",
               color: int = 0xffb6c1, fields: list = None,
               footer: str = "", thumbnail_url: str = "") -> dict:
    """
    Construye un dict de embed válido para la Discord API.
    fields = [{"name": "...", "value": "...", "inline": False}, ...]
    """
    embed = {"title": title, "description": description, "color": color}
    if fields:
        embed["fields"] = fields
    if footer:
        embed["footer"] = {"text": footer}
    if thumbnail_url:
        embed["thumbnail"] = {"url": thumbnail_url}
    return embed
