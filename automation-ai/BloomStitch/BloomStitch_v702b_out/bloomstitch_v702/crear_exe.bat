@echo off
title BloomStitch v7.2 - Crear EXE
color 0B
echo.
echo  ============================================
echo    BloomStitch v7.2  ^|  Creando .EXE
echo  ============================================
echo.
echo  Modos de compilacion:
echo    [1] --onedir  : EXE + carpeta _internal (arranca rapido, recomendado)
echo    [2] --onefile : Un solo EXE autocontenido (mas facil de compartir)
echo.
set /p MODO="Elige modo [1/2] (Enter = 1): "
if "%MODO%"=="2" (
    set BUILD_MODE=--onefile
    echo  Modo seleccionado: UN SOLO EXE
) else (
    set BUILD_MODE=--onedir
    echo  Modo seleccionado: EXE + carpeta _internal
)
echo.

cd /d "%~dp0"

if not exist "bloomstitch.py" (
    echo  ERROR: No se encontro bloomstitch.py en esta carpeta.
    pause & exit /b 1
)
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: Python no encontrado. Instala Python desde python.org
    pause & exit /b 1
)

echo [1/4] Instalando dependencias...
echo   - pyinstaller
python -m pip install pyinstaller -q
echo   - pillow
python -m pip install pillow -q
echo   - tkinterdnd2
python -m pip install tkinterdnd2 -q
echo   - google-auth-oauthlib
python -m pip install google-auth-oauthlib -q
echo   - google-api-python-client
python -m pip install google-api-python-client -q
if %errorlevel% neq 0 ( echo  ERROR en dependencias. & pause & exit /b 1 )
echo  OK — todas instaladas
echo.

echo [2/4] Compilando BloomStitch.exe...
echo  (puede tardar 2-3 minutos)
echo.

REM IMPORTANTE: NO poner comentarios al final de lineas "set ARGS=..." en batch
REM porque el espacio antes del REM se adjunta a la variable y corrompe el nombre.

set APPNAME=BloomStitch
set ARGS=%BUILD_MODE% --windowed --name %APPNAME% --noconfirm
if exist "icon.ico" set ARGS=%ARGS% --icon icon.ico
set ARGS=%ARGS% --hidden-import PIL
set ARGS=%ARGS% --hidden-import PIL.Image
set ARGS=%ARGS% --hidden-import PIL.ImageTk
set ARGS=%ARGS% --hidden-import tkinterdnd2
set ARGS=%ARGS% --collect-all tkinterdnd2
set ARGS=%ARGS% --hidden-import google.oauth2.credentials
set ARGS=%ARGS% --hidden-import google_auth_oauthlib.flow
set ARGS=%ARGS% --hidden-import googleapiclient.discovery
set ARGS=%ARGS% --hidden-import googleapiclient.http
set ARGS=%ARGS% --collect-all googleapiclient
set ARGS=%ARGS% --collect-all google_auth_oauthlib
set ARGS=%ARGS% --collect-all google.auth
set ARGS=%ARGS% --collect-all google.oauth2
set ARGS=%ARGS% --hidden-import google.auth.transport.requests
set ARGS=%ARGS% --hidden-import google.auth.crypt._python_rsa
set ARGS=%ARGS% --hidden-import google.auth.crypt._helpers
set ARGS=%ARGS% --hidden-import google.auth.crypt.rsa
set ARGS=%ARGS% --hidden-import google.auth.crypt.es256
set ARGS=%ARGS% --hidden-import google.auth._default
set ARGS=%ARGS% --hidden-import google.auth.credentials
set ARGS=%ARGS% --hidden-import google.auth.exceptions
set ARGS=%ARGS% --hidden-import google.oauth2.credentials
set ARGS=%ARGS% --hidden-import google.oauth2.service_account
set ARGS=%ARGS% --hidden-import google_auth_oauthlib.flow
set ARGS=%ARGS% --hidden-import googleapiclient.discovery
set ARGS=%ARGS% --hidden-import googleapiclient.http
set ARGS=%ARGS% --hidden-import googleapiclient.errors
set ARGS=%ARGS% --hidden-import httplib2
set ARGS=%ARGS% --hidden-import uritemplate
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

python -m PyInstaller %ARGS% bloomstitch.py
if %errorlevel% neq 0 ( echo  ERROR de compilacion. & pause & exit /b 1 )

echo.
echo [3/4] Copiando archivos al lado del EXE...
if "%MODO%"=="2" (
    set DEST=dist
) else (
    set DEST=dist\%APPNAME%
)

REM Assets de UI y motor (no embebidos — van al lado del exe)
if exist "icon.png"      copy /y "icon.png"      "%DEST%\" >nul
if exist "icon_alt.png"  copy /y "icon_alt.png"  "%DEST%\" >nul
if exist "splash.png"    copy /y "splash.png"    "%DEST%\" >nul
if exist "startup.wav"   copy /y "startup.wav"   "%DEST%\" >nul
if exist "vcomp140.dll"  copy /y "vcomp140.dll"  "%DEST%\" >nul
if exist "bloom_upscaler.exe" copy /y "bloom_upscaler.exe" "%DEST%\" >nul
if exist "waifu2x-ncnn-vulkan.exe" copy /y "waifu2x-ncnn-vulkan.exe" "%DEST%\bloom_upscaler.exe" >nul

if exist "models-cunet" (
    xcopy /e /i /q /y "models-cunet" "%DEST%\models-cunet\" >nul
)
if exist "models-upconv_7_anime_style_art_rgb" (
    xcopy /e /i /q /y "models-upconv_7_anime_style_art_rgb" "%DEST%\models-upconv_7_anime_style_art_rgb\" >nul
)

echo.
echo [3b/4] Creando acceso directo en el Escritorio...
if "%MODO%"=="2" (
    set EXE=%CD%\dist\%APPNAME%.exe
) else (
    set EXE=%CD%\dist\%APPNAME%\%APPNAME%.exe
)
powershell -NoProfile -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\BloomStitch.lnk');$s.TargetPath='%EXE%';$s.IconLocation='%EXE%,0';$s.Description='BloomStitch v7.2';$s.Save()" >nul 2>&1
if %errorlevel%==0 (echo  Acceso directo OK) else (echo  AVISO: no se pudo crear el acceso directo.)

echo.
echo [4/4] Limpiando temporales...
if exist "build"             rmdir /s /q build
if exist "%APPNAME%.spec"    del /q "%APPNAME%.spec"

echo.
echo  ============================================
echo   LISTO! EXE en: %DEST%\%APPNAME%.exe
echo.
echo   Estructura final:
echo     %DEST%\
echo       BloomStitch.exe
echo       bloom_upscaler.exe
echo       startup.wav
echo       icon.png / splash.png
echo       models-cunet\
echo       models-upconv_7_anime_style_art_rgb\
echo       _internal\   (librerias Python)
echo  ============================================
echo.
pause
