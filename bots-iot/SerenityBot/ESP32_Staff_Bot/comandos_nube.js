// ─────────────────────────────────────────────────────────────
// comandos_nube.gs — Lógica de los Comandos en la Nube
// ─────────────────────────────────────────────────────────────

const CANALES_TERMINADOS = [
  "1458345407959797902",
  "1458345512624459951",
  "1458345602151878767",
];
const CANAL_COORDINADORES_ID = "1483864769239978064";
const DISCORD_BOT_TOKEN_NUBE = "MTYOUR_DISCORD_BOT_TOKEN";

const OWNER_SHEET_TITLES = {
  "1154257480734490664": "Itsuki",
  "643559580990701596":  "Kato",
  "1203552106041180220": "Celeste",
  "1123475061664387093": "El pirateador"
};

function parsearCapitulos(capStr) {
  let caps = [];
  let partes = String(capStr).split(',');
  for (let p of partes) {
    p = p.trim();
    if (p.includes('-')) {
      let rng = p.split('-');
      if (rng.length === 2 && !isNaN(rng[0]) && !isNaN(rng[1])) {
        let inicio = parseFloat(rng[0]);
        let fin = parseFloat(rng[1]);
        if (inicio <= fin) {
          for (let i = inicio; i <= fin; i++) caps.push(String(i));
        } else {
          caps.push(p);
        }
      } else {
        caps.push(p);
      }
    } else if (p !== '') {
      caps.push(p);
    }
  }
  return [...new Set(caps)];
}

function timestampNowIso() {
  const now = new Date();
  return now.toISOString().replace('T', ' ').substring(0, 19);
}

// matchesUser() está definida globalmente en Code.gs - no duplicar aquí


/**
 * Obtiene año y mes de un valor que puede ser Date o String
 */
function getYearMonth(value) {
  if (value instanceof Date) {
    return { year: value.getFullYear(), month: value.getMonth() + 1 };
  }
  const s = String(value || "");
  const m = s.match(/^(\d{4})[-\/](\d{1,2})/);
  if (m) {
    return { year: parseInt(m[1]) || 0, month: parseInt(m[2]) || 0 };
  }
  const parsed = new Date(s);
  if (!isNaN(parsed.getTime())) {
    return { year: parsed.getFullYear(), month: parsed.getMonth() + 1 };
  }
  // Formato esperado: YYYY-MM-DD ...
  return { 
    year: parseInt(s.substring(0, 4)) || 0, 
    month: parseInt(s.substring(5, 7)) || 0 
  };
}

function sameUserId(a, b) {
  return normalizeIdFromSheet(a) === normalizeIdFromSheet(b);
}

// Helper: la hoja tiene "Capítulo" (con acento), pero el código usa "Capitulo"
function getCap(row) {
  return String(row.Capitulo || row["Capítulo"] || row["Cap\u00edtulo"] || "").trim();
}

function limitDiscordText(value, maxLen) {
  const s = String(value || "");
  if (s.length <= maxLen) return s || "\u200B";
  return s.substring(0, Math.max(0, maxLen - 20)) + "\n... (recortado)";
}

function normalizeSheetKey(value) {
  return String(value || "").trim().toLowerCase();
}

function getOwnerSheetName(adminId, adminNombre) {
  return OWNER_SHEET_TITLES[normalizeIdFromSheet(adminId)] || String(adminNombre || "").trim();
}

function getCandidateOwnerSheetsForSerie(ss, serieName) {
  const baseSheets = {
    Series: true, Asignaciones: true, Registro: true, Usuarios: true, Apodos: true,
    Config: true, PendingCmds: true, Correos: true, DebugLog: true, ActionFailures: true
  };
  const candidates = [];
  const seen = {};
  try {
    const seriesSheet = getSheet("Series");
    const data = seriesSheet.getDataRange().getValues();
    const headers = data[0] || [];
    const idxNombre = headers.indexOf("Nombre");
    const idxAdminId = headers.indexOf("Admin_ID");
    const idxAdminNombre = headers.indexOf("Admin_Nombre");
    for (let i = 1; i < data.length; i++) {
      if (normalizeSheetKey(data[i][idxNombre]) === normalizeSheetKey(serieName)) {
        const owner = getOwnerSheetName(data[i][idxAdminId], data[i][idxAdminNombre]);
        if (owner && !seen[owner]) {
          candidates.push(owner);
          seen[owner] = true;
        }
      }
    }
  } catch(e) {}
  Object.keys(OWNER_SHEET_TITLES).forEach(id => {
    const owner = OWNER_SHEET_TITLES[id];
    if (owner && !seen[owner]) {
      candidates.push(owner);
      seen[owner] = true;
    }
  });
  ss.getSheets().forEach(sheet => {
    const name = sheet.getName();
    if (!baseSheets[name] && !seen[name] && !name.startsWith("Registro_") && !name.startsWith("Backup_") && !name.startsWith("_staging_")) {
      candidates.push(name);
      seen[name] = true;
    }
  });
  return candidates;
}

function tareaAColumnaSheet(tarea) {
  const t = String(tarea).toLowerCase();
  if (t.includes('trad')) return 'Traduccion';
  if (t.includes('clean')) return 'Clean';
  if (t.includes('typ') || t.includes('edic')) return 'Edicion';
  if (t.includes('raw')) return 'RAW';
  if (t.includes('recort')) return 'Recorte';
  return 'Clean';
}

function actualizarEstadoTareaSerieBatchLocal(serieName, capitulos, tarea, valor) {
  const sheetSeries = getSheet("Series");
  if (!sheetSeries) return;
  const data = sheetSeries.getDataRange().getValues();
  let adminId = "";
  let adminNombre = "";
  
  for (let i = 1; i < data.length; i++) {
    if (String(data[i][0]).toLowerCase() === String(serieName).toLowerCase()) {
      adminId = String(data[i][7]);
      adminNombre = String(data[i][8]);
      break;
    }
  }
  
  let hoja = getOwnerSheetName(adminId, adminNombre) || "Sin responsable";
  let columna = tareaAColumnaSheet(tarea);
  return updateEstadoTareaSerieBatch(serieName, hoja, capitulos, columna, valor, false);
}

// ─────────────────────────────────────────────────────────────
// COMANDO: /terminado
// ─────────────────────────────────────────────────────────────
function cmdTerminado(cmd) {
  const lock = LockService.getScriptLock();
  let notifyArgs = null;
  try {
    lock.waitLock(10000);
  } catch(e) {
    return { content: "❌ El servidor está ocupado procesando otras tareas. Intenta de nuevo en unos segundos.", flags: 64 };
  }

  try {
    const channelId = cmd.channel_id;
    if (!CANALES_TERMINADOS.includes(String(channelId))) {
      return { content: "❌ Este comando solo se puede usar en los canales de 'Terminados'.", flags: 64 };
    }

    const userId = cmd.user_id;
    const userName = cmd.user_name;
    const opts = cmd.options;
    
    const rolVal = opts.rol || opts.tarea || "";
    const serieName = opts.serie_name || "";
    const serieChannelId = opts.serie_id || "";
    const capitulo = opts.capitulo || opts.cap || "";

    let capitulos = parsearCapitulos(capitulo);
    
    const sheetAsig = getSheet("Asignaciones");
    ensureHeaderColumn(sheetAsig, "Fecha_Asignacion");
    const dataAsig = sheetAsig.getDataRange().getValues();
    const headersAsig = dataAsig[0];
    
    const sheetReg = getSheet("Registro");
    const dataReg = sheetReg.getDataRange().getValues();
    const headersReg = dataReg[0];
    
    const fechaHoyStr = timestampNowIso();
    
    let exitos = [];
    let errores = [];
    
    const apodoVal = getApodoValue(userId, userName);
    const apodoLower = apodoVal.toLowerCase();

    for (let cap of capitulos) {
      let asignacion = null;
      let rowNum = -1;
      let asignacionTerminadaPrevia = null;
      
      for (let i = 1; i < dataAsig.length; i++) {
        let r = {};
        headersAsig.forEach((h, idx) => r[h] = dataAsig[i][idx]);
        
        if (String(r.Proyecto).toLowerCase() === String(serieName).toLowerCase() &&
            getCap(r) === String(cap) &&
            String(r.Tarea).toLowerCase() === String(rolVal).toLowerCase() &&
            matchesUser(r, userId, userName, apodoLower)) {
          
          if (String(r.Estado).toLowerCase() !== "terminado") {
            asignacion = r;
            rowNum = i + 1;
            break;
          } else {
            asignacionTerminadaPrevia = r;
          }
        }
      }
      
      if (!asignacion && !asignacionTerminadaPrevia) {
        errores.push(`Cap ${cap}: no estabas asignado`);
        continue;
      }
      if (!asignacion && asignacionTerminadaPrevia) {
        errores.push(`Cap ${cap}: ya estaba terminado`);
        continue;
      }
      
      let yaRegistrado = false;
      for (let i = 1; i < dataReg.length; i++) {
        let r = {};
        headersReg.forEach((h, idx) => r[h] = dataReg[i][idx]);
        
        if (String(r.Proyecto).toLowerCase() === String(serieName).toLowerCase() &&
            getCap(r) === String(cap) &&
            String(r.Tarea).toLowerCase() === String(rolVal).toLowerCase() &&
            matchesUser(r, userId, userName, apodoLower)) {
          yaRegistrado = true;
          break;
        }
      }
      
      if (!yaRegistrado) {
        sheetReg.appendRow([fechaHoyStr, apodoVal, serieName, cap, rolVal, asTextId(userId)]);
      }
      
      updateAsignacionEstado(rowNum, "Terminado");
      exitos.push(cap);
    }
    
    if (exitos.length > 0) {
      actualizarEstadoTareaSerieBatchLocal(serieName, exitos, rolVal, "✅");
      
      // Invalidar la caché del historial para el mes actual
      try {
        const ym = getYearMonth(new Date());
        CacheService.getScriptCache().remove(`mis_trabajos_${userId}_${ym.month}_${ym.year}`);
      } catch(e) {}
    }
    
    if (exitos.length === 0) {
      return { content: "❌ No se pudo completar ningún capítulo.\n" + errores.map(e => "> " + e).join("\n"), flags: 64 };
    }
    
    let capsStr = exitos.join(", ");
    let desc = `¡Excelente trabajo <@${userId}>! 🎉`;
    if (errores.length > 0) {
      desc += `\n\n⚠️ Algunos caps tuvieron problemas:\n` + errores.map(e => "> " + e).join("\n");
    }
  
  let embedUser = {
    title: `✅ ${exitos.length === 1 ? 'Trabajo' : exitos.length + ' Trabajos'} Terminado${exitos.length > 1 ? 's' : ''}`,
    description: desc,
    color: 0x57F287,
    fields: [
      { name: "📘 Proyecto", value: `<#${serieChannelId}>`, inline: true },
      { name: "📌 Capítulo(s)", value: `\`${capsStr}\``, inline: true },
      { name: "🛠️ Tarea Cumplida", value: `**${rolVal}**`, inline: false }
    ],
    footer: { text: "Bloom Scans • Usa /trabajos para ver tu acumulado." }
  };
  
    // Enviar a canal coordinadores (agrupado por serie)
    notifyArgs = [serieName, serieChannelId, userId, exitos, rolVal];
    
    return {
      embeds: [embedUser],
      flags: 64
    };
  } catch (err) {
    console.error("Error en cmdTerminado:", err);
    return { content: "❌ Error interno al procesar el comando: " + err.message, flags: 64 };
  } finally {
    lock.releaseLock();
    if (notifyArgs) {
      try {
        notificarCoordinadoresAgrupado.apply(null, notifyArgs);
      } catch(e) {
        console.error("Error notificando coordinadores:", e);
      }
    }
  }
}

