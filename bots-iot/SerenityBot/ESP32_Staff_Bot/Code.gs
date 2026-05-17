/**
 * Code.gs — Google Apps Script puente para SerenityStaff Lite
 * URL del deployment:
 * https://script.google.com/macros/s/AKfycby36VIxUtlFdc3kQnU0GEI2Sg6K0O_QhT_P1mLGFFKvMB0lNdvjkvQGqSq1Uf9BeOJk/exec
 *
 * HOJAS REQUERIDAS en el Spreadsheet:
 *   - Series        (Nombre, Canal_ID, Link_Drive, Folder_ID, Categoria, Idioma, Fecha_Agregada, Admin_ID, Admin_Nombre)
 *   - Asignaciones  (Proyecto, Capítulo, Tarea, Usuario, Estado, ID_Usuario)
 *   - Registro      (Fecha, Usuario, Proyecto, Capítulo, Tarea, ID_Usuario)
 *   - Usuarios      (user_id, last_msg, ausencia_hasta)
 *   - Apodos        (user_id, apodo)
 *   - Config        (clave, valor)   → fila: ticket_count, 0
 *   - PendingCmds   (id, command_json, processed)   ← Cola de comandos para el ESP32
 *
 * Este script también registra el Webhook de Discord en doPost()
 * para enrutar slash commands como filas en PendingCmds.
 */

// ─────────────────────────────────────────────────────────────
//  CONFIG
// ─────────────────────────────────────────────────────────────
const SPREADSHEET_ID = "1U_28Ggvm_ulCnpXASBkhzXH3VTBt79dCUS8gxRgWINk";
const DISCORD_PUBLIC_KEY = "a389957fb2ec96f7141d2f0c03f2e6af6f01f699ddcbfe535167054d2076c2c0";
const DISCORD_BOT_TOKEN  = "MTYOUR_DISCORD_BOT_TOKEN";
const APPLICATION_ID     = "1502112062971838464";

const BASE_SHEET_HEADERS = {
  PendingCmds: ["id", "command", "interaction_id", "interaction_token", "user_id", "user_name", "channel_id", "guild_id", "roles", "is_admin", "options", "processed", "created_at"],
  Usuarios: ["user_id", "last_msg", "ausencia_hasta"],
  Apodos: ["user_id", "apodo"],
  Config: ["clave", "valor"],
  Series: ["Nombre", "Canal_ID", "Link_Drive", "Folder_ID", "Categoria", "Idioma", "Fecha_Agregada", "Admin_ID", "Admin_Nombre"],
  Asignaciones: ["Proyecto", "Capitulo", "Tarea", "Usuario", "Estado", "ID_Usuario", "Fecha_Asignacion"],
  Registro: ["Fecha", "Usuario", "Proyecto", "Capitulo", "Tarea", "ID_Usuario"],
  Correos: ["ID_Usuario", "Correos"],
  DebugLog: ["created_at", "body"],
  ActionFailures: ["created_at", "command", "user_id", "url", "status", "message"]
};

// ─────────────────────────────────────────────────────────────
//  HELPERS DE SPREADSHEET
// ─────────────────────────────────────────────────────────────
function getSheet(name) {
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  let sheet = ss.getSheetByName(name);
  if (!sheet) {
    const headers = BASE_SHEET_HEADERS[name];
    if (!headers) {
      throw new Error("Hoja requerida no existe: " + name);
    }
    sheet = ss.insertSheet(name);
    sheet.appendRow(headers);
    return sheet;
  }
  if (sheet.getLastRow() === 0 && BASE_SHEET_HEADERS[name]) {
    sheet.appendRow(BASE_SHEET_HEADERS[name]);
  }
  return sheet;
}

function ensureHeaderColumn(sheet, headerName) {
  const lastCol = Math.max(sheet.getLastColumn(), 1);
  const headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0].map(h => String(h).trim());
  const idx = headers.indexOf(headerName);
  if (idx >= 0) return idx + 1;
  const newCol = headers.length + 1;
  sheet.getRange(1, newCol).setValue(headerName);
  return newCol;
}

function sheetToObjects(sheet) {
  if (!sheet) return [];
  const data = sheet.getDataRange().getValues();
  if (data.length < 2) return [];
  const headers = data[0].map(h => String(h).trim());
  return data.slice(1).map((row, idx) => {
    const obj = { _rowNum: idx + 2 };
    headers.forEach((h, i) => obj[h] = row[i]);
    return obj;
  });
}

function jsonOk(data) {
  return ContentService
    .createTextOutput(JSON.stringify({ ok: true, data: data }))
    .setMimeType(ContentService.MimeType.JSON);
}

function jsonErr(msg) {
  return ContentService
    .createTextOutput(JSON.stringify({ ok: false, error: msg }))
    .setMimeType(ContentService.MimeType.JSON);
}

