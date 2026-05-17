@echo off
chcp 65001 >nul
title Corrector de Traducciones v8.0 - Crear EXE
color 0B
echo.
echo  ============================================================
echo    Corrector de Traducciones v8.0  ^|  BloomScans
echo    Compilador .EXE con PyInstaller
echo  ============================================================
echo.
echo  Modos de compilacion:
echo    [1] --onedir  : EXE + carpeta _internal (arranca rapido, recomendado)
echo    [2] --onefile : Un solo EXE autocontenido (mas facil de compartir)
echo.
set /p MODO="  Elige modo [1/2] (Enter = 1): "
if "%MODO%"=="2" (
    set BUILD_MODE=--onefile
    echo  Modo seleccionado: UN SOLO EXE
) else (
    set BUILD_MODE=--onedir
    echo  Modo seleccionado: EXE + carpeta _internal
)
echo.

cd /d "%~dp0"

if not exist "corrector_traducciones.py" (
    echo  ERROR: No se encontro corrector_traducciones.py en esta carpeta.
    pause & exit /b 1
)

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: Python no encontrado. Instala Python 3.8+ desde python.org
    pause & exit /b 1
)

echo [1/4] Instalando dependencias...
echo   - pyinstaller
python -m pip install pyinstaller -q
echo   - pillow
python -m pip install pillow -q
echo   - requests
python -m pip install requests -q
echo   - pyspellchecker
python -m pip install pyspellchecker -q
echo   - google-auth-oauthlib
python -m pip install google-auth-oauthlib -q
echo   - google-api-python-client
python -m pip install google-api-python-client -q
if %errorlevel% neq 0 ( echo  ERROR en dependencias. & pause & exit /b 1 )
echo   OK — todas instaladas
echo.

echo [2/4] Compilando CorrectorTraduccionesBloom.exe...
echo   (puede tardar 2-3 minutos)
echo.

set APPNAME=CorrectorTraduccionesBloom
set ARGS=%BUILD_MODE% --windowed --name %APPNAME% --noconfirm
if exist "icon.ico" set ARGS=%ARGS% --icon icon.ico

REM Imports necesarios
set ARGS=%ARGS% --hidden-import PIL
set ARGS=%ARGS% --hidden-import PIL.Image
set ARGS=%ARGS% --hidden-import PIL.ImageTk
set ARGS=%ARGS% --hidden-import requests
set ARGS=%ARGS% --hidden-import spellchecker
set ARGS=%ARGS% --hidden-import google.oauth2.credentials
set ARGS=%ARGS% --hidden-import google_auth_oauthlib.flow
set ARGS=%ARGS% --hidden-import googleapiclient.discovery
set ARGS=%ARGS% --hidden-import googleapiclient.http
set ARGS=%ARGS% --collect-all googleapiclient
set ARGS=%ARGS% --collect-all google_auth_oauthlib

REM Excluir lo que no se necesita (reduce tamaño ~40%%)
set ARGS=%ARGS% --exclude-module matplotlib
set ARGS=%ARGS% --exclude-module numpy
set ARGS=%ARGS% --exclude-module scipy
set ARGS=%ARGS% --exclude-module pandas
set ARGS=%ARGS% --exclude-module IPython
set ARGS=%ARGS% --exclude-module cv2
set ARGS=%ARGS% --exclude-module tensorflow
set ARGS=%ARGS% --exclude-module torch
set ARGS=%ARGS% --exclude-module PyQt5
set ARGS=%ARGS% --exclude-module PyQt6
set ARGS=%ARGS% --exclude-module wx
set ARGS=%ARGS% --exclude-module gi
set ARGS=%ARGS% --exclude-module pygments
set ARGS=%ARGS% --exclude-module docutils
set ARGS=%ARGS% --exclude-module pydoc
set ARGS=%ARGS% --exclude-module unittest
set ARGS=%ARGS% --exclude-module xmlrpc
set ARGS=%ARGS% --exclude-module ftplib
set ARGS=%ARGS% --exclude-module http.server

python -m PyInstaller %ARGS% corrector_traducciones.py
if %errorlevel% neq 0 ( echo  ERROR de compilacion. & pause & exit /b 1 )

echo.
echo [3/4] Copiando archivos extras al lado del EXE...
if "%MODO%"=="2" (
    set DEST=dist
) else (
    set DEST=dist\%APPNAME%
)

REM Copiar archivos opcionales si existen
if exist "icon.ico"             copy /y "icon.ico"             "%DEST%\" >nul
if exist "icon.png"             copy /y "icon.png"             "%DEST%\" >nul
if exist "gemini_api_key.txt"   copy /y "gemini_api_key.txt"   "%DEST%\" >nul
if exist "corrector_gdrive_token.json" copy /y "corrector_gdrive_token.json" "%DEST%\" >nul

echo.
echo [3b/4] Creando acceso directo en el Escritorio...
if "%MODO%"=="2" (
    set EXE=%CD%\dist\%APPNAME%.exe
) else (
    set EXE=%CD%\dist\%APPNAME%\%APPNAME%.exe
)
powershell -NoProfile -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\CorrectorBloom.lnk');$s.TargetPath='%EXE%';$s.IconLocation='%EXE%,0';$s.Description='Corrector de Traducciones BloomScans';$s.Save()" >nul 2>&1
if %errorlevel%==0 (echo   Acceso directo creado en el Escritorio) else (echo   AVISO: no se pudo crear el acceso directo ^(no es critico^).)

echo.
echo [4/4] Limpiando temporales...
if exist "build"                   rmdir /s /q build
if exist "%APPNAME%.spec"          del /q "%APPNAME%.spec"

echo.
echo  ============================================================
echo   LISTO! EXE generado en:
echo     %DEST%\%APPNAME%.exe
echo.
echo   Archivos copiados junto al EXE:
echo     icon.ico / icon.png    (si existian)
echo     gemini_api_key.txt     (tu API key de Gemini)
echo  ============================================================
echo.

if exist "%DEST%\%APPNAME%.exe" (
    echo   Abriendo carpeta dist...
    explorer "%DEST%"
)

pause
