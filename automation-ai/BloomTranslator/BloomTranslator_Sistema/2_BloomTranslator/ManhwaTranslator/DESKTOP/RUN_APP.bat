@echo off
title Bloom Translator v2
color 0A

echo.
echo ============================================
echo    BLOOM TRANSLATOR v2
echo    UI Rediseñada
echo ============================================
echo.

REM Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no encontrado.
    echo Descarga Python 3.9+ desde python.org
    pause
    exit /b 1
)

REM Instalar dependencias si necesario
if not exist ".deps_installed" (
    echo Instalando dependencias (solo la primera vez)...
    pip install -r requirements_desktop.txt
    if errorlevel 1 (
        echo ERROR instalando dependencias
        pause
        exit /b 1
    )
    echo. > .deps_installed
)

echo.
echo Iniciando Bloom Translator...
echo Se abrira el navegador automaticamente.
echo Necesitas conexion a internet (servidor en Render.com).
echo Para cerrar, cierra esta ventana.
echo.

python app_desktop.py

pause