function jsonSimple(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * Fuerza un ID a ser tratado como texto en Sheets (agregando un apóstrofe inicial)
 */
function asTextId(id) {
  if (!id) return "";
  let s = String(id).trim();
  if (s.startsWith("'")) return s;
  return "'" + s;
}

/**
 * Normaliza un ID leído desde Sheets eliminando el apóstrofe inicial si existe
 */
function normalizeIdFromSheet(id) {
  return String(id || "").replace(/^'+/, "").trim();
}

/**
 * Valida si una fila de la hoja pertenece a un usuario específico
 */
function matchesUser(row, userId, userName, apodoUser) {
  let uidStr = normalizeIdFromSheet(row.ID_Usuario || row.id_usuario || "");
  let targetId = normalizeIdFromSheet(userId);
  
  if (uidStr && uidStr === targetId) return true;
  
  let sheetUser = String(row.Usuario || row.Name || row.name || "").trim().toLowerCase();
  let discordUser = String(userName || "").trim().toLowerCase();
  let apodoLower = String(apodoUser || "").trim().toLowerCase();
  
  if (sheetUser && discordUser && (sheetUser === discordUser || sheetUser.includes(discordUser) || discordUser.includes(sheetUser))) return true;
  if (sheetUser && apodoLower && (sheetUser === apodoLower || sheetUser.includes(apodoLower) || apodoLower.includes(sheetUser))) return true;
  
  return false;
}

// ─────────────────────────────────────────────────────────────
//  ROUTER PRINCIPAL (GET)
// ─────────────────────────────────────────────────────────────
function doGet(e) {
  try {
    const p = e.parameter || {};
    const action = p.action || "";

    if (action === "getSeries")          return jsonOk(sheetToObjects(getSheet("Series")));
    if (action === "getAsignaciones")    return jsonOk(sheetToObjects(getSheet("Asignaciones")));
    if (action === "getRegistros")       return jsonOk(sheetToObjects(getSheet("Registro")));

    if (action === "getUsuario")         return getUsuario(p.userId);
    if (action === "getApodo")           return getApodoEndpoint(p.userId);
    if (action === "listarDrive")        return listarDrive(p.folderId, p.soloCarpetas === "1");
    if (action === "getTablaSerie")      return getTablaSerie(p.serie, p.hoja);
    if (action === "getPendingCommands") return getPendingCommands();
    if (action === "getStaffInactividad")return getStaffInactividad(parseInt(p.diasLimite) || 7);
    if (action === "getDebugLog") {
      const rows = sheetToObjects(getSheet("DebugLog"));
      return jsonOk(rows);
    }

    return jsonErr("Acción GET desconocida: " + action);
  } catch(err) {
    return jsonErr("doGet error: " + err.message);
  }
}

// ─────────────────────────────────────────────────────────────
//  ROUTER PRINCIPAL (POST)
// ─────────────────────────────────────────────────────────────
function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);

    // ── Discord Webhook entry point ──
    // Discord envía type=1 (PING) o type=2 (APPLICATION_COMMAND)
    if (body.type === 1) {
      return ContentService
        .createTextOutput(JSON.stringify({ type: 1 }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    if (body.type === 2 || body.type === 3) {
      return handleDiscordInteraction(body);
    }
    if (body.type === 4) {
      return handleAutocomplete(body);
    }

    // ── Interaction processing (from Cloudflare) ──
    const action = body.action || "";

    if (action === "processInteraction") {
      // Legacy: Cloudflare now routes via type===2 → handleDiscordInteraction
      const interaction = body.interaction;
      if (!interaction || !interaction.data) {
        return jsonErr("Missing interaction data");
      }
      const cmdRecord = {
        command: interaction.data.name,
        interaction_id: "",
        interaction_token: "",
        user_id: "",
        user_name: "",
        channel_id: "",
        guild_id: "",
        roles: [],
        is_admin: false,
        options: {}
      };
      const result = executeCommand(cmdRecord);
      return jsonSimple({ ok: true, responsePayload: result });
    }

    // ── ESP32 API calls ──

    if (action === "upsertSerie")              return upsertSerie(body.serie);
    if (action === "addAsignacion")            return addAsignacion(body.row);
    if (action === "addAsignacionesBatch")     return addAsignacionesBatch(body.rows);
    if (action === "updateAsignacionEstado")   return updateAsignacionEstado(body.rowId, body.estado);
    if (action === "deleteAsignacion")         return deleteAsignacion(body.rowId);
    if (action === "syncAsignaciones")         return syncAsignaciones(body.filas);
    if (action === "addRegistro")              return addRegistro(body.row);
    if (action === "replaceRegistros")         return replaceRegistros(body.filas);
    if (action === "writeTablaSerie")          return writeTablaSerie(body.serie, body.hoja, body.filas);
    if (action === "updateEstadoTareaSerie")   return updateEstadoTareaSerie(body.serie, body.hoja, body.capitulo, body.columna, body.valor);
    if (action === "updateEstadoTareaSerieBatch") return updateEstadoTareaSerieBatch(body.serie, body.hoja, body.capitulos, body.columna, body.valor, body.upsertMissing === true);
    if (action === "setActividad")             return setActividad(body.userId, body.ts);
    if (action === "setAusencia")              return setAusencia(body.userId, body.fechaFin);
    if (action === "clearAusencia")            return clearAusencia(body.userId);
    if (action === "setApodo")                 return setApodo(body.userId, body.apodo);
    if (action === "siguienteTicket")          return siguienteTicket();
    if (action === "duplicarHojaRegistro")     return duplicarHojaRegistro(body.nombre, body.filas);
    if (action === "ackCommand")               return ackCommand(body.cmdId);
    if (action === "setCorreo")                return setCorreo(body.userId, body.email);
    if (action === "quitarStaff")              return quitarStaff(body.userId);
    if (action === "sendFollowup")             return sendFollowup(body.token, body.payload);
    if (action === "logActionFailure")         return logActionFailure(body.failure);

    return jsonErr("Acción POST desconocida: " + action);
  } catch(err) {
    return jsonErr("doPost error: " + err.message);
  }
}

// ─────────────────────────────────────────────────────────────
//  DISCORD INTERACTIONS → COLA DE COMANDOS
// ─────────────────────────────────────────────────────────────
function handleDiscordInteraction(body) {
  try {
    // ── Debug: guardar raw body para depuración ──
    try {
      const dbg = getSheet("DebugLog");
      dbg.appendRow([new Date().toISOString(), JSON.stringify(body).substring(0, 45000)]);
      // Mantener solo las últimas 20 filas de debug
      if (dbg.getLastRow() > 21) dbg.deleteRow(2);
    } catch(ignore) {}

    const data = body.data || {};
    let commandName = "";
    if (body.type === 2) {
      commandName = data.name;
    } else if (body.type === 3) {
      commandName = data.custom_id ? data.custom_id.split("|")[0] : "";
    }

    const user = body.member ? body.member.user : body.user;
    const roles = (body.member && body.member.roles) ? body.member.roles : [];
    const isAdmin = body.member ? (String(body.member.permissions) & 8) !== 0 : false;

    // Parsear opciones a dict plano
    const opts = {};
    const resolved = data.resolved || {};
    (data.options || []).forEach(opt => {
      opts[opt.name] = opt.value;
      const valStr = String(opt.value);

      if (resolved.channels) {
        const ch = resolved.channels[valStr] || resolved.channels[opt.value];
        if (ch) {
          opts[opt.name + "_name"] = ch.name || "";
          opts[opt.name + "_id"]   = String(ch.id || valStr);
        }
      }

      // Resolver usuarios (type 6)
      if (resolved.users) {
        const u = resolved.users[valStr] || resolved.users[opt.value];
        if (u) {
          opts[opt.name + "_user_id"]   = String(u.id || valStr);
          opts[opt.name + "_user_name"] = u.global_name || u.username || "";
        }
      }

      // Sobrescribir con nick del servidor si existe
      if (resolved.members) {
        const m = resolved.members[valStr] || resolved.members[opt.value];
        if (m && m.nick) {
          opts[opt.name + "_user_name"] = m.nick;
        }
      }
    });

    // Si es type 3 (botón), extraemos opts del custom_id
    // Formato esperado: "comando|key1=val1|key2=val2"
    if (body.type === 3 && data.custom_id) {
      const parts = data.custom_id.split("|");
      for (let i = 1; i < parts.length; i++) {
        const kv = parts[i].split("=");
        if (kv.length === 2) {
          opts[kv[0]] = kv[1];
        }
      }
    }

    // Extraer avatar del usuario que invocó el comando (prioridad: servidor > global)
    if (body.member && body.member.avatar) {
      opts["_user_avatar"] = "https://cdn.discordapp.com/guilds/" + String(body.guild_id) + "/users/" + String(user.id) + "/avatars/" + body.member.avatar + ".png?size=128";
    } else if (user && user.avatar) {
      opts["_user_avatar"] = "https://cdn.discordapp.com/avatars/" + String(user.id) + "/" + user.avatar + ".png?size=128";
    }

    // Normalizar campos comunes
    const cmdRecord = {
      command:           commandName,
      interaction_id:    body.id,
      interaction_token: body.token,
      user_id:           user ? String(user.id) : "",
      user_name:         user ? (user.global_name || user.username) : "",
      channel_id:        String(body.channel_id || ""),
      guild_id:          String(body.guild_id || ""),
      roles:             roles,
      is_admin:          isAdmin,
      options:           opts,
    };

    // ── NUBE ARCHITECTURE: Ejecutar comando de inmediato ──
    const result = executeCommand(cmdRecord);
    const extraActions = result.extraActions || [];
    delete result.extraActions; // Evitar que vaya en el payload de Discord

    // Retornamos el payload al Cloudflare Worker
    return jsonSimple({
      ok: true,
      responsePayload: result,
      extraActions: extraActions
    });

  } catch(err) {
    return jsonErr("handleDiscordInteraction: " + err.message);
  }
}

// ── LÓGICA DE COMANDOS EN LA NUBE ──
function executeCommand(cmd) {
  const name = cmd.command;
  
  if (name === "helps") {
    return {
      embeds: [{
        title: "🌸 Guía de Comandos — Bloom Scans Staff",
        description: "Aquí tienes todos los comandos disponibles para el staff.\nUsa cada comando con `/` en Discord.",
        color: 0xff7eb3,
        fields: [
          {"name": "✔️ /terminado", "value": "Marca tus asignaciones como terminadas.", "inline": false},
          {"name": "📊 /trabajos", "value": "Ver tus capítulos completados del mes actual.", "inline": false},
          {"name": "🔍 /ver_asignacion", "value": "Consulta quién está asignado a un capítulo.", "inline": false},
          {"name": "🎯 /asignarme", "value": "Asígnate automáticamente a un capítulo disponible.", "inline": false},
          {"name": "📌 /mis_asignaciones", "value": "Muestra todas tus tareas pendientes.", "inline": false},
          {"name": "🏆 /creditos", "value": "Muestra el staff que trabajó en un capítulo.", "inline": false},
          {"name": "🏅 /posibles_ganadores", "value": "Ranking del staff más activo del mes.", "inline": false},
          {"name": "✨ /apodo", "value": "Configura tu nombre artístico para créditos.", "inline": false},
          {"name": "🚫 /abandonar", "value": "Libera una tarea que tenías asignada.", "inline": false},
          {"name": "😴 /ausente", "value": "Registra una ausencia temporal (días + motivo).", "inline": false},
          {"name": "✅ /cancelar_ausencia", "value": "Cancela tu ausencia si regresaste antes.", "inline": false},
          {"name": "📧 /registrar_correo", "value": "Registra tu correo para acceso a Drive.", "inline": false},
        ],
        footer: { text: "Bloom Scans • Staff Bot (Cloud Edition) • /helps" }
      }],
      flags: 64
    };
  }
  
  if (name === "mis_asignaciones") {
    const userId = cmd.user_id;
    const userName = cmd.user_name;
    const sheet = getSheet("Asignaciones");
    if (!sheet) return { content: "❌ Error: Hoja Asignaciones no encontrada", flags: 64 };
    
    const data = sheet.getDataRange().getValues();
    if (data.length < 2) return {
      embeds: [{
        title: "📋 Mis Asignaciones",
        description: "No tienes capítulos asignados actualmente. ¡Buen trabajo! 🎉",
        color: 0x2ecc71,
        footer: { text: "Bloom Scans" }
      }],
      flags: 64
    };
    
    const headers = data[0];
    let mis = [];
    const apodoUser = getApodoValue(userId, userName);
    const apodoLower = apodoUser.toLowerCase();

    data.slice(1).forEach(row => {
      let r = {};
      headers.forEach((h, i) => r[h] = row[i]);
      if (matchesUser(r, userId, userName, apodoLower) && String(r.Estado).trim().toLowerCase() !== "terminado") {
        mis.push(r);
      }
    });
    
    if (mis.length === 0) {
      return {
        embeds: [{
          title: "📋 Mis Asignaciones",
          description: "No tienes capítulos asignados actualmente. ¡Buen trabajo! 🎉",
          color: 0x2ecc71,
          footer: { text: "Bloom Scans" }
        }],
        flags: 64
      };
    }
    
    // Agrupar por proyecto
    let proyectos = {};
    for (let f of mis) {
        let proy = f.Proyecto || "Sin proyecto";
        if (!proyectos[proy]) proyectos[proy] = [];
        let cap = f.Capitulo || f["Capítulo"] || "?";
        let tarea = f.Tarea || "?";
        let estado = String(f.Estado || "").trim();
        let icono = estado.toLowerCase() === "en proceso" ? "⌛" : "📌";
        proyectos[proy].push(`> ${icono} **Cap ${cap}** — \`${tarea}\`  *( ${estado} )*`);
    }

    let fields = [];
    for (let proy in proyectos) {
        let items = proyectos[proy];
        fields.push({
            name: `📘 ${proy}`,
            value: limitDiscordText(items.slice(0, 10).join("\n") + (items.length > 10 ? "\n> ..." : ""), 1000),
            inline: false
        });
        if (fields.length >= 25) break;
    }
    
    const avatarUrl = cmd.options && cmd.options._user_avatar ? cmd.options._user_avatar : null;
    let embed = {
      title: `🌸 Panel de Asignaciones | ${userName}`,
      description: "Tus tareas actuales ordenadas por proyecto:",
      color: 0xffb6c1,
      fields: fields,
      footer: { text: "Bloom Scans • Nube Edition" }
    };
    
    if (avatarUrl) {
      embed.thumbnail = { url: avatarUrl };
    }
    
    return {
      embeds: [embed],
      flags: 64
    };
  }

  if (name === "terminado") {
    // Definido en el nuevo archivo comandos_nube.gs
    return cmdTerminado(cmd);
  }

  if (name === "asignar") {
    // Definido en el nuevo archivo comandos_nube.gs
    return cmdAsignar(cmd);
  }
  
  if (name === "abandonar") return cmdAbandonar(cmd);
  if (name === "cancelar_asignacion") return cmdCancelarAsignacion(cmd);
  if (name === "trabajos") return cmdTrabajos(cmd);
  if (name === "ver_asignacion") return cmdVerAsignacion(cmd);
  if (name === "creditos") return cmdCreditos(cmd);
  if (name === "posibles_ganadores") return cmdPosiblesGanadores(cmd);
  if (name === "apodo") return cmdApodo(cmd);
  if (name === "registrar_correo") return cmdRegistrarCorreo(cmd);
  if (name === "ausente") return cmdAusente(cmd);
  if (name === "cancelar_ausencia") return cmdCancelarAusencia(cmd);
  if (name === "quitar_staff") return cmdQuitarStaff(cmd);
  if (name === "progreso" || name === "estado_serie") return cmdProgreso(cmd);
  if (name === "mi_perfil") return cmdMiPerfil(cmd);
  if (name === "limpiar_inactivos") return cmdLimpiarInactivos(cmd);
  if (name === "ticket") return cmdTicket(cmd);
  if (name === "dar_bienvenida") return cmdDarBienvenida(cmd);
  if (name === "finalizar_mes") return cmdFinalizarMes(cmd);
  if (name === "asignarme") return cmdAsignarme(cmd);
  if (name === "agregar_serie") return cmdAgregarSerie(cmd);
  if (name === "actualizar_drive") return cmdActualizarDrive(cmd);
  if (name === "refrescar_asignaciones") return cmdRefrescarAsignaciones(cmd);
  if (name === "mis_trabajos") return cmdMisTrabajos(cmd);
  if (name === "asignaciones_usuario") return cmdAsignacionesUsuario(cmd);

  return {
    content: "❌ Comando `/" + name + "` en proceso de migración a la nube. ¡Dame unos minutos para terminar de programarlo!",
    flags: 64
  };
}

// ─────────────────────────────────────────────────────────────
//  DISCORD AUTOCOMPLETE
// ─────────────────────────────────────────────────────────────
function handleAutocomplete(body) {
  try {
    const data = body.data || {};
    const options = data.options || [];
    
    let focusedOption = null;
    for (let opt of options) {
      if (opt.focused) { focusedOption = opt; break; }
      if (opt.options) {
        for (let subOpt of opt.options) {
          if (subOpt.focused) { focusedOption = subOpt; break; }
        }
      }
    }
    
    if (focusedOption && (focusedOption.name === "serie" || focusedOption.name === "canal" || focusedOption.name === "serie_name")) {
      const typed = String(focusedOption.value || "").toLowerCase().trim();
      
      let seriesNames = [];
      const cache = CacheService.getScriptCache();
      const cached = cache.get("series_names");
      if (cached) {
        seriesNames = JSON.parse(cached);
      } else {
        const sheet = getSheet("Series");
        const values = sheet.getDataRange().getValues();
        const nombreIdx = values.length > 0 ? values[0].indexOf("Nombre") : -1;
        if (nombreIdx >= 0) {
          for (let i = 1; i < values.length; i++) {
            if (values[i][nombreIdx]) seriesNames.push(String(values[i][nombreIdx]));
          }
        }
        cache.put("series_names", JSON.stringify(seriesNames), 300); // 5 min
      }
      
      let choices = [];
      for (let name of seriesNames) {
        if (name.toLowerCase().includes(typed)) {
          choices.push({ name: name.substring(0, 100), value: name.substring(0, 100) });
        }
        if (choices.length >= 25) break; // Discord limit
      }
      
      // Si no ha escrito nada y hay menos de 25 series, mostrar todas por defecto
      if (!typed && choices.length === 0 && seriesNames.length > 0) {
         choices = seriesNames.slice(0, 25).map(name => ({ name: name.substring(0, 100), value: name.substring(0, 100) }));
      }
      
      return jsonSimple({ ok: true, responsePayload: { type: 8, data: { choices: choices } } });
    }
    
    return jsonSimple({ ok: true, responsePayload: { type: 8, data: { choices: [] } } });
  } catch(e) {
    return jsonSimple({ ok: true, responsePayload: { type: 8, data: { choices: [] } } });
  }
}

// ─────────────────────────────────────────────────────────────
//  COLA DE COMANDOS — getPendingCommands / ackCommand
// ─────────────────────────────────────────────────────────────
function getPendingCommands() {
  const sheet = getSheet("PendingCmds");
  if (!sheet) return jsonOk([]);

  const data = sheet.getDataRange().getValues();
  if (data.length < 2) return jsonOk([]);

  const headers = data[0];
  const pending = [];

  data.slice(1).forEach((row, idx) => {
    const processed = row[11]; // columna "processed"
    if (processed) return;

    const cmd = {
      _id:               row[0],
      command:           row[1],
      interaction_id:    row[2],
      interaction_token: row[3],
      user_id:           String(row[4]),
      user_name:         row[5],
      channel_id:        String(row[6]),
      guild_id:          String(row[7]),
      roles:             JSON.parse(row[8] || "[]"),
      is_admin:          row[9],
      options:           JSON.parse(row[10] || "{}"),
    };
    pending.push(cmd);
  });

  return jsonOk(pending);
}

function ackCommand(cmdId) {
  const sheet = getSheet("PendingCmds");
  if (!sheet) return jsonErr("No sheet PendingCmds");
  const data = sheet.getDataRange().getValues();
  for (let i = 1; i < data.length; i++) {
    if (String(data[i][0]) === String(cmdId)) {
      sheet.deleteRow(i + 1); // Delete row to prevent sheet from growing indefinitely
      return jsonSimple({ ok: true });
    }
  }
  return jsonSimple({ ok: false, error: "cmdId not found" });
}

// ─────────────────────────────────────────────────────────────
//  SERIES
// ─────────────────────────────────────────────────────────────
function upsertSerie(serie) {
  const sheet = getSheet("Series");
  const data  = sheet.getDataRange().getValues();
  const headers = data[0];
  const nombreIdx = headers.indexOf("Nombre");
  const nombre = String(serie["Nombre"] || "").trim().toLowerCase();

  for (let i = 1; i < data.length; i++) {
    if (String(data[i][nombreIdx]).trim().toLowerCase() === nombre) {
      // Update
      const row = headers.map(h => serie[h] !== undefined ? serie[h] : data[i][headers.indexOf(h)]);
      sheet.getRange(i + 1, 1, 1, row.length).setValues([row]);
      CacheService.getScriptCache().remove("series_names");
      return jsonSimple({ ok: true, action: "updated" });
    }
  }
  // Insert
  sheet.appendRow(headers.map(h => serie[h] || ""));
  CacheService.getScriptCache().remove("series_names");
  return jsonSimple({ ok: true, action: "inserted" });
}

// ─────────────────────────────────────────────────────────────
//  ASIGNACIONES
// ─────────────────────────────────────────────────────────────
function addAsignacion(row) {
  const sheet = getSheet("Asignaciones");
  ensureHeaderColumn(sheet, "Fecha_Asignacion");
  sheet.appendRow([
    row.Proyecto, row.Capitulo, row.Tarea,
    row.Usuario, row.Estado, asTextId(row.ID_Usuario),
    row.Fecha_Asignacion || row.Fecha || timestampNowIso()
  ]);
  
  // Otorgar acceso a Drive automáticamente
  try {
    const correos = getCorreos(row.ID_Usuario);
    if (correos.length > 0) {
      const seriesSheet = getSheet("Series");
      const sData = seriesSheet.getDataRange().getValues();
      const sHeaders = sData[0];
      const nombreIdx = sHeaders.indexOf("Nombre");
      const folderIdx = sHeaders.indexOf("Folder_ID");
      let folderId = "";
      if (nombreIdx >= 0 && folderIdx >= 0) {
        for (let i = 1; i < sData.length; i++) {
          if (String(sData[i][nombreIdx]).toLowerCase() === String(row.Proyecto).toLowerCase()) {
            folderId = String(sData[i][folderIdx]);
            break;
          }
        }
      }
      if (folderId) {
        const folder = DriveApp.getFolderById(folderId);
        correos.forEach(c => {
          try { folder.addEditor(c); } catch(e) {}
        });
      }
    }
  } catch(e) {}

  return jsonSimple({ ok: true });
}

function addAsignacionesBatch(rows) {
  const sheet = getSheet("Asignaciones");
  if (!rows || rows.length === 0) return jsonSimple({ ok: true });
  ensureHeaderColumn(sheet, "Fecha_Asignacion");
  
  const values = rows.map(row => [
    row.Proyecto, row.Capitulo, row.Tarea,
    row.Usuario, row.Estado, asTextId(row.ID_Usuario),
    row.Fecha_Asignacion || row.Fecha || timestampNowIso()
  ]);
  
  sheet.getRange(sheet.getLastRow() + 1, 1, values.length, 7).setValues(values);
  
  // Otorgar acceso a Drive a todos
  try {
    const seriesSheet = getSheet("Series");
    const sData = seriesSheet.getDataRange().getValues();
    const sHeaders = sData[0];
    const nombreIdx = sHeaders.indexOf("Nombre");
    const folderIdx = sHeaders.indexOf("Folder_ID");
    
    // Agrupar correos por carpeta
    rows.forEach(row => {
      const correos = getCorreos(row.ID_Usuario);
      if (correos.length > 0 && nombreIdx >= 0 && folderIdx >= 0) {
        let folderId = "";
        for (let i = 1; i < sData.length; i++) {
          if (String(sData[i][nombreIdx]).toLowerCase() === String(row.Proyecto).toLowerCase()) {
            folderId = String(sData[i][folderIdx]);
            break;
          }
        }
        if (folderId) {
          const folder = DriveApp.getFolderById(folderId);
          correos.forEach(c => {
            try { folder.addEditor(c); } catch(e) {}
          });
        }
      }
    });
  } catch(e) {}

  return jsonSimple({ ok: true });
}

function updateAsignacionEstado(rowId, estado) {
  const sheet  = getSheet("Asignaciones");
  const rowNum = parseInt(rowId);
  if (rowNum >= 2 && rowNum <= sheet.getLastRow()) {
    // Estado está en col 5 (índice 4, 0-based)
    sheet.getRange(rowNum, 5).setValue(estado);
    return jsonSimple({ ok: true });
  }
  return jsonSimple({ ok: false, error: "Row not found: " + rowId });
}

function deleteAsignacion(rowId) {
  const sheet  = getSheet("Asignaciones");
  const rowNum = parseInt(rowId);
  if (rowNum >= 2) {
    sheet.deleteRow(rowNum);
    return jsonSimple({ ok: true });
  }
  return jsonSimple({ ok: false, error: "Invalid rowId" });
}

function uniqueSheetName(ss, baseName) {
  const safeBase = String(baseName).substring(0, 80);
  let name = safeBase;
  let i = 2;
  while (ss.getSheetByName(name)) {
    name = (safeBase + "_" + i).substring(0, 99);
    i++;
  }
  return name;
}

function writeTableValues(sheet, headers, values) {
  const rows = [headers].concat(values || []);
  sheet.clearContents();
  sheet.getRange(1, 1, rows.length, headers.length).setValues(rows);
}

function backupSheetData(ss, sheet, backupBaseName) {
  const data = sheet.getDataRange().getValues();
  const backupName = uniqueSheetName(ss, backupBaseName);
  const backup = ss.insertSheet(backupName);
  if (data.length > 0 && data[0].length > 0) {
    backup.getRange(1, 1, data.length, data[0].length).setValues(data);
  }
  return backupName;
}

function replaceSheetContentsSafely(sheetName, headers, values) {
  if (!Array.isArray(values)) return jsonErr(sheetName + ": filas debe ser un array");
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = ss.getSheetByName(sheetName);
  if (!sheet) return jsonErr("Hoja no existe: " + sheetName);

  const stamp = Utilities.formatDate(new Date(), "America/Argentina/Buenos_Aires", "yyyyMMdd_HHmmss");
  const stagingName = uniqueSheetName(ss, "_staging_" + sheetName + "_" + stamp);
  const staging = ss.insertSheet(stagingName);
  try {
    writeTableValues(staging, headers, values);
    if (staging.getLastRow() !== values.length + 1) {
      throw new Error("staging incompleto: " + staging.getLastRow() + " filas");
    }
    const backupName = backupSheetData(ss, sheet, "Backup_" + sheetName + "_" + stamp);
    writeTableValues(sheet, headers, values);
    ss.deleteSheet(staging);
    return jsonSimple({ ok: true, backup: backupName, rows: values.length });
  } catch(err) {
    return jsonErr("replace " + sheetName + " cancelado: " + err.message + ". Staging: " + stagingName);
  }
}

function syncAsignaciones(filas) {
  const safeHeaders = BASE_SHEET_HEADERS.Asignaciones;
  const safeValues = (filas || []).map(f => [
    f.Proyecto || "", f["Capítulo"] || f["CapÃ­tulo"] || f.Capitulo || "",
    f.Tarea || "", f.Usuario || "", f.Estado || "",
    asTextId(f.ID_Usuario || f.user_id || ""),
    f.Fecha_Asignacion || f.Fecha || timestampNowIso()
  ]);
  return replaceSheetContentsSafely("Asignaciones", safeHeaders, safeValues);
}

// ─────────────────────────────────────────────────────────────
//  REGISTROS
// ─────────────────────────────────────────────────────────────
function addRegistro(row) {
  const sheet = getSheet("Registro");
  sheet.appendRow([
    row.Fecha, row.Usuario, row.Proyecto,
    row.Capitulo, row.Tarea, asTextId(row.ID_Usuario)
  ]);
  return jsonSimple({ ok: true });
}

function replaceRegistros(filas) {
  const safeHeaders = BASE_SHEET_HEADERS.Registro;
  const safeValues = (filas || []).map(f => [
    f.Fecha || "", f.Usuario || "", f.Proyecto || "",
    f["Capítulo"] || f["CapÃ­tulo"] || f.Capitulo || "", f.Tarea || "", asTextId(f.ID_Usuario || f.user_id || "")
  ]);
  return replaceSheetContentsSafely("Registro", safeHeaders, safeValues);
}

// ─────────────────────────────────────────────────────────────
//  TABLA DE SERIE (hojas por responsable)
// ─────────────────────────────────────────────────────────────
function getTablaSerie(serieName, hojaName) {
  const ss    = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = ss.getSheetByName(hojaName);
  if (!sheet) return jsonOk([]);

  const data = sheet.getDataRange().getValues();
  if (data.length === 0) return jsonOk([]);

  // Buscar el bloque de la serie (fila 1 = títulos de series)
  const fila0 = data[0];
  let startCol = -1;
  for (let c = 0; c < fila0.length; c++) {
    if (String(fila0[c]).trim().toLowerCase() === String(serieName).trim().toLowerCase()) {
      startCol = c;
      break;
    }
  }
  if (startCol < 0) return jsonOk([]);

  const HEADERS = ["Cap","Idioma","RAW","Clean","Traduccion","Edicion","Recorte","Subido_Web","Fecha_RAW"];
  const filas = [];
  for (let r = 4; r < data.length; r++) {
    const cap = String(data[r][startCol] || "").trim();
    if (!cap) break;
    const obj = {};
    HEADERS.forEach((h, i) => obj[h] = String(data[r][startCol + i] || "").trim());
    filas.push(obj);
  }
  return jsonOk(filas);
}

function writeTablaSerie(serieName, hojaName, filas) {
  const ss    = SpreadsheetApp.openById(SPREADSHEET_ID);
  let sheet   = ss.getSheetByName(hojaName);
  if (!sheet) {
    sheet = ss.insertSheet(hojaName);
  }

  const data  = sheet.getDataRange().getValues();
  const fila0 = data.length > 0 ? data[0] : [];
  let startCol = -1;
  for (let c = 0; c < fila0.length; c++) {
    if (String(fila0[c]).trim().toLowerCase() === String(serieName).trim().toLowerCase()) {
      startCol = c + 1; // 1-based
      break;
    }
  }

  const HEADERS = ["Cap","Idioma","RAW","Clean","Traduccion","Edicion","Recorte","Subido_Web","Fecha_RAW"];

  if (startCol < 0) {
    // Crear bloque nuevo al final
    startCol = fila0.length + 1;
    if (sheet.getMaxColumns() < startCol + HEADERS.length - 1) {
      sheet.insertColumnsAfter(sheet.getMaxColumns(), HEADERS.length);
    }
  }

  // Encabezados del bloque
  sheet.getRange(1, startCol).setValue(serieName);
  sheet.getRange(4, startCol, 1, HEADERS.length).setValues([HEADERS]);

  // Datos
  const rows = filas.map(f => HEADERS.map(h => f[h] || ""));
  if (rows.length > 0) {
    // Limpiar filas antiguas primero
    const lastRow = sheet.getLastRow();
    if (lastRow >= 5) {
      sheet.getRange(5, startCol, lastRow - 4, HEADERS.length).clearContent();
    }
    sheet.getRange(5, startCol, rows.length, HEADERS.length).setValues(rows);
  }

  return jsonSimple({ ok: true });
}

function updateEstadoTareaSerie(serieName, hojaName, capitulo, columna, valor) {
  const ss    = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = ss.getSheetByName(hojaName);
  if (!sheet) return jsonSimple({ ok: false, error: "Hoja no existe: " + hojaName });

  const data  = sheet.getDataRange().getValues();
  const fila0 = data[0] || [];
  let startCol = -1;
  for (let c = 0; c < fila0.length; c++) {
    if (String(fila0[c]).trim().toLowerCase() === String(serieName).trim().toLowerCase()) {
      startCol = c;
      break;
    }
  }
  if (startCol < 0) return jsonSimple({ ok: false, error: "Serie no encontrada en hoja" });

  const HEADERS = ["Cap","Idioma","RAW","Clean","Traduccion","Edicion","Recorte","Subido_Web","Fecha_RAW"];
  const colOffset = HEADERS.indexOf(columna);
  if (colOffset < 0) return jsonSimple({ ok: false, error: "Columna inválida: " + columna });

  const capNorm = _extraerNumCap(String(capitulo));
  for (let r = 4; r < data.length; r++) {
    const cellCap = _extraerNumCap(String(data[r][startCol] || ""));
    if (!cellCap) break;
    if (cellCap === capNorm) {
      sheet.getRange(r + 1, startCol + colOffset + 1).setValue(valor);
      return jsonSimple({ ok: true });
    }
  }
  return jsonSimple({ ok: false, error: "Capítulo no encontrado: " + capitulo });
}

function updateEstadoTareaSerieBatch(serieName, hojaName, capitulos, columna, valor, upsertMissing) {
  const ss    = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = ss.getSheetByName(hojaName);
  if (!sheet) return jsonSimple({ ok: false, error: "Hoja no existe: " + hojaName });

  const data  = sheet.getDataRange().getValues();
  const fila0 = data[0] || [];
  let startCol = -1;
  for (let c = 0; c < fila0.length; c++) {
    if (String(fila0[c]).trim().toLowerCase() === String(serieName).trim().toLowerCase()) {
      startCol = c;
      break;
    }
  }
  if (startCol < 0) return jsonSimple({ ok: false, error: "Serie no encontrada" });

  const HEADERS = ["Cap","Idioma","RAW","Clean","Traduccion","Edicion","Recorte","Subido_Web","Fecha_RAW"];
  const colOffset = HEADERS.indexOf(columna);
  if (colOffset < 0) return jsonSimple({ ok: false, error: "Columna inválida" });

  const capsNorm = capitulos.map(c => _extraerNumCap(String(c)));
  let capsNoEncontrados = [...capsNorm];
  
  let r = 4;
  for (; r < data.length; r++) {
    const rawVal = String(data[r][startCol] || "");
    if (!rawVal) break; // Fin de la lista de capítulos
    const cellCap = _extraerNumCap(rawVal);
    if (!cellCap) continue;
    
    let idx = capsNoEncontrados.indexOf(cellCap);
    if (idx !== -1) {
      sheet.getRange(r + 1, startCol + colOffset + 1).setValue(valor);
      capsNoEncontrados.splice(idx, 1);
    }
  }
  
  // Si quedaron capítulos sin encontrar, los agregamos al final de la columna automáticamente
  if (capsNoEncontrados.length > 0 && upsertMissing === true) {
    for (let cap of capsNoEncontrados) {
      sheet.getRange(r + 1, startCol + 1).setValue(cap);
      sheet.getRange(r + 1, startCol + colOffset + 1).setValue(valor);
      r++;
    }
  }
  
  return jsonSimple({ ok: capsNoEncontrados.length === 0 || upsertMissing === true, faltantes: capsNoEncontrados, agregados: upsertMissing === true ? capsNoEncontrados : [] });
}

function _extraerNumCap(nombre) {
  nombre = nombre.replace(/\.[a-zA-Z0-9]+$/, '').trim();
  const m = nombre.match(/(\d+(?:[.\-]\d+)?)/);
  return m ? m[1].replace('.', '-') : nombre;
}

// ─────────────────────────────────────────────────────────────
//  DRIVE
// ─────────────────────────────────────────────────────────────
function listarDrive(folderId, soloCarpetas) {
  try {
    const folder = DriveApp.getFolderById(folderId);
    const items  = [];

    if (soloCarpetas) {
      const it = folder.getFolders();
      while (it.hasNext()) {
        const f = it.next();
        items.push({ id: f.getId(), name: f.getName() });
      }
    } else {
      const it = folder.getFiles();
      while (it.hasNext()) {
        const f = it.next();
        items.push({ id: f.getId(), name: f.getName() });
      }
    }
    return jsonOk(items);
  } catch(err) {
    return jsonOk([]); // Folder no accesible → retorna vacío
  }
}

// ─────────────────────────────────────────────────────────────
//  USUARIOS / AUSENCIAS
// ─────────────────────────────────────────────────────────────
function getUsuario(userId) {
  const sheet = getSheet("Usuarios");
  if (!sheet) return jsonOk({});
  const data = sheet.getDataRange().getValues();
  const targetId = normalizeIdFromSheet(userId);
  for (let i = 1; i < data.length; i++) {
    if (normalizeIdFromSheet(data[i][0]) === targetId) {
      return jsonOk({ user_id: data[i][0], last_msg: data[i][1], ausencia_hasta: data[i][2] });
    }
  }
  return jsonOk({});
}

function setActividad(userId, ts) {
  const sheet = getSheet("Usuarios");
  const data  = sheet.getDataRange().getValues();
  const targetId = normalizeIdFromSheet(userId);
  for (let i = 1; i < data.length; i++) {
    if (normalizeIdFromSheet(data[i][0]) === targetId) {
      sheet.getRange(i + 1, 2).setValue(ts);
      return jsonSimple({ ok: true });
    }
  }
  sheet.appendRow([asTextId(userId), ts, ""]);
  return jsonSimple({ ok: true });
}

function setAusencia(userId, fechaFin) {
  const sheet = getSheet("Usuarios");
  const data  = sheet.getDataRange().getValues();
  const targetId = normalizeIdFromSheet(userId);
  for (let i = 1; i < data.length; i++) {
    if (normalizeIdFromSheet(data[i][0]) === targetId) {
      sheet.getRange(i + 1, 3).setValue(fechaFin);
      return jsonSimple({ ok: true });
    }
  }
  sheet.appendRow([asTextId(userId), "", fechaFin]);
  return jsonSimple({ ok: true });
}

function clearAusencia(userId) {
  const sheet = getSheet("Usuarios");
  const data  = sheet.getDataRange().getValues();
  const targetId = normalizeIdFromSheet(userId);
  for (let i = 1; i < data.length; i++) {
    if (normalizeIdFromSheet(data[i][0]) === targetId) {
      sheet.getRange(i + 1, 3).setValue("");
      return jsonSimple({ ok: true });
    }
  }
  return jsonSimple({ ok: true });
}

function getStaffInactividad(diasLimite) {
  const sheet = getSheet("Usuarios");
  if (!sheet) return jsonOk([]);
  const data = sheet.getDataRange().getValues();
  const ahora = new Date();
  const limite = new Date(ahora.getTime() - diasLimite * 86400000);
  const inactivos = [];

  for (let i = 1; i < data.length; i++) {
    const uid       = normalizeIdFromSheet(data[i][0]);
    const lastMsg   = data[i][1];
    const ausencia  = data[i][2];

    // Si tiene ausencia activa, saltar
    if (ausencia) {
      const fechaAus = new Date(ausencia);
      if (ahora < fechaAus) continue;
    }

    if (!lastMsg) {
      inactivos.push({ user_id: uid, last_msg: "Nunca" });
    } else {
      const lastDt = new Date(lastMsg);
      if (lastDt < limite) {
        inactivos.push({ user_id: uid, last_msg: String(lastMsg) });
      }
    }
  }
  return jsonOk(inactivos);
}

// ─────────────────────────────────────────────────────────────
//  APODOS
// ─────────────────────────────────────────────────────────────
/**
 * Obtiene el apodo directamente como string para uso interno
 */
function getApodoValue(userId, fallbackName) {
  const sheet = getSheet("Apodos");
  if (!sheet) return fallbackName || "";
  const data = sheet.getDataRange().getValues();
  const targetId = normalizeIdFromSheet(userId);
  for (let i = 1; i < data.length; i++) {
    if (normalizeIdFromSheet(data[i][0]) === targetId) {
      return data[i][1];
    }
  }
  return fallbackName || "";
}

/**
 * Endpoint para obtener apodo via JSON
 */
function getApodoEndpoint(userId) {
  const apodo = getApodoValue(userId);
  return jsonSimple({ ok: true, apodo: apodo });
}

function setApodo(userId, apodo) {
  const sheet = getSheet("Apodos");
  const data  = sheet.getDataRange().getValues();
  const targetId = normalizeIdFromSheet(userId);
  for (let i = 1; i < data.length; i++) {
    if (normalizeIdFromSheet(data[i][0]) === targetId) {
      sheet.getRange(i + 1, 2).setValue(apodo);
      return jsonSimple({ ok: true });
    }
  }
  sheet.appendRow([asTextId(userId), apodo]);
  return jsonSimple({ ok: true });
}

// ─────────────────────────────────────────────────────────────
//  TICKET COUNTER
// ─────────────────────────────────────────────────────────────
function siguienteTicket() {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
  } catch(e) {
    return jsonErr("Sistema ocupado generando ticket");
  }
  try {
    const sheet = getSheet("Config");
    const data  = sheet.getDataRange().getValues();
    for (let i = 1; i < data.length; i++) {
      if (String(data[i][0]) === "ticket_count") {
        const nuevo = (parseInt(data[i][1]) || 0) + 1;
        sheet.getRange(i + 1, 2).setValue(nuevo);
        return jsonSimple({ ok: true, ticketNum: nuevo });
      }
    }
    sheet.appendRow(["ticket_count", 1]);
    return jsonSimple({ ok: true, ticketNum: 1 });
  } finally {
    lock.releaseLock();
  }
}

// ─────────────────────────────────────────────────────────────
//  BACKUP / DUPLICAR HOJA REGISTRO
// ─────────────────────────────────────────────────────────────
function duplicarHojaRegistro(nombre, filas) {
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  let hoja = ss.getSheetByName(nombre);
  if (hoja) {
    hoja.clearContents();
  } else {
    hoja = ss.insertSheet(nombre);
  }
  const headers = ["Fecha", "Usuario", "Proyecto", "Capítulo", "Tarea", "ID_Usuario"];
  hoja.appendRow(headers);
  filas.forEach(f => hoja.appendRow([
    f.Fecha || "", f.Usuario || "", f.Proyecto || "",
    f["Capítulo"] || f.Capitulo || "", f.Tarea || "", asTextId(f.ID_Usuario || f.user_id || "")
  ]));
  return jsonSimple({ ok: true });
}

// ─────────────────────────────────────────────────────────────
//  CORREOS Y DRIVE PERMISSIONS
// ─────────────────────────────────────────────────────────────
function setCorreo(userId, email) {
  let sheet = getSheet("Correos");
  if (!sheet) {
    const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
    sheet = ss.insertSheet("Correos");
    sheet.appendRow(["ID_Usuario", "Correos"]);
  }
  const data = sheet.getDataRange().getValues();
  const targetId = normalizeIdFromSheet(userId);
  for (let i = 1; i < data.length; i++) {
    if (normalizeIdFromSheet(data[i][0]) === targetId) {
      let arr = String(data[i][1] || "").split(",").map(c => c.trim()).filter(c => c);
      if (!arr.includes(email)) arr.push(email);
      sheet.getRange(i + 1, 2).setValue(arr.join(", "));
      return jsonSimple({ ok: true, msg: "Correo añadido exitosamente." });
    }
  }
  sheet.appendRow([asTextId(userId), email]);
  return jsonSimple({ ok: true, msg: "Correo registrado exitosamente." });
}

function getCorreos(userId) {
  const sheet = getSheet("Correos");
  if (!sheet) return [];
  const data = sheet.getDataRange().getValues();
  const targetId = normalizeIdFromSheet(userId);
  for (let i = 1; i < data.length; i++) {
    if (normalizeIdFromSheet(data[i][0]) === targetId) {
      return String(data[i][1]).split(",").map(c => c.trim()).filter(c => c);
    }
  }
  return [];
}

function quitarStaff(userId) {
  const asigSheet = getSheet("Asignaciones");
  const aData = asigSheet.getDataRange().getValues();
  const proyectos = new Set();
  
  // Borrar todas las asignaciones del usuario
  for (let i = aData.length - 1; i >= 1; i--) {
    if (normalizeIdFromSheet(aData[i][5]) === normalizeIdFromSheet(userId)) {
      proyectos.add(aData[i][0]);
      asigSheet.deleteRow(i + 1);
    }
  }

  // Revocar acceso a Drive de las series que tenía
  const correos = getCorreos(userId);
  if (correos.length > 0 && proyectos.size > 0) {
    const seriesSheet = getSheet("Series");
    const sData = seriesSheet.getDataRange().getValues();
    const sHeaders = sData[0];
    const nombreIdx = sHeaders.indexOf("Nombre");
    const folderIdx = sHeaders.indexOf("Folder_ID");

    if (nombreIdx >= 0 && folderIdx >= 0) {
      proyectos.forEach(proy => {
        let folderId = "";
        for (let i = 1; i < sData.length; i++) {
          if (String(sData[i][nombreIdx]).toLowerCase() === String(proy).toLowerCase()) {
            folderId = String(sData[i][folderIdx]);
            break;
          }
        }
        if (folderId) {
          try {
            const folder = DriveApp.getFolderById(folderId);
            correos.forEach(c => {
              try { folder.removeEditor(c); } catch(e) {}
            });
          } catch(e) {}
        }
      });
    }
  }
  return jsonSimple({ ok: true });
}

// ─────────────────────────────────────────────────────────────
//  PROXY: Enviar followup a Discord en nombre del ESP32
//  El ESP32 no puede hacer PATCH a discord.com (limitación TLS de MicroPython).
//  En su lugar, envía el payload a este endpoint y GAS lo reenvía.
// ─────────────────────────────────────────────────────────────
function logActionFailure(failure) {
  try {
    const f = failure || {};
    const sheet = getSheet("ActionFailures");
    sheet.appendRow([
      new Date().toISOString(),
      String(f.command || ""),
      normalizeIdFromSheet(f.user_id || ""),
      String(f.url || "").substring(0, 500),
      String(f.status || ""),
      String(f.message || "").substring(0, 1000)
    ]);
    return jsonSimple({ ok: true });
  } catch(err) {
    return jsonErr("logActionFailure error: " + err.message);
  }
}

function sendFollowup(interactionToken, payload) {
  try {
    if (!interactionToken || !payload) {
      return jsonErr("sendFollowup: token y payload requeridos");
    }

    const url = "https://discord.com/api/v10/webhooks/" + APPLICATION_ID + "/" + interactionToken + "/messages/@original";

    const options = {
      method: "patch",
      contentType: "application/json",
      headers: {
        "Authorization": "Bot " + DISCORD_BOT_TOKEN,
      },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true,
    };

    const resp = UrlFetchApp.fetch(url, options);
    const code = resp.getResponseCode();

    if (code >= 200 && code < 300) {
      return jsonSimple({ ok: true, status: code });
    } else {
      return jsonErr("Discord API error " + code + ": " + resp.getContentText().substring(0, 200));
    }
  } catch(err) {
    return jsonErr("sendFollowup error: " + err.message);
  }
}