function notificarCoordinadoresAgrupado(serieName, serieChannelId, userId, capitulos, rolVal) {
  const urlGet = `https://discord.com/api/v10/channels/${CANAL_COORDINADORES_ID}/messages?limit=20`;
  const optionsGet = {
    method: "GET",
    headers: { "Authorization": `Bot ${DISCORD_BOT_TOKEN_NUBE}` },
    muteHttpExceptions: true
  };
  
  let targetMsgId = null;
  let existingEmbed = null;
  
  try {
    const res = UrlFetchApp.fetch(urlGet, optionsGet);
    if (res.getResponseCode() === 200) {
      const msgs = JSON.parse(res.getContentText());
      for (let m of msgs) {
        if (m.author && m.author.bot && m.embeds && m.embeds.length > 0) {
          let em = m.embeds[0];
          if (em.title === "📢 Tareas terminadas" && em.fields) {
            let esMismaSerie = false;
            for (let f of em.fields) {
              if (f.name === "📘 Serie" && f.value.includes(serieChannelId)) {
                esMismaSerie = true;
                break;
              }
            }
            if (esMismaSerie) {
              targetMsgId = m.id;
              existingEmbed = em;
              break;
            }
          }
        }
      }
    }
  } catch(e) { console.error(e); }
  
  let capsStr = capitulos.join(", ");
  let nuevaLinea = `• <@${userId}> completó Cap(s) \`${capsStr}\` (**${rolVal}**)`;
  
  if (targetMsgId && existingEmbed) {
    let oldDesc = existingEmbed.description || "";
    let lineas = oldDesc.split('\n').filter(l => l.trim() !== "");
    lineas.push(nuevaLinea);
    
    // Mantener sólo los últimos 15
    if (lineas.length > 15) lineas = lineas.slice(lineas.length - 15);
    
    existingEmbed.description = lineas.join('\n');
    existingEmbed.timestamp = new Date().toISOString();
    
    const urlPatch = `https://discord.com/api/v10/channels/${CANAL_COORDINADORES_ID}/messages/${targetMsgId}`;
    try {
      UrlFetchApp.fetch(urlPatch, {
        method: "PATCH",
        headers: { "Authorization": `Bot ${DISCORD_BOT_TOKEN_NUBE}`, "Content-Type": "application/json" },
        payload: JSON.stringify({ embeds: [existingEmbed] }),
        muteHttpExceptions: true
      });
      return;
    } catch(e) { console.error(e); }
  }
  
  // Si no se encontró o falló el PATCH, hacemos POST
  let embedCoord = {
    title: "📢 Tareas terminadas",
    description: nuevaLinea,
    color: 0x3498db,
    fields: [
      { name: "📘 Serie", value: `<#${serieChannelId}>`, inline: false }
    ],
    footer: { text: "Bloom Scans • Revisión administrativa" },
    timestamp: new Date().toISOString()
  };
  
  const urlPost = `https://discord.com/api/v10/channels/${CANAL_COORDINADORES_ID}/messages`;
  try {
    UrlFetchApp.fetch(urlPost, {
      method: "POST",
      headers: { "Authorization": `Bot ${DISCORD_BOT_TOKEN_NUBE}`, "Content-Type": "application/json" },
      payload: JSON.stringify({ embeds: [embedCoord] }),
      muteHttpExceptions: true
    });
  } catch(e) {}
}

// ─────────────────────────────────────────────────────────────
// UTILIDADES VISUALES Y GAMIFICACIÓN
// ─────────────────────────────────────────────────────────────
function getPortadaUrl(serieName) {
  const sheet = getSheet("Series");
  if (!sheet) return null;
  const data = sheet.getDataRange().getValues();
  const headers = data[0];
  const idxNombre = headers.indexOf("Nombre");
  const idxPortada = headers.indexOf("Portada_URL");
  if (idxNombre < 0 || idxPortada < 0) return null;
  for (let i = 1; i < data.length; i++) {
    if (String(data[i][idxNombre]).toLowerCase() === String(serieName).toLowerCase()) {
      let p = String(data[i][idxPortada]).trim();
      return p.startsWith("http") ? p : null;
    }
  }
  return null;
}

function getRango(caps) {
  if (caps < 10) return "🌱 Iniciado";
  if (caps < 30) return "🌸 Editor Activo";
  if (caps < 60) return "🔥 Leyenda del Scan";
  return "👑 Dios del Manhwa";
}

function renderProgressBar(current, target, length = 10) {
  const filled = Math.min(length, Math.floor((current / target) * length));
  const empty = Math.max(0, length - filled);
  return "█".repeat(filled) + "░".repeat(empty);
}

// ─────────────────────────────────────────────────────────────
// UTILIDADES PARA DISCORD API (Requieren UrlFetchApp)
// ─────────────────────────────────────────────────────────────

function asegurarRolCanal(guildId, serieName) {
  const targetName = String(serieName).toLowerCase().trim();
  const cacheKey = "ROLE_" + guildId + "_" + targetName.replace(/\s+/g, '_');
  const cache = CacheService.getScriptCache();
  const cached = cache.get(cacheKey);
  if (cached) return cached;

  const urlGet = `https://discord.com/api/v10/guilds/${guildId}/roles`;
  const optionsGet = {
    method: "GET",
    headers: { "Authorization": `Bot ${DISCORD_BOT_TOKEN_NUBE}` },
    muteHttpExceptions: true
  };
  
  try {
    const res = UrlFetchApp.fetch(urlGet, optionsGet);
    if (res.getResponseCode() === 200) {
      const roles = JSON.parse(res.getContentText());
      for (let r of roles) {
        if (String(r.name).toLowerCase().trim() === targetName) {
          cache.put(cacheKey, String(r.id), 21600); // Guardar por 6 horas
          return String(r.id);
        }
      }
    }
  } catch(e) { console.error(e); }
  
  // No existe, crearlo
  const urlPost = `https://discord.com/api/v10/guilds/${guildId}/roles`;
  const payload = {
    name: serieName,
    color: 0xff7eb3,
    mentionable: true
  };
  const optionsPost = {
    method: "POST",
    headers: {
      "Authorization": `Bot ${DISCORD_BOT_TOKEN_NUBE}`,
      "Content-Type": "application/json"
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  };
  
  try {
    const res2 = UrlFetchApp.fetch(urlPost, optionsPost);
    if (res2.getResponseCode() === 200 || res2.getResponseCode() === 201) {
      const nuevo = JSON.parse(res2.getContentText());
      return String(nuevo.id);
    }
  } catch(e) { console.error(e); }
  
  return "";
}

function esAdminOCoordinador(roles, esAdmin) {
  if (esAdmin) return true;
  const COORD_ID = "1460674417460777138";
  return roles && roles.includes(COORD_ID);
}

// ─────────────────────────────────────────────────────────────
// COMANDO: /asignar
// ─────────────────────────────────────────────────────────────
function cmdAsignar(cmd) {
  if (!esAdminOCoordinador(cmd.roles, cmd.is_admin)) {
    return { content: "❌ No tienes permisos para usar este comando.", flags: 64 };
  }

  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
  } catch(e) {
    return { content: "❌ El servidor está ocupado. Intenta de nuevo.", flags: 64 };
  }

  try {
    const opts = cmd.options;
    const targetUserId = opts.usuario_user_id || "";
    const targetUserName = opts.usuario_user_name || "";
    const tareaVal = opts.tarea || "";
    const serieName = opts.serie_name || "";
    const serieChannelId = opts.serie_id || "";
    const capitulo = opts.capitulo || "";
    const guildId = cmd.guild_id;

    const capitulos = parsearCapitulos(capitulo);
    
    const sheetAsig = getSheet("Asignaciones");
    const dataAsig = sheetAsig.getDataRange().getValues();
    const headersAsig = dataAsig[0];
    
    // Verificar duplicados
    let duplicados = [];
    for (let cap of capitulos) {
      for (let i = 1; i < dataAsig.length; i++) {
        let r = {};
        headersAsig.forEach((h, idx) => r[h] = dataAsig[i][idx]);
        if (String(r.Proyecto).toLowerCase() === String(serieName).toLowerCase() &&
            getCap(r) === String(cap) &&
            String(r.Tarea).toLowerCase() === String(tareaVal).toLowerCase()) {
          duplicados.push(cap);
          break;
        }
      }
    }
    
    if (duplicados.length > 0) {
      return {
        content: `❌ **Tarea duplicada** en caps: \`${duplicados.join(', ')}\`\nUsa \`/cancelar_asignacion\` primero.`,
        flags: 64
      };
    }
    
    let roleId = asegurarRolCanal(guildId, serieName);
    let extraActions = [];
    
    if (roleId) {
      extraActions.push({
        url: `https://discord.com/api/v10/guilds/${guildId}/members/${targetUserId}/roles/${roleId}`,
        method: "PUT",
        auth: `Bot ${DISCORD_BOT_TOKEN_NUBE}`,
        body: {}
      });
    }
    
    let rowsToAdd = [];
    for (let cap of capitulos) {
      rowsToAdd.push([
        serieName,
        cap,
        tareaVal,
        targetUserName,
        "En Proceso",
        asTextId(targetUserId),
        timestampNowIso()
      ]);
    }
    
    if (rowsToAdd.length > 0) {
      const range = sheetAsig.getRange(sheetAsig.getLastRow() + 1, 1, rowsToAdd.length, rowsToAdd[0].length);
      range.setValues(rowsToAdd);
    actualizarEstadoTareaSerieBatchLocal(serieName, capitulos, tareaVal, "⏳");
  }
  
  let capsStr = capitulos.join(", ");
  let capDisplay = capitulos.length > 1 ? `**${capsStr}**` : `**${capitulos[0]}**`;
  
  let embedSerie = {
    title: "🌸 Nueva Tarea Asignada",
    description: `<@${targetUserId}> Se te ha asignado ${capitulos.length === 1 ? 'un capítulo' : capitulos.length + ' capítulos'}.`,
    color: 0xffb6c1,
    fields: [
      { name: "🛠️ Tarea", value: `**${tareaVal}**`, inline: true },
      { name: "📌 Capítulo(s)", value: capDisplay, inline: true }
    ],
    footer: { text: "Bloom Scans • Calidad y Coherencia" }
  };
  
  extraActions.push({
    url: `https://discord.com/api/v10/channels/${serieChannelId}/messages`,
    method: "POST",
    auth: `Bot ${DISCORD_BOT_TOKEN_NUBE}`,
    body: { content: `<@${targetUserId}>`, embeds: [embedSerie] }
  });
  
  let extrasLog = [];
  if (roleId) {
    extrasLog.push({ name: "🏷️ Rol", value: `✅ <@&${roleId}>`, inline: true });
  }
  
  const CANAL_ASIGNACIONES_LOG = "1460771399999160442";
  let embedLog = {
    title: "✨ Nueva Asignación Registrada",
    color: 0xff7eb3,
    description: `Se ha delegado ${capitulos.length === 1 ? 'una tarea' : capitulos.length + ' tareas'} a **${targetUserName}**.`,
    fields: [
      { name: "📘 Proyecto", value: `<#${serieChannelId}>`, inline: true },
      { name: "📌 Capítulo(s)", value: `\`${capsStr}\``, inline: true },
      { name: "👤 Staff", value: `<@${targetUserId}>`, inline: true },
      { name: "🛠️ Tarea", value: `**${tareaVal}**`, inline: false },
      ...extrasLog
    ],
    footer: { text: `Bloom Scans • ID:${targetUserId} | Caps:${capsStr}` }
  };
  
  extraActions.push({
    url: `https://discord.com/api/v10/channels/${CANAL_ASIGNACIONES_LOG}/messages`,
    method: "POST",
    auth: `Bot ${DISCORD_BOT_TOKEN_NUBE}`,
    body: { embeds: [embedLog] }
  });
  
    return {
      content: `✅ Se han asignado los capítulos \`${capsStr}\` a **${targetUserName}**.`,
      extraActions: extraActions,
      flags: 64
    };
  } catch(e) {
    console.error("Error en cmdAsignar:", e);
    return { content: "❌ Error al realizar la asignación: " + e.message, flags: 64 };
  } finally {
    lock.releaseLock();
  }
}

