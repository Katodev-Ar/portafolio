# 🚀 INICIO RÁPIDO - MANHWA TRANSLATOR

## ⚡ PARA EMPEZAR EN 5 MINUTOS

### PASO 1: Configurar Servidor

```bash
# 1. Sube server_COMPLETE.py a Render.com
# 2. Agrega variable de entorno:
GEMINI_API_KEY=tu_clave_aqui

# 3. Espera deployment (2-3 minutos)
# 4. Copia la URL: https://tu-app.onrender.com
```

### PASO 2: Actualizar URL en Desktop App

Abre `app_desktop_COMPLETE.py` y cambia:

```python
SERVER_URL = "https://tu-app.onrender.com"  # ← Tu URL de Render
```

### PASO 3: Instalar Dependencias

```bash
pip install -r requirements_desktop.txt
```

### PASO 4: Ejecutar

```bash
python app_desktop_COMPLETE.py
```

---

## 🔑 CREAR PRIMERA LICENCIA

### Opción A: SQL Directo (Render Dashboard)

```sql
INSERT INTO licenses (key, type, credits, is_staff)
VALUES ('BLOOM-ADMIN-001', 'Admin', 10000, 1);
```

### Opción B: Python Script

Crea `create_license.py`:

```python
import sqlite3

conn = sqlite3.connect('manhwa_translator.db')
c = conn.cursor()

c.execute('''
    INSERT INTO licenses (key, type, credits, is_staff)
    VALUES (?, ?, ?, ?)
''', ('BLOOM-ADMIN-001', 'Admin', 10000, 1))

conn.commit()
conn.close()
print("Licencia creada: BLOOM-ADMIN-001")
```

Ejecuta:
```bash
python create_license.py
```

---

## 📁 CONFIGURAR GOOGLE DRIVE (Solo para Modo Staff)

### 1. Google Cloud Console

1. Ir a: https://console.cloud.google.com
2. Crear proyecto "Manhwa Translator"
3. Activar "Google Drive API"
4. Credenciales → OAuth 2.0 → Aplicación de escritorio
5. Descargar `credentials.json`

### 2. Colocar credentials.json

```
manhwa-translator/
├── app_desktop_COMPLETE.py
├── credentials.json  ← Aquí
└── ...
```

---

## 🏗️ ESTRUCTURA DEL DRIVE PARA SERIES

```
Serie: Para tu final perfecto/
├── RAW/              ← Imágenes originales por capítulo
│   ├── 1/
│   │   ├── 01.jpg
│   │   ├── 02.jpg
│   ├── 2/
│   ├── 7/
│       ├── 01.jpg
│       ├── 02.jpg
├── TRADUCCION/       ← Aquí se guardan los resultados
    ├── Traduccion_1.txt
    ├── Traduccion_7.txt
```

---

## ➕ AGREGAR SERIE (Admin)

### Opción A: SQL

```sql
INSERT INTO series (name, drive_link, created_at, created_by)
VALUES (
    'Para tu final perfecto',
    'https://drive.google.com/drive/folders/TU_FOLDER_ID',
    datetime('now'),
    'BLOOM-ADMIN-001'
);
```

### Opción B: API con Postman/Curl

```bash
curl -X POST https://tu-app.onrender.com/api/series/add \
  -H "Content-Type: application/json" \
  -d '{
    "admin_key": "BLOOM-ADMIN-001",
    "name": "Para tu final perfecto",
    "drive_link": "https://drive.google.com/drive/folders/TU_FOLDER_ID"
  }'
```

---

## 👥 CREAR LICENCIAS PARA TU EQUIPO

### Staff (con acceso a Drive)

```sql
INSERT INTO licenses (key, type, credits, is_staff)
VALUES ('STAFF-JUAN-001', 'Staff', 500, 1);
```

### Usuarios Normales (sin Drive)

```sql
INSERT INTO licenses (key, type, credits, is_staff)
VALUES ('USER-SCAN-XYZ-001', 'Professional', 100, 0);
```

---

## 🎯 FLUJO COMPLETO - EJEMPLO

### Como Admin (Tú):

```
1. Creas serie en DB
2. Organizas Drive con estructura RAW/TRADUCCION
3. Compartes Drive con tu staff
4. Das licencia STAFF a tu equipo
```

### Como Staff (Tu equipo):

```
1. Abre app → Modo Bloom Staff
2. Login Google
3. Selecciona serie
4. Selecciona capítulo 7
5. App descarga imágenes de RAW/7/
6. Trabaja (OCR, traducción)
7. Guarda en Drive → TRADUCCION/Traduccion_7.txt
```

### Como Usuario Normal (Otros scans):

```
1. Abre app → Modo Local
2. Carga imágenes desde PC
3. Trabaja normalmente
4. Exporta todo localmente
```

---

## 🛠️ COMPILAR A .EXE

```bash
# Windows
compile.bat

# O manualmente:
pyinstaller --onefile --windowed ^
  --add-data "models;models" ^
  --name "ManhwaTranslator" ^
  app_desktop_COMPLETE.py
```

**Resultado:** `dist/ManhwaTranslator.exe`

**Distribuir:**
- ManhwaTranslator.exe
- credentials.json (para staff)

---

## ✅ CHECKLIST FINAL

### Servidor:
- [ ] Subido a Render
- [ ] Variable GEMINI_API_KEY configurada
- [ ] URL copiada y actualizada en desktop app

### Desktop App:
- [ ] SERVER_URL actualizado
- [ ] Dependencias instaladas
- [ ] credentials.json descargado (si usas modo staff)
- [ ] Carpeta models/ con archivos .bin y .param

### Base de Datos:
- [ ] Licencia admin creada
- [ ] Serie(s) agregada(s) (si usas modo staff)
- [ ] Licencias staff/usuarios creadas

### Drive (si usas modo staff):
- [ ] Estructura RAW/TRADUCCION creada
- [ ] Imágenes organizadas por capítulo en RAW/
- [ ] Permisos compartidos con cuentas staff

---

## 🎉 ¡LISTO PARA USAR!

Ya tienes:
- ✅ Sistema completo funcionando
- ✅ Modo Local para usuarios normales
- ✅ Modo Staff con Google Drive
- ✅ Sistema de etiquetas
- ✅ Clean de imágenes
- ✅ Exportación completa

**¡A traducir manhwas!** 🌸
