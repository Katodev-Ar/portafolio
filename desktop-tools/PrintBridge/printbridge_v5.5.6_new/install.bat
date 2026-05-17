@echo off
title PrintBridge - Instalador

echo.
echo  =========================================
echo       PRINTBRIDGE  -  Instalador
echo  =========================================
echo.

REM Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python no encontrado.
    echo  Descargalo desde https://www.python.org/downloads/
    echo  Asegurate de marcar "Add Python to PATH" al instalar.
    pause
    exit /b 1
)
echo  [OK] Python encontrado.

REM Crear entorno virtual
if not exist "venv" (
    echo  Creando entorno virtual...
    python -m venv venv
)
echo  [OK] Entorno virtual listo.

REM Instalar dependencias (ignorar aviso de upgrade de pip)
echo  Instalando dependencias (puede tardar unos minutos)...
call venv\Scripts\pip install --upgrade pip --quiet 2>nul
call venv\Scripts\pip install -r requirements.txt --quiet
echo  [OK] Dependencias instaladas.

REM Crear carpetas necesarias
if not exist "data" mkdir data
if not exist "web" mkdir web
echo  [OK] Carpetas creadas.

REM Crear script de inicio
echo @echo off > start.bat
echo cd /d "%%~dp0" >> start.bat
echo call venv\Scripts\python app.py >> start.bat
echo  [OK] start.bat creado.

REM Crear acceso directo usando archivo PS1 temporal (soporta rutas con espacios)
set "DEST=%USERPROFILE%\Desktop\PrintBridge.lnk"
set "TARGET=%~dp0start.bat"
set "WDIR=%~dp0"
set "PSFILE=%TEMP%\pb_shortcut.ps1"

(
echo $ws = New-Object -ComObject WScript.Shell
echo $s = $ws.CreateShortcut^("%DEST%"^)
echo $s.TargetPath = "%TARGET%"
echo $s.WorkingDirectory = "%WDIR%"
echo $s.Description = "PrintBridge - Servidor de impresion"
echo $s.Save^(^)
) > "%PSFILE%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%PSFILE%"
del "%PSFILE%" >nul 2>&1

if exist "%DEST%" (
    echo  [OK] Acceso directo creado en el escritorio.
) else (
    echo  [AVISO] No se pudo crear el acceso directo. Usa start.bat directamente.
)

echo.
echo  =========================================
echo    Instalacion completada con exito
echo.
echo    - Doble clic en "PrintBridge" en tu
echo      escritorio para iniciar la app.
echo    - O ejecuta start.bat directamente.
echo  =========================================
echo.
echo  Presiona cualquier tecla para iniciar ahora...
pause >nul

call venv\Scripts\python app.py