// ─────────────────────────────────────────────────────────────
// COMANDO: /abandonar
// ─────────────────────────────────────────────────────────────
function cmdAbandonar(cmd) {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
  } catch(e) {
    return { content: "❌ El servidor está ocupado. Intenta de nuevo.", flags: 64 };
  }

  try {
    const opts = cmd.options;
    const serieName = opts.serie_name || "";
    const capitulo = opts.capitulo || "";
    const tareaVal = opts.tarea || "";
    const userId = cmd.user_id;
    const userName = cmd.user_name;

    const sheetAsig = getSheet("Asignaciones");
    const dataAsig = sheetAsig.getDataRange().getValues();
    const headersAsig = dataAsig[0];
    
    const apodoVal = getApodoValue(userId, userName);
    const apodoLower = apodoVal.toLowerCase();

    let rowNum = -1;
    for (let i = 1; i < dataAsig.length; i++) {
      let r = {};
      headersAsig.forEach((h, idx) => r[h] = dataAsig[i][idx]);
      if (String(r.Proyecto).toLowerCase() === String(serieName).toLowerCase() &&
          getCap(r) === String(capitulo) &&
          String(r.Tarea).toLowerCase() === String(tareaVal).toLowerCase() &&
          matchesUser(r, userId, userName, apodoLower) &&
          String(r.Estado).toLowerCase() !== "terminado") {
        rowNum = i + 1;
        break;
      }
    }
    
    if (rowNum === -1) {
      return { content: "❌ No encontré esa tarea asignada a ti o ya está terminada.", flags: 64 };
    }
    
    sheetAsig.deleteRow(rowNum);
    actualizarEstadoTareaSerieBatchLocal(serieName, [capitulo], tareaVal, "❌");
    
    return { content: "✅ Has abandonado la tarea.", flags: 64 };
  } catch(e) {
    return { content: "❌ Error al abandonar la tarea: " + e.message, flags: 64 };
  } finally {
    lock.releaseLock();
  }
}

// ─────────────────────────────────────────────────────────────
// COMANDO: /cancelar_asignacion
// ─────────────────────────────────────────────────────────────
function cmdCancelarAsignacion(cmd) {
  if (!esAdminOCoordinador(cmd.roles, cmd.is_admin)) {
    return { content: "❌ Sin permisos.", flags: 64 };
  }

  const opts = cmd.options;
  const serieName = opts.serie_name || "";
  const capituloStr = opts.capitulo || "";
  const tareaVal = opts.tarea || "";

  const capitulos = parsearCapitulos(capituloStr);
  if (capitulos.length === 0) {
    return { content: "❌ Formato de capítulo inválido.", flags: 64 };
  }
  
  const sheetAsig = getSheet("Asignaciones");
  const dataAsig = sheetAsig.getDataRange().getValues();
  const headersAsig = dataAsig[0];
  
  let rowsToDelete = [];
  let exitos = [];
  let errores = [];
  
  for (let cap of capitulos) {
    let rowNum = -1;
    for (let i = 1; i < dataAsig.length; i++) {
      let r = {};
      headersAsig.forEach((h, idx) => r[h] = dataAsig[i][idx]);
      if (String(r.Proyecto).toLowerCase() === String(serieName).toLowerCase() &&
          getCap(r) === String(cap) &&
          String(r.Tarea).toLowerCase() === String(tareaVal).toLowerCase() &&
          String(r.Estado).toLowerCase() !== "terminado") {
        rowNum = i + 1;
        break;
      }
    }
    
    if (rowNum !== -1) {
      if (!rowsToDelete.includes(rowNum)) rowsToDelete.push(rowNum);
      exitos.push(cap);
    } else {
      errores.push(`Cap ${cap}: no asignado`);
    }
  }
  
  // Ordenar de mayor a menor para borrar de abajo hacia arriba sin alterar los indices
  rowsToDelete.sort((a, b) => b - a);
  for (let r of rowsToDelete) {
    sheetAsig.deleteRow(r);
  }
  
  if (exitos.length > 0) {
    actualizarEstadoTareaSerieBatchLocal(serieName, exitos, tareaVal, "❌");
  }
  
  let desc = `✅ Asignación de **${tareaVal}** cancelada para ${exitos.length} cap(s).`;
  if (errores.length > 0) {
    desc += `\n\n⚠️ Errores:\n` + errores.map(e => `> ${e}`).join("\n");
  }
  
  return { content: desc, flags: 64 };
}

// ─────────────────────────────────────────────────────────────
// COMANDO: /trabajos
// ─────────────────────────────────────────────────────────────
function nombreMes(mesNum) {
  const meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];
  return meses[mesNum - 1] || "Mes " + mesNum;
}

function cmdTrabajos(cmd) {
  const userId = cmd.user_id;
  const userName = cmd.user_name;
  const apodoUser = getApodoValue(userId, userName);
  const mesNum = cmd.options && cmd.options.mes ? parseInt(cmd.options.mes) : (new Date().getMonth() + 1);
  const anioNum = cmd.options && cmd.options.anio ? parseInt(cmd.options.anio) : new Date().getFullYear();
  
  const sheetReg = getSheet("Registro");
  const dataReg = sheetReg.getDataRange().getValues();
  const headersReg = dataReg[0];
  
  let conteo = 0;
  for (let i = 1; i < dataReg.length; i++) {
    let r = {};
    headersReg.forEach((h, idx) => r[h] = dataReg[i][idx]);
    
    const ym = getYearMonth(r.Fecha);
    if (matchesUser(r, userId, userName, apodoUser) && ym.month === mesNum && ym.year === anioNum) {
      conteo++;
    }
  }
  
  let rango = getRango(conteo);
  let bar = renderProgressBar(conteo, 30, 15); // Meta de 30 para veterano
  
  let embed = {
    title: "📊 Tu Rendimiento", 
    color: 0xffb6c1,
    thumbnail: { url: cmd.options && cmd.options._user_avatar ? cmd.options._user_avatar : "https://cdn.discordapp.com/embed/avatars/0.png" },
    fields: [
      { name: "Mes", value: nombreMes(mesNum), inline: true },
      { name: "Total Trabajos", value: `**${conteo}** capítulos`, inline: true },
      { name: "🏆 Rango", value: rango, inline: false },
      { name: "Progreso a la siguiente meta", value: `\`${bar}\``, inline: false }
    ],
    footer: { text: "Bloom Scans - ¡Sigue así!" }
  };
  
  return { embeds: [embed], flags: 64 };
}

// ─────────────────────────────────────────────────────────────
// COMANDO: /ver_asignacion
// ─────────────────────────────────────────────────────────────
function normalizarTarea(tarea) {
  const t = String(tarea || "").toLowerCase()
    .normalize("NFD").replace(/[\u0300-\u036f]/g, ""); // quitar acentos para comparar
  if (t.includes('trad')) return 'Traductor';
  if (t.includes('edic') || t.includes('edit') || t.includes('typ')) return 'Editor';
  if (t.includes('clean') || t.includes('limpi')) return 'Cleaner';
  if (t.includes('recort')) return 'Recorte'; // rol separado, no contamina Cleaner
  if (t.includes('raw')) return null; // RAW no es un rol de créditos
  return null; // fallback seguro: ignorar roles desconocidos
}

function cmdVerAsignacion(cmd) {
  const opts = cmd.options;
  const serieName = opts.serie_name || "";
  const capitulo = opts.capitulo || "";
  const serieChannelId = opts.serie_id || "";
  
  const sheetAsig = getSheet("Asignaciones");
  const dataAsig = sheetAsig.getDataRange().getValues();
  const headersAsig = dataAsig[0];
  
  let staff = {
    "Traductor": "⚪ No asignado", 
    "Editor": "⚪ No asignado", 
    "Cleaner": "⚪ No asignado"
  };
  
  for (let i = 1; i < dataAsig.length; i++) {
    let r = {};
    headersAsig.forEach((h, idx) => r[h] = dataAsig[i][idx]);
    
    if (String(r.Proyecto).toLowerCase() === String(serieName).toLowerCase() && getCap(r) === String(capitulo)) {
      let estado = String(r.Estado).toLowerCase() === "terminado" ? "✅ Terminado" : "⏳ En Proceso";
      let t = normalizarTarea(r.Tarea);
      if (staff.hasOwnProperty(t)) {
        staff[t] = `👤 **${r.Usuario}** — ${estado}`;
      }
    }
  }
  
  let fields = [];
  for (let t in staff) {
    fields.push({ name: `✨ ${t}`, value: staff[t], inline: false });
  }
  
  let urlPortada = getPortadaUrl(serieName);
  let embed = {
    title: `🌸 Estado Actual | ${serieName}`,
    description: `Revisando las asignaciones para el **Capítulo \`${capitulo}\`**.`,
    color: 0xff7eb3,
    fields: fields,
    footer: { text: "Bloom Scans • Consulta de Asignaciones" }
  };
  
  if (urlPortada) {
    embed.thumbnail = { url: urlPortada };
  }
  
  return { embeds: [embed], flags: 64 };
}

// ─────────────────────────────────────────────────────────────
// COMANDO: /creditos
// ─────────────────────────────────────────────────────────────
function cmdCreditos(cmd) {
  const opts = cmd.options;
  const serieName = opts.serie_name || "";
  const capitulo = opts.capitulo || "";
  
  // Primero buscar en Registro (trabajos terminados)
  const sheetReg = getSheet("Registro");
  const dataReg = sheetReg.getDataRange().getValues();
  const headersReg = dataReg[0];
  
  let creds = {
    "Traductor": "⚪ Pendiente",
    "Editor":    "⚪ Pendiente",
    "Cleaner":   "⚪ Pendiente"
  };
  
  // Buscar en Registro (completados)
  for (let i = 1; i < dataReg.length; i++) {
    let r = {};
    headersReg.forEach((h, idx) => r[h] = dataReg[i][idx]);
    
    if (String(r.Proyecto || "").toLowerCase() === String(serieName).toLowerCase() &&
        getCap(r) === String(capitulo).trim()) {
      let t = normalizarTarea(r.Tarea);
      if (t && creds.hasOwnProperty(t)) {
        // Usar getApodoValue global (normaliza IDs) en lugar de helper local
        let apodo = getApodoValue(String(r.ID_Usuario || ""), String(r.Usuario || ""));
        creds[t] = `👤 **${apodo}**`;
      }
    }
  }
  
  // Si algún rol sigue como Pendiente, también buscar en Asignaciones (en proceso)
  const rolesIncompletos = Object.values(creds).some(v => v.includes("Pendiente"));
  if (rolesIncompletos) {
    const sheetAsig = getSheet("Asignaciones");
    const dataAsig = sheetAsig.getDataRange().getValues();
    const headersAsig = dataAsig[0];
    
    for (let i = 1; i < dataAsig.length; i++) {
      let r = {};
      headersAsig.forEach((h, idx) => r[h] = dataAsig[i][idx]);
      
      if (String(r.Proyecto || "").toLowerCase() === String(serieName).toLowerCase() &&
          getCap(r) === String(capitulo).trim() &&
          String(r.Estado || "").toLowerCase() !== "terminado") {
        let t = normalizarTarea(r.Tarea);
        if (t && creds.hasOwnProperty(t) && creds[t].includes("Pendiente")) {
          let apodo = getApodoValue(String(r.ID_Usuario || ""), String(r.Usuario || ""));
          creds[t] = `⏳ **${apodo}** *(en proceso)*`;
        }
      }
    }
  }
  
  let fields = [];
  for (let t in creds) {
    fields.push({ name: `✨ ${t}`, value: creds[t], inline: false });
  }
  
  let urlPortada = getPortadaUrl(serieName);
  
  let embed = {
    title: `🏆 Créditos | ${serieName} | Cap ${capitulo}`,
    description: `Staff que trabajó en este capítulo:`,
    color: 0xffd700,
    fields: fields,
    footer: { text: "Bloom Scans • ¡Buen trabajo equipo!" }
  };
  
  if (urlPortada) {
    embed.thumbnail = { url: urlPortada };
  }
  
  return { 
    embeds: [embed],
    flags: 64
  };
}

