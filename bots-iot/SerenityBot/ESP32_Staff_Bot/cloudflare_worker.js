/**
 * Cloudflare Worker Proxy para SerenityStaff Lite
 * 
 * Este worker actúa como puente entre Discord y Google Apps Script.
 * Su único propósito es validar la firma criptográfica Ed25519 que Discord
 * exige para todos los Interactions Endpoints, ya que Apps Script no lo soporta.
 * 
 * CONFIGURACIÓN EN CLOUDFLARE:
 * 1. Crea un Worker en Cloudflare.
 * 2. Pega este código.
 * 3. Configura la siguiente Variable de Entorno (Settings -> Variables):
 *    - GAS_URL: (La URL completa de tu Google Apps Script web app)
 */

export default {
  async fetch(request, env, ctx) {
    // Solo aceptamos peticiones POST (Discord envía POST a los endpoints)
    if (request.method !== 'POST') {
      return new Response('Not Found', { status: 404 });
    }

    const signature = request.headers.get('x-signature-ed25519');
    const timestamp = request.headers.get('x-signature-timestamp');

    if (!signature || !timestamp) {
      return new Response('Missing signature headers', { status: 401 });
    }

    // Clona el cuerpo de la petición para poder leerlo y luego enviarlo
    const bodyText = await request.clone().text();

    // 1. Validar la firma Ed25519 usando Web Crypto API
    const isValid = await verifyDiscordSignature(
      bodyText,
      signature,
      timestamp,
      "a389957fb2ec96f7141d2f0c03f2e6af6f01f699ddcbfe535167054d2076c2c0" // Bloomie Public Key
    );

    if (!isValid) {
      return new Response('Invalid request signature', { status: 401 });
    }

    // Si es un PING de validación de Discord, respondemos inmediatamente
    const bodyJson = JSON.parse(bodyText);
    if (bodyJson.type === 1) { // 1 = PING
      return new Response(JSON.stringify({ type: 1 }), {
        headers: { 'Content-Type': 'application/json' }
      });
    }

    // 2. Si es válido, enviamos los datos al Google Apps Script (GAS)
    // Usamos ctx.waitUntil para no hacer esperar a Discord por la respuesta de GAS,
    // y respondemos inmediatamente con type: 5 (Deferred).
    
    // Extraer el nombre del comando
    let cmdName = "";
    if (bodyJson.type === 2) {
      cmdName = bodyJson.data ? bodyJson.data.name : "";
    } else if (bodyJson.type === 3) {
      cmdName = bodyJson.data && bodyJson.data.custom_id ? bodyJson.data.custom_id.split("|")[0] : "";
    }

    // Comandos cuya respuesta se auto-elimina a los 5 minutos para no llenar el chat
    // Detectar si es botón (type 3), autocomplete (type 4) vs slash command (type 2)
    const isButton = bodyJson.type === 3;
    const isAutocomplete = bodyJson.type === 4;

    if (isAutocomplete) {
      // Para Autocomplete, Discord requiere una respuesta sincrónica inmediata (tipo 8).
      // No podemos usar ctx.waitUntil ni diferir. Tenemos que esperar a GAS y devolver el JSON.
      try {
        const res = await fetch(env.GAS_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: bodyText
        });
        const data = await res.json();
        
        // GAS devuelve directamente { type: 8, data: { choices: [...] } }.
        if (data && data.type === 8) {
          return new Response(JSON.stringify(data), {
            headers: { 'Content-Type': 'application/json' }
          });
        }
        if (data && data.ok && data.responsePayload) {
          return new Response(JSON.stringify(data.responsePayload), {
            headers: { 'Content-Type': 'application/json' }
          });
        } else {
          return new Response(JSON.stringify({ type: 8, data: { choices: [] } }), {
            headers: { 'Content-Type': 'application/json' }
          });
        }
      } catch (err) {
        console.error("Error en Autocomplete fetch:", err);
        return new Response(JSON.stringify({ type: 8, data: { choices: [] } }), {
          headers: { 'Content-Type': 'application/json' }
        });
      }
    }

    ctx.waitUntil(
      fetch(env.GAS_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: bodyText
      })
      .then(r => r.json().catch(e => ({ ok: false, error: "JSON Parsing Error: " + e.message })))
      .then(data => {
        const appId = "1502112062971838464";
        let promises = [];
        
        if (!data.ok || !data.responsePayload) {
          data.responsePayload = { content: "❌ Error procesando el comando: " + (data.error || "desconocido") };
        }
        
        // Eliminar flags del PATCH, Discord se enoja si mandamos flags en el PATCH
        if (data.responsePayload && data.responsePayload.flags) {
          delete data.responsePayload.flags;
        }
        
        if (isButton) {
          // Para botones: PATCH al mensaje del webhook original
          const url = `https://discord.com/api/v10/webhooks/${appId}/${bodyJson.token}/messages/@original`;
          promises.push(
            fetch(url, {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(data.responsePayload)
            }).catch(e => console.error("Error en PATCH botón:", e))
          );
        } else {
          // Para slash commands: PATCH al mensaje deferred
          const url = `https://discord.com/api/v10/webhooks/${appId}/${bodyJson.token}/messages/@original`;
          promises.push(
            fetch(url, {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(data.responsePayload)
            }).catch(e => console.error("Error en PATCH a Discord:", e))
          );
        }
        
        if (data.extraActions && data.extraActions.length > 0) {
          for (let action of data.extraActions) {
            promises.push(
              fetch(action.url, {
                method: action.method || 'POST',
                headers: { 
                  'Content-Type': 'application/json', 
                  'Authorization': action.auth || '' 
                },
                body: JSON.stringify(action.body)
              }).then(async res => {
                if (!res.ok) {
                  const text = await res.text().catch(() => "");
                  console.error(`Error extraAction ${action.url}: HTTP ${res.status}`);
                  await logActionFailure(env.GAS_URL, bodyJson, action, res.status, text);
                }
              }).catch(e => {
                console.error("Error extraAction:", e);
                return logActionFailure(env.GAS_URL, bodyJson, action, "fetch_error", e.message);
              })
            );
          }
        }
        
        // Auto-borrar el mensaje después de 5 minutos (solo para slash commands, no botones)
        return Promise.all(promises);
      })
      .catch(err => console.error("Error al enviar a GAS:", err))
    );

    // 3. Responder a Discord al instante
    const ephemeralCommands = ["helps", "mis_asignaciones", "terminado", "trabajos", "ver_asignacion", "asignarme", "abandonar", "ausente", "cancelar_ausencia", "registrar_correo", "apodo", "progreso", "mi_perfil", "limpiar_inactivos", "ticket", "creditos", "posibles_ganadores", "cancelar_asignacion", "quitar_staff", "agregar_serie", "actualizar_drive", "refrescar_asignaciones", "mis_trabajos", "asignaciones_usuario"];
    const isEphemeral = ephemeralCommands.includes(cmdName);
    
    let responseData;
    if (isButton) {
      // type 6 = Deferred Update Message Component
      // Reconoce el botón silenciosamente y permite editar el mensaje existente via PATCH
      responseData = { type: 6 };
    } else if (isEphemeral) {
      // type 5 = Deferred Channel Message + ephemeral
      responseData = { type: 5, data: { flags: 64 } };
    } else {
      // type 5 = Deferred Channel Message (público)
      responseData = { type: 5 };
    }

    return new Response(JSON.stringify(responseData), {
      headers: { 'Content-Type': 'application/json' }
    });
  }
};

