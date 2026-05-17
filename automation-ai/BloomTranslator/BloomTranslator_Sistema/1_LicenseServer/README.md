# 🔑 SERVIDOR DE LICENCIAS - BLOOM TRANSLATOR

## 📋 INSTALACIÓN RÁPIDA

1. **Doble click en:** `RUN_SERVER.bat`
2. **Abrir navegador:** http://localhost:7777/admin
3. **¡Listo!** Ya puedes generar licencias

---

## 🎯 USO

### Generar Licencia FULL
1. Ir a http://localhost:7777/admin
2. Seleccionar tipo: **FULL**
3. Ingresar créditos (ej: 500)
4. Click en **Generar Licencia**
5. Copiar la key generada
6. Enviar al cliente

### Generar Licencia STAFF
1. Igual que FULL pero seleccionar **STAFF**
2. Ingresar ID de carpeta de Google Drive
3. Esta licencia solo podrá importar de esa carpeta

### Generar Key de Recarga
1. En la sección "Generar Key de Recarga"
2. Ingresar créditos a añadir (ej: 100)
3. Enviar al cliente para que la use en la app

---

## ⚙️ CONFIGURACIÓN

### Cambiar costos de créditos
Editar `config.json`:
```json
{
  "costs": {
    "cargar_imagen_local": 1,
    "limpiar_imagen": 2,
    "upscale_hd": 1,
    ...
  }
}
```

Reiniciar servidor para aplicar cambios.

---

## 🛡️ SEGURIDAD

- ✅ Solo corre en tu PC (localhost)
- ✅ NO necesita internet público
- ✅ Base de datos encriptada
- ✅ Keys de un solo uso
- ✅ Device binding (1 key = 1 PC)

---

## 🔧 SOLUCIÓN DE PROBLEMAS

**Error: "Puerto 7777 en uso"**
- Cerrar otras apps que usen ese puerto
- O cambiar puerto en `license_server.py` línea final

**Error: "Python no encontrado"**
- Instalar Python 3.9+ desde python.org
- Reiniciar PC después de instalar

**Error: "No se pueden instalar dependencias"**
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 📊 ESTADÍSTICAS

Ver en: http://localhost:7777/admin
- Total de licencias generadas
- Licencias activas
- Créditos consumidos
- Historial de activaciones

---

## 🆘 SOPORTE

Cualquier problema, contacta a:
- Discord: @itsuki0357
- Email: nekomanhwas@gmail.com
