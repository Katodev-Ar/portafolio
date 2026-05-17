/**
 * cargar_correos.js — Pega esto en Google Apps Script y ejecuta cargarCorreosMasivos()
 * Solo necesitas correrlo UNA vez para cargar los correos existentes.
 * Después de eso, los usuarios usan /registrar_correo normalmente.
 */
function cargarCorreosMasivos() {
  const SPREADSHEET_ID = "1U_28Ggvm_ulCnpXASBkhzXH3VTBt79dCUS8gxRgWINk";
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  
  let sheet = ss.getSheetByName("Correos");
  if (!sheet) {
    sheet = ss.insertSheet("Correos");
    sheet.appendRow(["ID_Usuario", "Correos", "Nombre_Discord"]);
  }
  
  // Datos extraídos del archivo correos.txt
  // Formato: [nombre_discord, correos_separados_por_coma]
  const correosData = [
    ["Bustlerz en decadencia", "fujoota30@gmail.com"],
    ["Celeste", "riverojuarezpaula@gmail.com"],
    ["ArtoMimme", "artomime@gmail.com"],
    ["loutomtom", "dayanaramendoza918@gmail.com"],
    ["Paulina García", "pg7209583@gmail.com"],
    ["Anthony", "nkaito005@gmail.com"],
    ["Junnie", "alejaacvdo@gmail.com, studio.junae@gmail.com"],
    ["Sopcat", "sophistar2406@gmail.com"],
    ["sof", "sofart266@gmail.com"],
    ["Deleted User", "dionix.dan03@gmail.com"],
    ["Emma", "v.wend.1233@gmail.com"],
    ["Putamadredexter", "Comcomlagrimita@gmail.com"],
    ["farock8", "faridumv@gmail.com"],
    ["Masoquista posiblemente murido", "wdgosthymore@gmail.com"],
    ["Estrella", "estres20052004@gmail.com"],
    ["Lucia", "annlu.sm16@gmail.com"],
    ["FosterCat", "fortunefostercat@gmail.com"],
    ["Star", "suckmydickpotter@gmail.com"],
    ["Quiiits.", "Nessquist@gmail.com"],
    ["MordreedT", "sirrera7@gmail.com"],
    ["Gomita", "miquiitha@gmail.com"],
    ["jqk", "ari.acomar97@gmail.com"],
    ["N.gv_", "nath.gv1001@gmail.com"],
    ["nyxis", "petitenyxis.tl@gmail.com"],
    ["Chad_fics", "masm122208@gmail.com"],
    ["Wiron", "andremoranrosales@gmail.com"],
    ["Nagherine", "kaguyelynagherine@gmail.com"],
    ["Wilest002", "nose28134@gmail.com"],
    ["Coni", "mushroomsoup4833@gmail.com, mushroomsoup4833.2@gmail.com"],
    ["Raizelt", "raizelt77@gmail.com"],
    ["JAMÓN", "jajamon140lol@gmail.com"],
    ["DeStronx7", "leandrofarfan06@gmail.com"],
    ["MONSTER", "Chiefm915@gmail.com"],
    ["Moon", "nightmarenight115@gmail.com"],
    ["El pirateador", "dibri.segrea@gmail.com"],
    ["Fwrchu", "fernandalopezveraa@gmail.com"],
    ["Ansho", "Anshosama@gmail.com"],
    ["Yoru", "est.ichiro11@gmail.com"],
    ["Tita12", "pmiau162@gmail.com"],
    ["momo la dinastia", "abriltales04@gmail.com"],
  ];
  
  // Intentar matchear con la hoja de Registro para obtener Discord IDs
  let regSheet = ss.getSheetByName("Registro");
  let userIdMap = {}; // nombre -> user_id
  
  if (regSheet) {
    let regData = regSheet.getDataRange().getValues();
    for (let i = 1; i < regData.length; i++) {
      let nombre = String(regData[i][1] || "").trim().toLowerCase();
      let userId = String(regData[i][5] || "").trim();
      if (nombre && userId) {
        userIdMap[nombre] = userId;
      }
    }
  }
  
  // También buscar en la hoja Asignaciones
  let asigSheet = ss.getSheetByName("Asignaciones");
  if (asigSheet) {
    let asigData = asigSheet.getDataRange().getValues();
    for (let i = 1; i < asigData.length; i++) {
      let nombre = String(asigData[i][3] || "").trim().toLowerCase();
      let userId = String(asigData[i][5] || "").trim();
      if (nombre && userId && !userIdMap[nombre]) {
        userIdMap[nombre] = userId;
      }
    }
  }
  
  // Leer correos existentes para no duplicar
  let existingData = sheet.getDataRange().getValues();
  let existingIds = new Set();
  let existingNames = new Set();
  for (let i = 1; i < existingData.length; i++) {
    existingIds.add(String(existingData[i][0]).trim());
    existingNames.add(String(existingData[i][2] || "").trim().toLowerCase());
  }
  
  let cargados = 0;
  let sinId = 0;
  
  for (let [nombre, correos] of correosData) {
    let nombreLower = nombre.toLowerCase();
    
    // Buscar Discord ID
    let userId = userIdMap[nombreLower] || "";
    
    // Si no se encontró, intentar búsqueda parcial
    if (!userId) {
      for (let key in userIdMap) {
        if (key.includes(nombreLower) || nombreLower.includes(key)) {
          userId = userIdMap[key];
          break;
        }
      }
    }
    
    // Verificar que no esté ya registrado
    if (userId && existingIds.has(userId)) continue;
    if (!userId && existingNames.has(nombreLower)) continue;
    
    let idToUse = userId || "PENDIENTE_" + nombre.replace(/\s+/g, "_");
    sheet.appendRow([idToUse, correos, nombre]);
    cargados++;
    if (!userId) sinId++;
  }
  
  Logger.log(`✅ Cargados: ${cargados} correos. Sin Discord ID: ${sinId} (marcados como PENDIENTE_)`);
  Logger.log("Los usuarios con ID PENDIENTE_ se actualizarán automáticamente cuando usen /registrar_correo.");
}
