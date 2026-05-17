
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
  
  data.slice(1).forEach(row => {
    let r = {};
    headers.forEach((h, i) => r[h] = row[i]);
    if (String(r.ID_Usuario).trim() === String(userId) && String(r.Estado).trim().toLowerCase() !== "terminado") {
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
          value: items.slice(0, 10).join("\n") + (items.length > 10 ? "\n> ..." : ""),
          inline: false
      });
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
  
  let sheetName = "Registro";
  let hoyMes = new Date().getMonth() + 1;
  let hoyAnio = new Date().getFullYear();
  
  if (mesNum !== hoyMes || anioNum !== hoyAnio) {
    let mesName = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"][mesNum-1];
    sheetName = `Registro_${mesName}_${anioNum}`;
  }
  
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheetReg = ss.getSheetByName(sheetName);
  
  if (!sheetReg) {
    return { content: `❌ No hay datos para el mes ${mesNum}/${anioNum}.`, flags: 64 };
  }
  
  const dataReg = sheetReg.getDataRange().getValues();
  if (dataReg.length < 2) {
    return { content: `❌ No hay registros para este mes.`, flags: 64 };
  }
  
  const headersReg = dataReg[0];
  let trabajos = [];
  
  for (let i = 1; i < dataReg.length; i++) {
    let r = {};
    headersReg.forEach((h, idx) => r[h] = dataReg[i][idx]);
    
    // Si la hoja es la actual, filtrar por mes de la fecha
    if (sheetName === "Registro") {
      let fStr = String(r.Fecha || "");
      if (fStr.length >= 7) {
        let m_f = parseInt(fStr.substring(5, 7));
        if (m_f !== mesNum) continue;
      }
    }
    
    if (String(r.ID_Usuario).trim() === String(userId).trim()) {
      let proy = r.Proyecto || "Desconocido";
      let cap = getCap(r);
      let tarea = r.Tarea || "?";
      let fecha = r.Fecha ? String(r.Fecha).substring(0, 10) : "?";
      trabajos.push(`• **${proy}** — Cap \`${cap}\` — _${tarea}_  (${fecha})`);
    }
  }
  
  if (trabajos.length === 0) {
    return { content: `No tienes capítulos finalizados en ${mesNum}/${anioNum}.`, flags: 64 };
  }
  
  // Paginación
  const ITEMS_PER_PAGE = 15;
  const totalPaginas = Math.ceil(trabajos.length / ITEMS_PER_PAGE);
  if (pagina > totalPaginas) pagina = totalPaginas;
  if (pagina < 1) pagina = 1;
  
  const start = (pagina - 1) * ITEMS_PER_PAGE;
  const end = start + ITEMS_PER_PAGE;
  const paginaTrabajos = trabajos.slice(start, end);
  
  let embed = {
    title: `📚 Mis Trabajos Finalizados`,
    description: `Mostrando tus capítulos terminados en **${mesNum}/${anioNum}**.\nTotal de trabajos: **${trabajos.length}**\n\n` + paginaTrabajos.join("\n"),
    color: 0x9b59b6,
    footer: { text: `Página ${pagina} de ${totalPaginas} • Bloom Scans` }
  };
  
  let components = [];
  if (totalPaginas > 1) {
    let row = { type: 1, components: [] };
    
    if (pagina > 1) {
      row.components.push({
        type: 2,
        style: 1,
        label: "◀️ Anterior",
        custom_id: `mis_trabajos|page=${pagina-1}|mes=${mesNum}|anio=${anioNum}`
      });
    }
    
    if (pagina < totalPaginas) {
      row.components.push({
        type: 2,
        style: 1,
        label: "Siguiente ▶️",
        custom_id: `mis_trabajos|page=${pagina+1}|mes=${mesNum}|anio=${anioNum}`
      });
    }
    
    components.push(row);
  }
  
  return { embeds: [embed], components: components, flags: 64 };
}
