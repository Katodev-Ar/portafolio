# 🖨️ PrintBridge

Servidor de impresión para compartir tu impresora USB con todos los dispositivos de tu red.

## ¿Cómo funciona?

Tu PC con la impresora corre esta app. Cualquier celular, tablet u otra computadora en tu WiFi puede imprimir desde el navegador sin instalar nada.

```
[Celular / Otra PC]  ──WiFi──►  [PrintBridge en tu PC]  ──USB──►  [Impresora]
```

---

## 📦 Instalación

### Requisitos previos

1. **Python 3.10 o superior**
   - Descarga desde https://www.python.org/downloads/
   - ⚠️ Al instalar, marca **"Add Python to PATH"**

2. **LibreOffice** (para imprimir DOCX, XLSX, PPTX, etc.)
   - Descarga desde https://www.libreoffice.org/download/
   - Instala con las opciones predeterminadas

3. **SumatraPDF** (recomendado para mejor impresión)
   - Descarga desde https://www.sumatrapdfreader.org/download-free-pdf-viewer
   - Instala con las opciones predeterminadas

### Instalar PrintBridge

1. Extrae todos los archivos en una carpeta (ej: `C:\PrintBridge\`)
2. Doble clic en **`install.bat`**
3. Espera a que termine la instalación
4. ¡Listo! La app se abrirá automáticamente

---

## 🚀 Uso diario

### Iniciar PrintBridge
- Doble clic en el icono **PrintBridge** del escritorio
- La app se minimiza a la bandeja del sistema (junto al reloj)
- El ícono verde = servidor activo

### Imprimir desde otro dispositivo
1. Abre el navegador (Chrome, Firefox, Safari, etc.)
2. Escribe la dirección que aparece en la app, por ejemplo:
   ```
   http://192.168.1.100:7878
   ```
3. Ingresa el PIN (por defecto: **1234**)
4. ¡Sube tu archivo y a imprimir!

### Cambiar el PIN
1. Abre PrintBridge en tu PC
2. Ve a la pestaña **Configuración**
3. Cambia el PIN y guarda

---

## 📁 Formatos soportados

| Tipo | Formatos |
|------|----------|
| Documentos | PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, ODT, RTF, TXT |
| Imágenes | JPG, PNG, BMP, TIFF, WEBP, GIF |

---

## 🔒 Seguridad

- El servidor solo es accesible desde tu red WiFi local
- Cada dispositivo necesita el PIN **una sola vez**
- Puedes ver y revocar dispositivos desde la app

---

## ❓ Solución de problemas

**No puedo conectarme desde mi celular:**
- Verifica que el celular esté en la misma red WiFi que la PC
- Comprueba que el firewall de Windows no esté bloqueando el puerto 7878
- Ve a: Panel de control → Firewall → Permitir aplicación → Python

**La impresora no aparece:**
- Verifica que la impresora esté conectada por USB y encendida
- En Windows: Configuración → Bluetooth y dispositivos → Impresoras
- Reinicia PrintBridge después de conectar la impresora

**No convierte archivos DOCX/XLSX:**
- Instala LibreOffice desde https://www.libreoffice.org

---

## 📂 Estructura del proyecto

```
printbridge/
├── app.py              ← Aplicación principal (ventana + bandeja)
├── server.py           ← Servidor web (FastAPI)
├── printer.py          ← Control de impresora Windows
├── queue_manager.py    ← Cola de impresión
├── device_manager.py   ← Gestión de dispositivos autorizados
├── config.py           ← Configuración
├── web/
│   └── index.html      ← Interfaz web completa
├── data/               ← Datos guardados (config, historial, etc.)
├── requirements.txt    ← Dependencias Python
└── install.bat         ← Instalador automático
```