// ─────────────────────────────────────────────────────────────
// COMANDO: /posibles_ganadores
// ─────────────────────────────────────────────────────────────
function cmdPosiblesGanadores(cmd) {
  const mesNum = cmd.options && cmd.options.mes ? parseInt(cmd.options.mes) : (new Date().getMonth() + 1);
  const anioNum = cmd.options && cmd.options.anio ? parseInt(cmd.options.anio) : new Date().getFullYear();
  
  const sheetReg = getSheet("Registro");
  const dataReg = sheetReg.getDataRange().getValues();
  const headersReg = dataReg[0];
  
  let rankingObj = {};
  
  for (let i = 1; i < dataReg.length; i++) {
    let r = {};
    headersReg.forEach((h, idx) => r[h] = dataReg[i][idx]);
    
    const ym = getYearMonth(r.Fecha);
    let m_f = ym.month;
    let y_f = ym.year;
    
    if (m_f === mesNum && y_f === anioNum) {
      let uid = normalizeIdFromSheet(r.ID_Usuario);
      let un = r.Usuario;
      if (!rankingObj[uid]) rankingObj[uid] = { count: 0, name: un };
      rankingObj[uid].count++;
    }
  }
  
  let rankingList = Object.values(rankingObj).sort((a, b) => b.count - a.count);
  
  let calificados = rankingList.filter(r => r.count >= 25);
  let noCalif = rankingList.filter(r => r.count < 25);
  
  let fields = [];
  if (calificados.length > 0) {
    let medallas = ["🥇", "🥈", "🥉"];
    let txt = "";
    calificados.forEach((r, i) => {
      let m = i < 3 ? medallas[i] : '🎖️';
      let bar = renderProgressBar(r.count, 25, 10);
      txt += `${m} **${r.name}** — \`${r.count}\` caps\n\`${bar}\`\n`;
    });
    fields.push({ name: "✅ CALIFICAN (25+ caps)", value: limitDiscordText(txt, 1000), inline: false });
  } else {
    fields.push({ name: "⚠️ NADIE CALIFICA AÚN", value: "Mínimo 25 caps.", inline: false });
  }
  
  if (noCalif.length > 0) {
    let txt2 = "";
    noCalif.slice(0, 8).forEach(r => {
      let bar = renderProgressBar(r.count, 25, 10);
      txt2 += `• **${r.name}** — \`${r.count}\` (faltan ${25 - r.count})\n\`${bar}\`\n`;
    });
    fields.push({ name: "📌 CERCA DE CALIFICAR", value: limitDiscordText(txt2, 1000), inline: false });
  }
  
  let embed = {
    title: "🏆 POSIBLES GANADORES DEL MES 🏆",
    description: `**Mes:** ${nombreMes(mesNum)} ${anioNum}`,
    color: 0xffd700,
    fields: fields,
    footer: { text: "Bloom Scans • Motivación y Competencia Sana" }
  };
  
  return { embeds: [embed], flags: 64 };
}

// ─────────────────────────────────────────────────────────────
// COMANDO: /apodo y /registrar_correo
// ─────────────────────────────────────────────────────────────
function cmdApodo(cmd) {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
  } catch(e) {
    return { content: "❌ El servidor está ocupado. Intenta de nuevo.", flags: 64 };
  }

  try {
    const userId = cmd.user_id;
    const nuevoApodo = cmd.options && (cmd.options.nombre || cmd.options.apodo) ? (cmd.options.nombre || cmd.options.apodo) : "";
    if (!nuevoApodo) return { content: "❌ Faltó el apodo.", flags: 64 };
    
    const sheet = getSheet("Apodos");
    const data = sheet.getDataRange().getValues();
    let row = -1;
    const targetId = normalizeIdFromSheet(userId);

    for (let i = 1; i < data.length; i++) {
      if (normalizeIdFromSheet(data[i][0]) === targetId) {
        row = i + 1;
        break;
      }
    }
    if (row !== -1) {
      sheet.getRange(row, 2).setValue(nuevoApodo);
    } else {
      sheet.appendRow([asTextId(userId), nuevoApodo]);
    }
    return { content: `✅ Tu apodo para créditos ahora es: **${nuevoApodo}**`, flags: 64 };
  } catch(e) {
    return { content: "❌ Error al actualizar apodo: " + e.message, flags: 64 };
  } finally {
    lock.releaseLock();
  }
}

function grantDriveAccessForActiveAssignments(userId, correo) {
  const projects = {};
  const asigSheet = getSheet("Asignaciones");
  const asigData = asigSheet.getDataRange().getValues();
  const asigHeaders = asigData[0] || [];
  const idxProyecto = asigHeaders.indexOf("Proyecto");
  const idxEstado = asigHeaders.indexOf("Estado");
  const idxUsuario = asigHeaders.indexOf("ID_Usuario");
  for (let i = 1; i < asigData.length; i++) {
    const estado = String(asigData[i][idxEstado] || "").toLowerCase();
    if (estado === "terminado") continue;
    if (sameUserId(asigData[i][idxUsuario], userId)) {
      const proyecto = String(asigData[i][idxProyecto] || "").trim();
      if (proyecto) projects[proyecto.toLowerCase()] = proyecto;
    }
  }
  const projectNames = Object.keys(projects).map(k => projects[k]);
  if (projectNames.length === 0) return { granted: 0, failed: 0 };

  const seriesSheet = getSheet("Series");
  const sData = seriesSheet.getDataRange().getValues();
  const sHeaders = sData[0] || [];
  const idxNombre = sHeaders.indexOf("Nombre");
  const idxFolder = sHeaders.indexOf("Folder_ID");
  let granted = 0;
  let failed = 0;
  projectNames.forEach(projectName => {
    let folderId = "";
    for (let i = 1; i < sData.length; i++) {
      if (normalizeSheetKey(sData[i][idxNombre]) === normalizeSheetKey(projectName)) {
        folderId = String(sData[i][idxFolder] || "").trim();
        break;
      }
    }
    if (!folderId) {
      failed++;
      return;
    }
    try {
      DriveApp.getFolderById(folderId).addEditor(correo);
      granted++;
    } catch(e) {
      failed++;
    }
  });
  return { granted: granted, failed: failed };
}

function cmdRegistrarCorreo(cmd) {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
  } catch(e) {
    return { content: "❌ El servidor está ocupado. Intenta de nuevo.", flags: 64 };
  }

  try {
    const userId = cmd.user_id;
    const correo = cmd.options && cmd.options.correo ? String(cmd.options.correo).trim() : "";
    if (!correo.includes("@")) return { content: "❌ Correo inválido.", flags: 64 };
    
    const sheet = getSheet("Correos");
    if (!sheet) return { content: "❌ No se encontró la hoja de 'Correos'. Contacta a un administrador.", flags: 64 };

    const data = sheet.getDataRange().getValues();
    let row = -1;
    const targetId = normalizeIdFromSheet(userId);

    for (let i = 1; i < data.length; i++) {
      if (normalizeIdFromSheet(data[i][0]) === targetId) {
        row = i + 1;
        break;
      }
    }
    
    if (row !== -1) {
      let correos = String(data[row - 1][1] || "").split(",").map(c => c.trim()).filter(c => c);
      if (!correos.includes(correo)) correos.push(correo);
      sheet.getRange(row, 2).setValue(correos.join(", "));
    } else {
      // La hoja Correos suele tener: ID_Usuario | Correo
      sheet.appendRow([asTextId(userId), correo]);
    }
    
    const retro = grantDriveAccessForActiveAssignments(userId, correo);
    let extra = "";
    if (retro.granted > 0) extra = `\nSe re-sincronizó acceso en **${retro.granted}** serie(s) activa(s).`;
    if (retro.failed > 0) extra += `\n⚠️ No pude re-sincronizar **${retro.failed}** serie(s); avisa a un admin si te falta acceso.`;
    return { content: `✅ Correo \`${correo}\` registrado correctamente para Drive.${extra}`, flags: 64 };
  } catch(e) {
    return { content: "❌ Error al registrar correo: " + e.message, flags: 64 };
  } finally {
    lock.releaseLock();
  }
}

// ─────────────────────────────────────────────────────────────
// COMANDO: /ausente y /cancelar_ausencia
// ─────────────────────────────────────────────────────────────
function cmdAusente(cmd) {
  const userId = cmd.user_id;
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
  } catch(e) {
    return { content: "El servidor esta ocupado. Intenta de nuevo.", flags: 64 };
  }
  const dias = cmd.options && cmd.options.dias ? parseInt(cmd.options.dias) : 0;
  const motivo = cmd.options && cmd.options.motivo ? cmd.options.motivo : "Sin motivo";
  
  if (dias < 1 || dias > 30) {
    lock.releaseLock();
    return { content: "Los dias de ausencia deben estar entre 1 y 30.", flags: 64 };
  }
  
  let dateFin = new Date();
  dateFin.setDate(dateFin.getDate() + dias);
  let fechaFinIso = dateFin.toISOString().replace('T', ' ').substring(0, 19);
  
  try {
    const sheet = getSheet("Usuarios");
    const data = sheet.getDataRange().getValues();
    let row = -1;
    for (let i = 1; i < data.length; i++) {
      if (sameUserId(data[i][0], userId)) {
        row = i + 1;
        break;
      }
    }
    if (row !== -1) {
      sheet.getRange(row, 3).setValue(fechaFinIso);
    } else {
      sheet.appendRow([asTextId(userId), "", fechaFinIso]);
    }
  } finally {
    lock.releaseLock();
  }
  
  let embed = {
    title: "💤 Registro de Ausencia", color: 0x3498db,
    fields: [
      { name: "Staff", value: `<@${userId}>`, inline: true },
      { name: "Regresa", value: fechaFinIso.substring(0, 10), inline: true },
      { name: "Motivo", value: motivo, inline: false }
    ]
  };
  
  const ADMIN_CHANNEL_ID = "1432254360666247168";
  return {
    content: "✅ Ausencia registrada. ¡Cuídate!",
    flags: 64,
    extraActions: [{
      url: `https://discord.com/api/v10/channels/${ADMIN_CHANNEL_ID}/messages`,
      method: "POST",
      auth: `Bot ${DISCORD_BOT_TOKEN_NUBE}`,
      body: { embeds: [embed] }
    }]
  };
}

function cmdCancelarAusencia(cmd) {
  const userId = cmd.user_id;
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
  } catch(e) {
    return { content: "El servidor esta ocupado. Intenta de nuevo.", flags: 64 };
  }
  try {
    const sheet = getSheet("Usuarios");
    const data = sheet.getDataRange().getValues();
    let row = -1;
    for (let i = 1; i < data.length; i++) {
      if (sameUserId(data[i][0], userId)) {
        row = i + 1;
        break;
      }
    }
    if (row !== -1) {
      sheet.getRange(row, 3).setValue("");
    }
  } finally {
    lock.releaseLock();
  }
  
  let embed = {
    title: "🔄 Regreso Anticipado",
    description: `<@${userId}> canceló su ausencia.`,
    color: 0x57F287
  };
  
  const ADMIN_CHANNEL_ID = "1432254360666247168";
  return {
    content: "✅ Ausencia cancelada. ¡Bienvenido de vuelta!",
    flags: 64,
    extraActions: [{
      url: `https://discord.com/api/v10/channels/${ADMIN_CHANNEL_ID}/messages`,
      method: "POST",
      auth: `Bot ${DISCORD_BOT_TOKEN_NUBE}`,
      body: { embeds: [embed] }
    }]
  };
}

// ─────────────────────────────────────────────────────────────
// COMANDO: /quitar_staff
// ─────────────────────────────────────────────────────────────
function cmdQuitarStaff(cmd) {
  if (!esAdminOCoordinador(cmd.roles, cmd.is_admin)) {
    return { content: "❌ Sin permisos.", flags: 64 };
  }

  const targetUserId = cmd.options && cmd.options.usuario_user_id ? cmd.options.usuario_user_id : "";
  if (!targetUserId) return { content: "❌ Falta el usuario.", flags: 64 };
  
  // Usar la función ya existente en Code.gs para borrar DB y revocar Drive
  quitarStaff(targetUserId);

  let embed = {
    title: "🚫 Revocación de Accesos",
    description: `Se han eliminado todas las asignaciones y se ha revocado el acceso a los archivos de Drive para el usuario <@${targetUserId}>.`,
    color: 0xE74C3C,
    footer: { text: "Bloom Scans • Administración de Seguridad" }
  };
  
  const ADMIN_CHANNEL_ID = "1432254360666247168"; // Canal de Administradores
  return {
    content: `✅ Accesos revocados para <@${targetUserId}>.`,
    flags: 64,
    extraActions: [{
      url: `https://discord.com/api/v10/channels/${ADMIN_CHANNEL_ID}/messages`,
      method: "POST",
      auth: `Bot ${DISCORD_BOT_TOKEN_NUBE}`,
      body: { embeds: [embed] }
    }]
  };
}