/**
 * Función auxiliar para validar Ed25519 en Cloudflare Workers
 */
async function verifyDiscordSignature(body, signatureHex, timestamp, publicKeyHex) {
  try {
    const encoder = new TextEncoder();
    const data = encoder.encode(timestamp + body);
    
    const signature = hexToUint8Array(signatureHex);
    const publicKey = hexToUint8Array(publicKeyHex);

    const cryptoKey = await crypto.subtle.importKey(
      "raw",
      publicKey,
      { name: "Ed25519" },
      false,
      ["verify"]
    );

    return await crypto.subtle.verify(
      cryptoKey.algorithm.name,
      cryptoKey,
      signature,
      data
    );
  } catch (error) {
    console.error("Error validando firma:", error);
    return false;
  }
}

function hexToUint8Array(hex) {
  const bytes = new Uint8Array(Math.ceil(hex.length / 2));
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.substr(i * 2, 2), 16);
  }
  return bytes;
}

async function logActionFailure(gasUrl, interaction, action, status, message) {
  if (!gasUrl) return;
  try {
    const user = interaction.member ? interaction.member.user : interaction.user;
    let command = "";
    if (interaction.type === 2) command = interaction.data ? interaction.data.name : "";
    if (interaction.type === 3) command = interaction.data && interaction.data.custom_id ? interaction.data.custom_id.split("|")[0] : "";
    await fetch(gasUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "logActionFailure",
        failure: {
          command,
          user_id: user ? user.id : "",
          url: action && action.url ? action.url : "",
          status,
          message
        }
      })
    });
  } catch(e) {
    console.error("No se pudo registrar ActionFailure:", e);
  }
}
