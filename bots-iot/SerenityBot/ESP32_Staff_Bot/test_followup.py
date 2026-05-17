"""Test: interceptar un comando de la cola y enviar la respuesta desde PC."""
import requests, json, time

GAS_URL = "https://script.google.com/macros/s/AKfycbx01DK4HVjAtr3dSSvW51McjTyGJstuEUl917X9p6238nSGsF4PdpUdg8K6aQPTA2ac/exec"
APP_ID = "1502112062971838464"
BOT_TOKEN = "MTYOUR_DISCORD_BOT_TOKEN"

print("Esperando un comando en la cola...")
print(">>> VE A DISCORD Y ESCRIBE /helps <<<")

for i in range(90):
    r = requests.get(GAS_URL + "?action=getPendingCommands").json()
    cmds = r.get("data", [])
    if cmds:
        cmd = cmds[0]
        cmd_name = cmd.get("command", "?")
        print(f"Comando recibido: {cmd_name}")
        token = cmd["interaction_token"]

        headers = {
            "Authorization": f"Bot {BOT_TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "SerenityBot/1.0",
        }
        payload = {
            "content": "Test de respuesta directa desde PC!",
            "embeds": [{
                "title": "Test Embed",
                "description": "Si ves esto, el followup funciona.",
                "color": 0xff7eb3,
            }]
        }

        url = f"https://discord.com/api/v10/webhooks/{APP_ID}/{token}/messages/@original"
        print(f"PATCH URL: {url[:80]}...")
        resp = requests.patch(url, headers=headers, json=payload)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text[:500]}")

        # ACK the command
        requests.post(GAS_URL, json={"action": "ackCommand", "cmdId": cmd["_id"]})
        print("Comando ACK'd")
        break
    time.sleep(1)
    if i % 10 == 0:
        print(f"  ...esperando ({i}s)")
else:
    print("Timeout - no se recibio comando en 90s")