// ─────────────────────────────────────────────────────────────
// NUEVOS COMANDOS PREMIUM
// ─────────────────────────────────────────────────────────────

function cmdProgreso(cmd) {
  const serieName = cmd.options && cmd.options.serie_name ? cmd.options.serie_name : "";
  if (!serieName) return { content: "❌ Debes indicar el nombre de la serie.", flags: 64 };
  
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  const hojas = getCandidateOwnerSheetsForSerie(ss, serieName);
  let dataSerie = null;
  let headers = [];
  
  for (let h of hojas) {
    let sheet = ss.getSheetByName(h);
    if (!sheet) continue;
    let data = sheet.getDataRange().getValues();
    let fila0 = data[0] || [];
    let startCol = -1;
    for (let c = 0; c < fila0.length; c++) {
      if (String(fila0[c]).trim().toLowerCase() === String(serieName).trim().toLowerCase()) {
        startCol = c;
        break;
      }
    }
    if (startCol >= 0) {
      headers = ["Cap","Idioma","RAW","Clean","Traduccion","Edicion","Recorte","Subido_Web","Fecha_RAW"];
      dataSerie = [];
      for (let r = 4; r < data.length; r++) {
        let cap = String(data[r][startCol] || "");
        if (!cap) break;
        let obj = {};
        headers.forEach((hd, idx) => obj[hd] = data[r][startCol + idx]);
        dataSerie.push(obj);
      }
      break;
    }
  }
  
  if (!dataSerie) {
    return { content: "❌ No encontré la serie en ninguna hoja administrativa.", flags: 64 };
  }
  
  let totalCaps = dataSerie.length;
  if (totalCaps === 0) {
    return { content: "⚠️ La serie no tiene capítulos registrados aún.", flags: 64 };
  }
  
  let stats = { "RAW": 0, "Clean": 0, "Traduccion": 0, "Edicion": 0, "Recorte": 0 };
  for (let row of dataSerie) {
    for (let t in stats) {
      if (String(row[t]).includes("✅")) stats[t]++;
    }
  }
  
  let fields = [];
  for (let t in stats) {
    let bar = renderProgressBar(stats[t], totalCaps, 10);
    let pct = Math.floor((stats[t] / totalCaps) * 100);
    fields.push({ name: `📌 ${t}`, value: `\`${bar}\` ${pct}% (${stats[t]}/${totalCaps})`, inline: false });
  }
  
  let chartData = {
    type: 'doughnut',
    data: {
      labels: ['RAW','Clean','Traduccion','Edicion','Recorte'],
      datasets: [{
        data: [stats.RAW, stats.Clean, stats.Traduccion, stats.Edicion, stats.Recorte],
        backgroundColor: ['#E74C3C','#3498DB','#F1C40F','#2ECC71','#9B59B6']
      }]
    },
    options: {
      plugins: {
        legend: { position: 'right', labels: { fontColor: '#ffffff' } }
      }
    }
  };
  let chartUrl = "https://quickchart.io/chart?bkg=transparent&c=" + encodeURIComponent(JSON.stringify(chartData));
  
  let portadaUrl = getPortadaUrl(serieName);
  let embed = {
    title: `📈 Progreso de ${serieName}`,
    description: `Análisis general de los capítulos registrados.`,
    color: 0x3498db,
    image: { url: chartUrl },
    fields: fields,
    footer: { text: "Bloom Scans • Datos en tiempo real" }
  };
  if (portadaUrl) embed.thumbnail = { url: portadaUrl };
  
  return { embeds: [embed], flags: 64 };
}

function cmdMiPerfil(cmd) {
  const userId = cmd.user_id;
  const userName = cmd.user_name;
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  const apodoUserPerfil = getApodoValue(userId, userName);
  
  const sheetReg = getSheet("Registro");
  const dataReg = sheetReg.getDataRange().getValues();
  let totalCapsHist = 0;
  let totalCapsMes = 0;
  
  // Buscar en todas las hojas que comiencen con "Registro" para el histórico
  const allSheets = ss.getSheets();
  for (let s of allSheets) {
    let sName = s.getName();
    if (sName === "Registro" || sName.startsWith("Registro_")) {
      let data = s.getDataRange().getValues();
      for (let i = 1; i < data.length; i++) {
        let registroUsuario = String(data[i][1] || "").trim().toLowerCase();
        let perfilMatch = sameUserId(data[i][5], userId);
        if (!perfilMatch && registroUsuario) {
          let discordUser = String(userName || "").trim().toLowerCase();
          let apodoLower = String(apodoUserPerfil || "").trim().toLowerCase();
          perfilMatch = (discordUser && (registroUsuario === discordUser || registroUsuario.includes(discordUser) || discordUser.includes(registroUsuario))) ||
            (apodoLower && (registroUsuario === apodoLower || registroUsuario.includes(apodoLower) || apodoLower.includes(registroUsuario)));
        }
        if (perfilMatch) {
          totalCapsHist++;
          if (sName === "Registro") totalCapsMes++; // Caps del mes actual
        }
      }
    }
  }
  
  let rango = getRango(totalCapsHist);
  let apodo = "No registrado";
  let correo = "No registrado";
  
  const sApodos = getSheet("Apodos");
  if (sApodos) {
    const dA = sApodos.getDataRange().getValues();
    for (let i = 1; i < dA.length; i++) {
      if (sameUserId(dA[i][0], userId)) {
        apodo = dA[i][1];
        break;
      }
    }
  }
  
  // En comandos_nube.js, la hoja de correos se llama "Correos" y tiene columnas [ID_Usuario, Correos, Nombre]
  const sCorreos = getSheet("Correos");
  if (sCorreos) {
    const dU = sCorreos.getDataRange().getValues();
    for (let i = 1; i < dU.length; i++) {
      if (sameUserId(dU[i][0], userId)) {
        correo = String(dU[i][1]).trim() || "No registrado";
        break;
      }
    }
  }
  
  let avatarUrl = cmd.options && cmd.options._user_avatar ? cmd.options._user_avatar : "https://cdn.discordapp.com/embed/avatars/0.png";
  
  // Calcular progreso para el siguiente rango
  let nextRankName = "Máximo Rango Alcanzado";
  let capsToNext = 0;
  let currentRankFloor = 0;
  let nextRankCeiling = totalCapsHist;

  if (totalCapsHist < 10) {
    nextRankName = "🌸 Editor Activo"; currentRankFloor = 0; nextRankCeiling = 10;
  } else if (totalCapsHist < 30) {
    nextRankName = "🔥 Leyenda del Scan"; currentRankFloor = 10; nextRankCeiling = 30;
  } else if (totalCapsHist < 60) {
    nextRankName = "👑 Dios del Manhwa"; currentRankFloor = 30; nextRankCeiling = 60;
  }

  let progressField = "¡Has alcanzado el rango máximo! 🌟";
  if (nextRankCeiling > totalCapsHist) {
    let progressInRange = totalCapsHist - currentRankFloor;
    let rangeTotal = nextRankCeiling - currentRankFloor;
    let bar = renderProgressBar(progressInRange, rangeTotal, 12);
    let pct = Math.floor((progressInRange / rangeTotal) * 100);
    progressField = `**${nextRankName}**\n\`${bar}\` ${pct}% (${totalCapsHist}/${nextRankCeiling})`;
  }
  
  let embed = {
    title: `👤 Perfil de Staff | ${userName}`,
    description: `Resumen de tu trayectoria y progreso en Bloom Scans.`,
    color: 0x57F287,
    thumbnail: { url: avatarUrl },
    fields: [
      { name: "🎭 Apodo Créditos", value: `\`${apodo}\``, inline: true },
      { name: "📧 Correo", value: `\`${correo}\``, inline: true },
      { name: "\u200B", value: "\u200B", inline: false }, // Spacer
      { name: "🏅 Rango Actual", value: `**${rango}**`, inline: true },
      { name: "📅 Este Mes", value: `\`${totalCapsMes}\` caps`, inline: true },
      { name: "🏆 Histórico", value: `\`${totalCapsHist}\` caps`, inline: true },
      { name: "🚀 Progreso de Rango", value: progressField, inline: false }
    ],
    footer: { text: "Bloom Scans • Perfil de Staff" }
  };
  
  return { embeds: [embed], flags: 64 };
}

function cmdLimpiarInactivos(cmd) {
  if (!esAdminOCoordinador(cmd.roles, cmd.is_admin)) {
    return { content: "❌ Sin permisos.", flags: 64 };
  }
  
  const sheetReg = getSheet("Registro");
  const dataReg = sheetReg.getDataRange().getValues();
  
  let ultimasFechas = {};
  for (let i = 1; i < dataReg.length; i++) {
    let uId = normalizeIdFromSheet(dataReg[i][5]);
    let fechaValor = dataReg[i][0];
    if (uId && fechaValor) {
      let d = fechaValor instanceof Date ? fechaValor : new Date(fechaValor);
      if (isNaN(d.getTime())) continue;
      if (!ultimasFechas[uId] || d > ultimasFechas[uId]) {
        ultimasFechas[uId] = d;
      }
    }
  }
  
  let inactivos = [];
  const hoy = new Date();
  for (let uId in ultimasFechas) {
    let diffDays = Math.floor((hoy - ultimasFechas[uId]) / (1000 * 60 * 60 * 24));
    if (diffDays >= 30) {
      inactivos.push(`• <@${uId}> - Último reporte: hace ${diffDays} días`);
    }
  }
  
  let txt = inactivos.length > 0 ? inactivos.join("\n") : "✅ Todo el staff está activo.";
  
  let embed = {
    title: "🧹 Reporte de Inactividad (+30 días)",
    description: limitDiscordText(txt, 4000),
    color: 0xE74C3C,
    footer: { text: "Bloom Scans • Mantenimiento" }
  };
  
  return { embeds: [embed], flags: 64 };
}

// ─────────────────────────────────────────────────────────────
// CRON JOB: Recordatorio de Asignaciones Estancadas
// ─────────────────────────────────────────────────────────────
function enviarRecordatorioAsignaciones() {
  const sheetAsig = getSheet("Asignaciones");
  if (!sheetAsig) return;
  const data = sheetAsig.getDataRange().getValues();
  const headers = data[0];
  
  let estancadas = [];
  const hoy = new Date();
  
  const idxEstado = headers.indexOf("Estado");
  if (idxEstado < 0) return;
  let idxCreation = headers.indexOf("Fecha_Asignacion");
  if (idxCreation < 0) idxCreation = headers.indexOf("Fecha");
  if (idxCreation < 0) return;
  
  for (let i = 1; i < data.length; i++) {
    let estado = String(data[i][idxEstado] || "").toLowerCase();
    if (estado !== "terminado") {
      let fecha = data[i][idxCreation];
      if (fecha) {
        let diff = Math.floor((hoy - new Date(fecha)) / (1000 * 60 * 60 * 24));
        if (diff >= 7) {
          let proy = data[i][0];
          let cap = data[i][1];
          let tarea = data[i][2];
          let user = normalizeIdFromSheet(data[i][5]);
          estancadas.push(`• **${proy}** Cap \`${cap}\` (${tarea}) -> <@${user}> (hace ${diff} días)`);
        }
      }
    }
  }
  
  if (estancadas.length === 0) return;
  
  if (estancadas.length > 30) {
    let extras = estancadas.length - 30;
    estancadas = estancadas.slice(0, 30);
    estancadas.push(`... y ${extras} asignaciones más estancadas.`);
  }
  
  let embed = {
    title: "⚠️ Recordatorio Semanal: Asignaciones Pendientes",
    description: limitDiscordText("Las siguientes tareas llevan pendientes bastante tiempo y requieren atención:\n\n" + estancadas.join("\n"), 4000),
    color: 0xF1C40F,
    footer: { text: "Bloom Scans • Limpieza automática" }
  };
  
  const urlPost = `https://discord.com/api/v10/channels/${CANAL_COORDINADORES_ID}/messages`;
  try {
    UrlFetchApp.fetch(urlPost, {
      method: "POST",
      headers: { "Authorization": `Bot ${DISCORD_BOT_TOKEN_NUBE}`, "Content-Type": "application/json" },
      payload: JSON.stringify({ content: "¡Hola Coordinadores! Aquí está el reporte semanal.", embeds: [embed] }),
      muteHttpExceptions: true
    });
  } catch(e) {}
}

// ─────────────────────────────────────────────────────────────
// UTILIDADES PARA TICKET
// ─────────────────────────────────────────────────────────────
function getConfig(key, defaultVal) {
  let sheet = getSheet("Config");
  if (!sheet) return defaultVal;
  let data = sheet.getDataRange().getValues();
  for (let i = 1; i < data.length; i++) {
    if (data[i][0] === key) return data[i][1];
  }
  sheet.appendRow([key, defaultVal]);
  return defaultVal;
}

function setConfig(key, value) {
  let sheet = getSheet("Config");
  if (!sheet) return;
  let data = sheet.getDataRange().getValues();
  for (let i = 1; i < data.length; i++) {
    if (data[i][0] === key) {
      sheet.getRange(i + 1, 2).setValue(value);
      return;
    }
  }
  sheet.appendRow([key, value]);
}

// ─────────────────────────────────────────────────────────────
// NUEVOS COMANDOS ELITE
// ─────────────────────────────────────────────────────────────

function cmdTicket(cmd) {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
  } catch(e) {
    return { content: "❌ El servidor está ocupado. Intenta de nuevo.", flags: 64 };
  }

  try {
    const adminId = cmd.options && cmd.options.admin_user_id ? cmd.options.admin_user_id : (cmd.options && cmd.options.admin ? cmd.options.admin : "");
    const guildId = cmd.guild_id;
    const userId = cmd.user_id;
    
    if (!adminId) return { content: "❌ Debes elegir un administrador.", flags: 64 };
    
    let ticketCount = parseInt(getConfig("ticket_count", "1")) || 1;
    let lastError = "";

    for (let attempt = 0; attempt < 3; attempt++) {
      let nextNumber = ticketCount + attempt;
      let channelName = `ticket-${nextNumber.toString().padStart(3, '0')}`;
      let payload = {
        name: channelName,
        type: 0,
        parent_id: "1458356934489935882",
        permission_overwrites: [
          { id: guildId, type: 0, allow: "0", deny: "1024" },
          { id: userId, type: 1, allow: "3072", deny: "0" },
          { id: adminId, type: 1, allow: "3072", deny: "0" }
        ]
      };

      const res = UrlFetchApp.fetch(`https://discord.com/api/v10/guilds/${guildId}/channels`, {
        method: "POST",
        headers: { "Authorization": `Bot ${DISCORD_BOT_TOKEN_NUBE}`, "Content-Type": "application/json" },
        payload: JSON.stringify(payload),
        muteHttpExceptions: true
      });
      const code = res.getResponseCode();
      const body = res.getContentText();
      if (code >= 200 && code < 300) {
        const created = JSON.parse(body);
        setConfig("ticket_count", nextNumber + 1);
        return { content: `✅ Ticket creado: <#${created.id}>`, flags: 64 };
      }
      lastError = `HTTP ${code}: ${body.substring(0, 180)}`;
    }

    return { content: "❌ Discord no pudo crear el canal del ticket. No se consumió número. " + lastError, flags: 64 };
  } catch(e) {
    return { content: "❌ Error al crear el ticket: " + e.message, flags: 64 };
  } finally {
    lock.releaseLock();
  }
}

function cmdDarBienvenida(cmd) {
  if (!esAdminOCoordinador(cmd.roles, cmd.is_admin)) return { content: "❌ Sin permisos.", flags: 64 };
  
  const userId = cmd.options && cmd.options.usuario_user_id ? cmd.options.usuario_user_id : (cmd.options && cmd.options.usuario ? cmd.options.usuario : "");
  if (!userId) return { content: "❌ Faltan parámetros.", flags: 64 };
  
  const guildId = cmd.guild_id;
  const STAFF_ROLE_ID = "1132158706851786854";
  const BIENVENIDA_CHANNEL_ID = "1458357173737361520";
  
  let embed = {
    title: "🌸 ¡Nuevo Miembro del Staff! 🌸",
    description: `¡Bienvenido <@${userId}> a Bloom Scans!\nPor favor lee las <#1458360744893481045> y usa \`/registrar_correo\` para tener acceso a los archivos.`,
    color: 0xffb6c1,
    image: { url: "https://media1.tenor.com/m/Zp92UjD1D4QAAAAd/cute-anime-dance.gif" }
  };
  
  return {
    content: `✅ Bienvenida enviada a <@${userId}>.`,
    flags: 64,
    extraActions: [
      {
        url: `https://discord.com/api/v10/guilds/${guildId}/members/${userId}/roles/${STAFF_ROLE_ID}`,
        method: "PUT",
        auth: `Bot ${DISCORD_BOT_TOKEN_NUBE}`,
        body: {}
      },
      {
        url: `https://discord.com/api/v10/channels/${BIENVENIDA_CHANNEL_ID}/messages`,
        method: "POST",
        auth: `Bot ${DISCORD_BOT_TOKEN_NUBE}`,
        body: { content: `<@${userId}>`, embeds: [embed] }
      }
    ]
  };
}

function cmdFinalizarMes(cmd) {
  if (cmd.user_id !== "1154257480734490664") return { content: "❌ Solo la dueña puede cerrar el mes.", flags: 64 };
  
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(30000); // 30 segundos para esta tarea pesada
  } catch(e) {
    return { content: "❌ El servidor está ocupado. Intenta de nuevo.", flags: 64 };
  }

  try {
    const mesObjetivo = cmd.options && cmd.options.mes ? parseInt(cmd.options.mes) : (new Date().getMonth() + 1);
    const anioObjetivo = cmd.options && cmd.options.anio ? parseInt(cmd.options.anio) : new Date().getFullYear();
    
    const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
    const sheetReg = ss.getSheetByName("Registro");
    const data = sheetReg.getDataRange().getValues();
    const headers = data[0];
    
    let tempRanking = {};
    let registrosRetener = [headers];
    let registrosMes = [];
    
    for (let i = 1; i < data.length; i++) {
      const ym = getYearMonth(data[i][0]);
      
      if (ym.month === mesObjetivo && ym.year === anioObjetivo) {
        registrosMes.push(data[i]);
        let uid = normalizeIdFromSheet(data[i][5]);
        let name = data[i][1];
        if (!tempRanking[uid]) tempRanking[uid] = { name: name, count: 0 };
        tempRanking[uid].count++;
      } else {
        registrosRetener.push(data[i]);
      }
    }
  
  if (registrosMes.length === 0) return { content: `❌ No hay datos para el mes ${mesObjetivo}/${anioObjetivo}.`, flags: 64 };
  
  let rankArr = [];
  for (let uid in tempRanking) {
    if (tempRanking[uid].count >= 25) {
      rankArr.push({ uid: uid, name: tempRanking[uid].name, count: tempRanking[uid].count });
    }
  }
  rankArr.sort((a,b) => b.count - a.count);
  
  let embed = {
    title: "🌸 BLOOM SCANS - PREMIACIÓN MENSUAL 🌸",
    description: `**Mes cerrado:** ${mesObjetivo}/${anioObjetivo}\n¡Felicidades a los ganadores! Solo califican aquellos con **25+ trabajos**.`,
    color: 0xffb6c1,
    fields: []
  };
  
  let podio = ["🥇 PRIMER LUGAR ($10)", "🥈 SEGUNDO LUGAR ($5)", "🥉 TERCER LUGAR ($3)"];
  let menciones = "";
  
  if (rankArr.length === 0) {
    embed.description += "\n\n⚠️ Nadie alcanzó la meta mínima de 25.";
  } else {
    for (let i = 0; i < rankArr.length; i++) {
      if (i < 3) {
        embed.fields.push({ name: podio[i], value: `👤 **${rankArr[i].name}**\n📊 \`${rankArr[i].count}\` caps.`, inline: false });
      } else {
        menciones += `• **${rankArr[i].name}** (${rankArr[i].count} caps) - $2 USD\n`;
      }
    }
    if (menciones) embed.fields.push({ name: "🎖️ MENCIONES ESPECIALES", value: menciones, inline: false });
  }
  
  let mesName = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"][mesObjetivo-1];
  let sheetName = uniqueSheetName(ss, `Registro_${mesName}_${anioObjetivo}`);
  let newSheet = ss.insertSheet(sheetName);
  let backupData = [headers].concat(registrosMes);
  newSheet.getRange(1, 1, backupData.length, headers.length).setValues(backupData);

  if (newSheet.getLastRow() !== backupData.length) {
    throw new Error("El backup mensual no se escribió completo. No se limpió Registro.");
  }

  let stagingName = uniqueSheetName(ss, `_staging_Registro_${mesName}_${anioObjetivo}`);
  let staging = ss.insertSheet(stagingName);
  staging.getRange(1, 1, registrosRetener.length, headers.length).setValues(registrosRetener);
  if (staging.getLastRow() !== registrosRetener.length) {
    throw new Error("El staging de Registro no se escribió completo. No se limpió Registro.");
  }

  sheetReg.clearContents();
  sheetReg.getRange(1, 1, registrosRetener.length, headers.length).setValues(registrosRetener);
  ss.deleteSheet(staging);
  
    return {
      content: `✅ Ranking cerrado. Archivo generado: ${sheetName}`,
      flags: 64,
      extraActions: [{
        url: `https://discord.com/api/v10/channels/1444910811863711825/messages`,
        method: "POST",
        auth: `Bot ${DISCORD_BOT_TOKEN_NUBE}`,
        body: { content: "@everyone", embeds: [embed] }
      }]
    };
  } catch(e) {
    console.error("Error en cmdFinalizarMes:", e);
    return { content: "❌ Error al finalizar el mes: " + e.message, flags: 64 };
  } finally {
    lock.releaseLock();
  }
}

// ─────────────────────────────────────────────────────────────
// COMANDO: /asignarme
// ─────────────────────────────────────────────────────────────
function cmdAsignarme(cmd) {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
  } catch(e) {
    return { content: "❌ El servidor está ocupado. Intenta de nuevo.", flags: 64 };
  }

  try {
    const userId = cmd.user_id;
    const userName = cmd.user_name;
    const guildId = cmd.guild_id;
    const tareaVal = cmd.options && cmd.options.tarea ? cmd.options.tarea : "";
    const categoriaVal = cmd.options && cmd.options.categoria ? cmd.options.categoria : "";
    const idiomaVal = cmd.options && cmd.options.idioma ? cmd.options.idioma : "cualquiera";
    
    if (!tareaVal || !categoriaVal) return { content: "❌ Faltan parámetros obligatorios.", flags: 64 };
    
    const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
    const seriesSheet = getSheet("Series");
    const seriesData = seriesSheet.getDataRange().getValues();
    const sHeaders = seriesData[0];
    const idxNombre = sHeaders.indexOf("Nombre");
    const idxCanalId = sHeaders.indexOf("Canal_ID");
    const idxCategoria = sHeaders.indexOf("Categoria");
    const idxIdioma = sHeaders.indexOf("Idioma");
    const idxFolderId = sHeaders.indexOf("Folder_ID");
    const idxAdminId = sHeaders.indexOf("Admin_ID");
    const idxAdminNombre = sHeaders.indexOf("Admin_Nombre");
    
    // Filtrar series por categoría e idioma
    let candidatas = [];
    for (let i = 1; i < seriesData.length; i++) {
      let cat = String(seriesData[i][idxCategoria] || "").trim();
      if (cat !== categoriaVal) continue;
      if (idiomaVal !== "cualquiera") {
        let idioma = String(seriesData[i][idxIdioma] || "").trim();
        if (idioma !== idiomaVal && idioma !== "Ambos") continue;
      }
      candidatas.push({
        nombre: String(seriesData[i][idxNombre]),
        canalId: normalizeIdFromSheet(seriesData[i][idxCanalId]),
        folderId: String(seriesData[i][idxFolderId] || ""),
        adminId: normalizeIdFromSheet(seriesData[i][idxAdminId] || ""),
        adminNombre: String(seriesData[i][idxAdminNombre] || "")
      });
    }
    
    if (candidatas.length === 0) {
      return { content: `❌ No hay series con categoría **${categoriaVal}**.`, flags: 64 };
    }
    
    // Shuffle para distribución justa
    for (let i = candidatas.length - 1; i > 0; i--) {
      let j = Math.floor(Math.random() * (i + 1));
      [candidatas[i], candidatas[j]] = [candidatas[j], candidatas[i]];
    }
    
    // Leer asignaciones existentes
    const asigSheet = getSheet("Asignaciones");
    const asigData = asigSheet.getDataRange().getValues();
    
    let columnaSheet = tareaAColumnaSheet(tareaVal);
    
    let capEncontrado = null;
    let serieEncontrada = null;
    
    for (let serie of candidatas) {
      let hoja = getOwnerSheetName(serie.adminId, serie.adminNombre);
      let sheet = ss.getSheetByName(hoja);
      if (!sheet) continue;
      
      let data = sheet.getDataRange().getValues();
      let fila0 = data[0] || [];
      let startCol = -1;
      for (let c = 0; c < fila0.length; c++) {
        if (String(fila0[c]).trim().toLowerCase() === serie.nombre.toLowerCase()) {
          startCol = c;
          break;
        }
      }
      if (startCol < 0) continue;
      
      let HEADERS = ["Cap","Idioma","RAW","Clean","Traduccion","Edicion","Recorte","Subido_Web","Fecha_RAW"];
      let colIdx = HEADERS.indexOf(columnaSheet);
      let rawIdx = HEADERS.indexOf("RAW");
      let cleanIdx = HEADERS.indexOf("Clean");
      let tradIdx = HEADERS.indexOf("Traduccion");
      
      for (let r = 4; r < data.length; r++) {
        let cap = String(data[r][startCol] || "").trim();
        if (!cap) break;
        
        // RAW debe estar listo
        let rawVal = String(data[r][startCol + rawIdx] || "");
        if (!rawVal.includes("✅")) continue;
        
        // Ya terminado? saltar
        let subidoVal = String(data[r][startCol + HEADERS.indexOf("Subido_Web")] || "");
        if (subidoVal.includes("✅")) continue;
        
        // La tarea ya terminada? saltar
        let tareaEstado = String(data[r][startCol + colIdx] || "");
        if (tareaEstado.includes("✅") || tareaEstado.includes("⏳")) continue;
        
        // Para Edición, necesita Clean + Traducción listos
        if (tareaVal === "Edicion") {
          let cleanVal = String(data[r][startCol + cleanIdx] || "");
          let tradVal = String(data[r][startCol + tradIdx] || "");
          if (!cleanVal.includes("✅") || !tradVal.includes("✅")) continue;
        }
        
        // Verificar que no esté ya asignado a alguien
        let yaAsignado = false;
        for (let a = 1; a < asigData.length; a++) {
          let ap = String(asigData[a][0] || "").toLowerCase();
          let ac = String(asigData[a][1] || "").trim();
          let at = String(asigData[a][2] || "").toLowerCase();
          let ae = String(asigData[a][4] || "").toLowerCase();
          if (ap === serie.nombre.toLowerCase() && ac === cap && at === tareaVal.toLowerCase() && ae !== "terminado") {
            yaAsignado = true;
            break;
          }
        }
        if (yaAsignado) continue;
        
        capEncontrado = cap;
        serieEncontrada = serie;
        break;
      }
      if (capEncontrado) break;
    }
    
    if (!capEncontrado) {
      return { content: `😔 No hay caps disponibles para **${tareaVal}** en categoría **${categoriaVal}** en este momento.`, flags: 64 };
    }
    
    // Registrar la asignación
    ensureHeaderColumn(asigSheet, "Fecha_Asignacion");
    asigSheet.appendRow([serieEncontrada.nombre, capEncontrado, tareaVal, userName, "En Proceso", asTextId(userId), timestampNowIso()]);
    actualizarEstadoTareaSerieBatchLocal(serieEncontrada.nombre, [capEncontrado], tareaVal, "⏳");
    
    // Dar rol automáticamente
    let roleId = asegurarRolCanal(guildId, serieEncontrada.nombre);
    let extraActions = [];
    
    if (roleId) {
      extraActions.push({
        url: `https://discord.com/api/v10/guilds/${guildId}/members/${userId}/roles/${roleId}`,
        method: "PUT",
        auth: `Bot ${DISCORD_BOT_TOKEN_NUBE}`,
        body: {}
      });
    }
    
    // Notificar en el canal de la serie
    let embedSerie = {
      title: "🌸 Nueva Autoasignación",
      description: `¡<@${userId}> se ha asignado a un nuevo capítulo!`,
      color: 0xffb6c1,
      fields: [
        { name: "🛠️ Tarea", value: `**${tareaVal}**`, inline: true },
        { name: "📌 Capítulo", value: `\`${capEncontrado}\``, inline: true }
      ],
      footer: { text: "Bloom Scans • Autoasignación" }
    };
    
    extraActions.push({
      url: `https://discord.com/api/v10/channels/${serieEncontrada.canalId}/messages`,
      method: "POST",
      auth: `Bot ${DISCORD_BOT_TOKEN_NUBE}`,
      body: { content: `<@${userId}>`, embeds: [embedSerie] }
    });
    
    // Log de asignaciones
    const CANAL_ASIGNACIONES_LOG = "1460771399999160442";
    extraActions.push({
      url: `https://discord.com/api/v10/channels/${CANAL_ASIGNACIONES_LOG}/messages`,
      method: "POST",
      auth: `Bot ${DISCORD_BOT_TOKEN_NUBE}`,
      body: { embeds: [{
        title: "✨ Autoasignación Registrada",
        color: 0x3498db,
        fields: [
          { name: "📘 Proyecto", value: `<#${serieEncontrada.canalId}>`, inline: true },
          { name: "📌 Capítulo", value: `\`${capEncontrado}\``, inline: true },
          { name: "👤 Staff", value: `<@${userId}>`, inline: true },
          { name: "🛠️ Tarea", value: `**${tareaVal}**`, inline: false }
        ],
        footer: { text: `Bloom Scans • ID:${userId}` }
      }] }
    });
    
    let embed = {
      title: "✅ ¡Te has asignado exitosamente!",
      color: 0x57F287,
      fields: [
        { name: "📚 Serie", value: serieEncontrada.nombre, inline: true },
        { name: "📌 Capítulo", value: `\`${capEncontrado}\``, inline: true },
        { name: "🛠️ Tarea", value: `**${tareaVal}**`, inline: true }
      ],
      footer: { text: "Cuando termines usa /terminado • Bloom Scans" }
    };
    
    return {
      embeds: [embed],
      flags: 64,
      extraActions: extraActions
    };
  } catch(e) {
    console.error("Error en cmdAsignarme:", e);
    return { content: "❌ Error al realizar la autoasignación: " + e.message, flags: 64 };
  } finally {
    lock.releaseLock();
  }
}

// ─────────────────────────────────────────────────────────────
// COMANDO: /agregar_serie
// ─────────────────────────────────────────────────────────────
function extraerFolderIdFromUrl(url) {
  let m = String(url).match(/\/folders\/([a-zA-Z0-9_-]+)/);
  if (m) return m[1];
  m = String(url).match(/id=([a-zA-Z0-9_-]+)/);
  if (m) return m[1];
  return "";
}

function findRawFolder(parentFolder) {
  const aliases = { raw: true, raws: true, "1raw": true, "01raw": true };
  const folders = parentFolder.getFolders();
  while (folders.hasNext()) {
    const folder = folders.next();
    const key = String(folder.getName()).toLowerCase().replace(/[^a-z0-9]/g, "");
    if (aliases[key]) return folder;
  }
  return null;
}

function cmdAgregarSerie(cmd) {
  if (!esAdminOCoordinador(cmd.roles, cmd.is_admin)) return { content: "❌ Sin permisos.", flags: 64 };
  
  const opts = cmd.options;
  const canalName = opts.canal_name || "";
  const canalId = opts.canal_id || opts.canal || "";
  const linkDrive = opts.link_drive || "";
  const categoriaVal = opts.categoria || "";
  const idiomaVal = opts.idioma || "";
  
  if (!canalId || !linkDrive) return { content: "❌ Faltan parámetros.", flags: 64 };
  
  let folderId = extraerFolderIdFromUrl(linkDrive);
  if (!folderId) return { content: "❌ No pude extraer el ID del Drive. Verifica el link.", flags: 64 };
  
  let nombreSerie = canalName || "serie-" + canalId;
  
  // Verificar duplicado
  const seriesSheet = getSheet("Series");
  const sData = seriesSheet.getDataRange().getValues();
  const sHeaders = sData[0];
  const idxNombre = sHeaders.indexOf("Nombre");
  const idxCanalId = sHeaders.indexOf("Canal_ID");
  const idxFolderId = sHeaders.indexOf("Folder_ID");
  
  for (let i = 1; i < sData.length; i++) {
    const sameName = normalizeSheetKey(sData[i][idxNombre]) === normalizeSheetKey(nombreSerie);
    const sameChannel = normalizeIdFromSheet(sData[i][idxCanalId]) === normalizeIdFromSheet(canalId);
    const sameFolder = String(sData[i][idxFolderId] || "").trim() === folderId;
    if (sameName || sameChannel || sameFolder) {
      let reason = sameName ? "nombre" : (sameChannel ? "canal" : "carpeta de Drive");
      return { content: `⚠️ La serie **${nombreSerie}** ya está registrada por ${reason}.`, flags: 64 };
    }
  }
  
  // Insertar nueva serie
  let fechaHoy = new Date().toISOString().substring(0, 10);
  seriesSheet.appendRow([
    nombreSerie,
    asTextId(canalId),
    linkDrive,
    folderId,
    categoriaVal,
    idiomaVal,
    fechaHoy,
    asTextId(cmd.user_id),
    cmd.user_name
  ]);
  
  // Invalidar caché
  CacheService.getScriptCache().remove("series_names");
  
  // Contar archivos en Drive
  let capsCount = 0;
  try {
    let folder = DriveApp.getFolderById(folderId);
    let subfolders = folder.getFolders();
    while (subfolders.hasNext()) {
      subfolders.next();
      capsCount++;
    }
  } catch(e) {}
  
  let embed = {
    title: "✅ Serie Agregada al Sistema",
    color: 0xffb6c1,
    fields: [
      { name: "📚 Serie", value: `<#${canalId}>`, inline: true },
      { name: "🏷️ Categoría", value: categoriaVal, inline: true },
      { name: "🌐 Idioma", value: idiomaVal, inline: true },
      { name: "👤 Admin", value: `<@${cmd.user_id}>`, inline: true },
      { name: "📁 Carpetas en Drive", value: `**${capsCount}** detectadas`, inline: false }
    ],
    footer: { text: "Bloom Scans • Sistema de producción" }
  };
  
  return { embeds: [embed], flags: 64 };
}

// ─────────────────────────────────────────────────────────────
// COMANDO: /actualizar_drive
// ─────────────────────────────────────────────────────────────
function cmdActualizarDrive(cmd) {
  if (!esAdminOCoordinador(cmd.roles, cmd.is_admin)) return { content: "❌ Sin permisos.", flags: 64 };
  
  const serieName = cmd.options && cmd.options.serie_name ? cmd.options.serie_name : "";
  if (!serieName) return { content: "❌ Falta la serie.", flags: 64 };
  
  const seriesSheet = getSheet("Series");
  const sData = seriesSheet.getDataRange().getValues();
  const sHeaders = sData[0];
  let folderId = "";
  let adminId = "";
  let adminNombre = "";
  
  for (let i = 1; i < sData.length; i++) {
    if (String(sData[i][sHeaders.indexOf("Nombre")]).toLowerCase() === serieName.toLowerCase()) {
      folderId = String(sData[i][sHeaders.indexOf("Folder_ID")] || "");
      adminId = normalizeIdFromSheet(sData[i][sHeaders.indexOf("Admin_ID")] || "");
      adminNombre = String(sData[i][sHeaders.indexOf("Admin_Nombre")] || "");
      break;
    }
  }
  
  if (!folderId) return { content: "❌ Serie no encontrada o sin Folder_ID.", flags: 64 };
  
  let hoja = getOwnerSheetName(adminId, adminNombre) || "Sin responsable";
  
  // Leer carpetas RAW del Drive
  let capsEncontrados = [];
  try {
    let folder = DriveApp.getFolderById(folderId);
    let rawFolder = findRawFolder(folder);
    if (rawFolder) {
      let files = rawFolder.getFolders();
      while (files.hasNext()) {
        let f = files.next();
        capsEncontrados.push(f.getName());
      }
      // Si no hay subcarpetas, contar archivos
      if (capsEncontrados.length === 0) {
        let archivos = rawFolder.getFiles();
        while (archivos.hasNext()) {
          capsEncontrados.push(archivos.next().getName());
        }
      }
    }
  } catch(e) {
    return { content: "❌ Error accediendo a Drive: " + e.message, flags: 64 };
  }
  
  if (capsEncontrados.length === 0) {
    return { content: "⚠️ No se encontraron capítulos en la carpeta RAW.", flags: 64 };
  }
  
  // Actualizar la hoja de la serie
  let capsNorm = capsEncontrados.map(function(n) {
    let m = n.match(/(\d+(?:[\.\-]\d+)?)/);
    return m ? m[1] : n;
  });
  
  updateEstadoTareaSerieBatch(serieName, hoja, capsNorm, "RAW", "✅", true);
  
  return {
    content: "✅ **" + serieName + "** actualizada desde Drive.\n📁 **" + capsEncontrados.length + "** capítulos RAW sincronizados en la hoja `" + hoja + "`.",
    flags: 64
  };
}

// ─────────────────────────────────────────────────────────────
// COMANDO: /refrescar_asignaciones
// ─────────────────────────────────────────────────────────────
function cmdRefrescarAsignaciones(cmd) {
  if (!esAdminOCoordinador(cmd.roles, cmd.is_admin)) return { content: "❌ Sin permisos.", flags: 64 };
  
  const sheet = getSheet("Asignaciones");
  const data = sheet.getDataRange().getValues();
  
  if (data.length < 2) {
    return { content: "⚠️ No hay asignaciones registradas.", flags: 64 };
  }
  
  let totalAsig = data.length - 1;
  let enProceso = 0;
  let terminadas = 0;
  let porSerie = {};
  
  for (let i = 1; i < data.length; i++) {
    let estado = String(data[i][4] || "").toLowerCase();
    if (estado === "terminado") {
      terminadas++;
    } else {
      enProceso++;
    }
    let proy = String(data[i][0] || "Sin proyecto");
    if (!porSerie[proy]) porSerie[proy] = 0;
    porSerie[proy]++;
  }
  
  let seriesListTxt = "";
  let seriesArr = Object.entries(porSerie).sort(function(a,b) { return b[1] - a[1]; });
  seriesArr.slice(0, 10).forEach(function(entry) {
    seriesListTxt += "• **" + entry[0] + "** — " + entry[1] + " asignaciones\n";
  });
  if (seriesArr.length > 10) seriesListTxt += "... y " + (seriesArr.length - 10) + " series más.\n";
  
  let embed = {
    title: "🔄 Estado de Asignaciones",
    color: 0x3498db,
    fields: [
      { name: "📊 Total", value: "`" + totalAsig + "` asignaciones", inline: true },
      { name: "⏳ En Proceso", value: "`" + enProceso + "`", inline: true },
      { name: "✅ Terminadas", value: "`" + terminadas + "`", inline: true },
      { name: "📚 Por Serie", value: seriesListTxt || "Sin datos", inline: false }
    ],
    footer: { text: "Bloom Scans • Datos sincronizados desde Google Sheets" }
  };
  
  return { embeds: [embed], flags: 64 };
}


// ─────────────────────────────────────────────────────────────
// COMANDO: /asignaciones_usuario
// ─────────────────────────────────────────────────────────────
function cmdAsignacionesUsuario(cmd) {
  if (!esAdminOCoordinador(cmd.roles, cmd.is_admin)) {
    return { content: "❌ Sin permisos.", flags: 64 };
  }
  
  const userId = cmd.options.usuario_user_id || cmd.options.usuario;
  const userName = cmd.options.usuario_user_name || "Usuario";
  
  const sheet = getSheet("Asignaciones");
  if (!sheet) return { content: "❌ Error: Hoja Asignaciones no encontrada", flags: 64 };
  
  const data = sheet.getDataRange().getValues();
  if (data.length < 2) return { content: "La hoja está vacía.", flags: 64 };
  
  const headers = data[0];
  let mis = [];
  const apodoUser = getApodoValue(userId, userName);
  
  data.slice(1).forEach(row => {
    let r = {};
    headers.forEach((h, i) => r[h] = row[i]);
    if (matchesUser(r, userId, userName, apodoUser) && String(r.Estado).trim().toLowerCase() !== "terminado") {
      mis.push(r);
    }
  });
  
  if (mis.length === 0) {
    return {
      embeds: [{
        title: `📋 Asignaciones | ${userName}`,
        description: "El usuario no tiene capítulos asignados actualmente.",
        color: 0x2ecc71,
        footer: { text: "Bloom Scans" }
      }],
      flags: 64
    };
  }
  
  let proyectos = {};
  for (let f of mis) {
      let proy = f.Proyecto || "Sin proyecto";
      if (!proyectos[proy]) proyectos[proy] = [];
      let cap = f.Capitulo || f["Capítulo"] || "?";
      let tarea = f.Tarea || "?";
      let estado = String(f.Estado || "").trim();
      let icono = estado.toLowerCase() === "en proceso" ? "⏳" : "📝";
      proyectos[proy].push(`> ${icono} **Cap ${cap}** — \`${tarea}\` *( ${estado} )*`);
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
  
  const avatarUrl = cmd.options && cmd.options.usuario_user_avatar ? cmd.options.usuario_user_avatar : null;
  let embed = {
    title: `📋 Panel de Asignaciones | ${userName}`,
    description: "Tareas actuales ordenadas por proyecto:",
    color: 0xffb6c1,
    fields: fields,
    footer: { text: "Bloom Scans • Consulta Admin" }
  };
  
  if (avatarUrl) {
    embed.thumbnail = { url: avatarUrl };
  }
  
  return {
    embeds: [embed],
    flags: 64
  };
}

// ─────────────────────────────────────────────────────────────
// COMANDO: /mis_trabajos (con paginación tipo botón)
// ─────────────────────────────────────────────────────────────
function cmdMisTrabajos(cmd) {
  const userId = cmd.user_id;
  const userName = cmd.user_name;
  const opts = cmd.options;
  
  // Opciones base
  let mesNum = parseInt(opts.mes) || (new Date().getMonth() + 1);
  let anioNum = parseInt(opts.anio) || new Date().getFullYear();
  let pagina = parseInt(opts.page) || 1;
  
  // ── CACHÉ: Intentar leer del caché primero (páginas 2+ serán instantáneas) ──
  const cacheKey = "mis_trabajos_" + userId + "_" + mesNum + "_" + anioNum;
  const cache = CacheService.getScriptCache();
  let trabajos = null;
  
  const cached = cache.get(cacheKey);
  if (cached) {
    try {
      trabajos = JSON.parse(cached);
    } catch(e) {
      trabajos = null;
    }
  }
  
  // Si no hay caché, consultar la hoja (solo pasa en página 1 o caché expirado)
  if (!trabajos) {
    let sheetName = "Registro";
    let hoyMes = new Date().getMonth() + 1;
    let hoyAnio = new Date().getFullYear();
    
    if (mesNum !== hoyMes || anioNum !== hoyAnio) {
      let mesName = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"][mesNum-1];
      sheetName = "Registro_" + mesName + "_" + anioNum;
    }
    
    const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
    const sheetReg = ss.getSheetByName(sheetName);
    
    if (!sheetReg) {
      return { content: "No hay datos para el mes " + mesNum + "/" + anioNum + ".", flags: 64 };
    }
    
    const dataReg = sheetReg.getDataRange().getValues();
    if (dataReg.length < 2) {
      return { content: "No hay registros para este mes.", flags: 64 };
    }
    
    const headersReg = dataReg[0];
    
    // Obtener apodo una sola vez fuera del loop
    let apodoUser = "";
    try {
      apodoUser = String(getApodoValue(userId, userName) || "").trim().toLowerCase();
    } catch(e) {}
    
    trabajos = [];
    
    for (let i = 1; i < dataReg.length; i++) {
      let r = {};
      headersReg.forEach(function(h, idx) { r[h] = dataReg[i][idx]; });
      
      // Si la hoja es la actual, filtrar por mes de la fecha
      if (sheetName === "Registro") {
        let m_f = -1;
        const ym = getYearMonth(r.Fecha);
        m_f = ym.month;
        const y_f = ym.year;
        if ((m_f !== -1 && m_f !== mesNum) || (y_f && y_f !== anioNum)) continue;
      }
      
      let isMatch = false;
      let uidStr = normalizeIdFromSheet(r.ID_Usuario || "");
      
      // 1. Intentar por ID exacto
      if (uidStr && uidStr !== "undefined" && uidStr === normalizeIdFromSheet(userId)) {
        isMatch = true;
      }
      
      // 2. Fallback por nombre/apodo (IDs corrompidos por notación científica)
      if (!isMatch) {
        let sheetUser = String(r.Usuario || "").trim().toLowerCase();
        let discordUser = String(userName).trim().toLowerCase();
        
        if (sheetUser && discordUser && (sheetUser === discordUser || sheetUser.includes(discordUser) || discordUser.includes(sheetUser))) {
          isMatch = true;
        } else if (sheetUser && apodoUser && (sheetUser === apodoUser || sheetUser.includes(apodoUser) || apodoUser.includes(sheetUser))) {
          isMatch = true;
        }
      }
      
      if (isMatch) {
        let proy = r.Proyecto || "Desconocido";
        let cap = getCap(r);
        let tarea = r.Tarea || "?";
        let fecha = "?";
        if (r.Fecha instanceof Date) {
          fecha = Utilities.formatDate(r.Fecha, "America/Argentina/Buenos_Aires", "yyyy-MM-dd");
        } else if (r.Fecha) {
          fecha = String(r.Fecha).substring(0, 10);
        }
        trabajos.push("• **" + proy + "** — Cap `" + cap + "` — _" + tarea + "_  (" + fecha + ")");
      }
    }
    
    // Guardar en caché por 10 minutos (600 segundos)
    if (trabajos.length > 0) {
      try {
        const cachePayload = JSON.stringify(trabajos);
        if (cachePayload.length < 90000) cache.put(cacheKey, cachePayload, 600);
      } catch(e) {}
    }
  }
  
  if (trabajos.length === 0) {
    return { content: "No tienes capítulos finalizados en " + mesNum + "/" + anioNum + ".", flags: 64 };
  }
  
  // Paginación
  var ITEMS_PER_PAGE = 15;
  var totalPaginas = Math.ceil(trabajos.length / ITEMS_PER_PAGE);
  if (pagina > totalPaginas) pagina = totalPaginas;
  if (pagina < 1) pagina = 1;
  
  var start = (pagina - 1) * ITEMS_PER_PAGE;
  var end = start + ITEMS_PER_PAGE;
  var paginaTrabajos = trabajos.slice(start, end);
  
  var embed = {
    title: "📚 Mis Trabajos Finalizados",
    description: limitDiscordText("Mostrando tus capítulos terminados en **" + mesNum + "/" + anioNum + "**.\nTotal de trabajos: **" + trabajos.length + "**\n\n" + paginaTrabajos.join("\n"), 4000),
    color: 0x9b59b6,
    footer: { text: "Página " + pagina + " de " + totalPaginas + " • Bloom Scans" }
  };
  
  var components = [];
  if (totalPaginas > 1) {
    var row = { type: 1, components: [] };
    
    if (pagina > 1) {
      row.components.push({
        type: 2,
        style: 1,
        label: "◀ Anterior",
        custom_id: "mis_trabajos|page=" + (pagina-1) + "|mes=" + mesNum + "|anio=" + anioNum
      });
    }
    
    if (pagina < totalPaginas) {
      row.components.push({
        type: 2,
        style: 1,
        label: "Siguiente ▶",
        custom_id: "mis_trabajos|page=" + (pagina+1) + "|mes=" + mesNum + "|anio=" + anioNum
      });
    }
    
    components.push(row);
  }
  
  return { embeds: [embed], components: components, flags: 64 };
}

