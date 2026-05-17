@echo off
title Bloom Translator - Servidor de Licencias
color 0A

echo.
echo ============================================
echo    BLOOM TRANSLATOR - SERVIDOR DE LICENCIAS
echo ============================================
echo.
echo Iniciando servidor en localhost:7777...
echo.

REM Verificar si Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no esta instalado
    echo Descarga Python desde: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Instalar dependencias si es necesario
if not exist "venv" (
    echo Creando entorno virtual...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo Instalando dependencias...
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

REM Iniciar servidor
echo.
echo ============================================
echo    SERVIDOR INICIADO
echo ============================================
echo.
echo Panel Admin: http://localhost:7777/admin
echo.
echo Presiona Ctrl+C para detener
echo.

python license_server.py

pause
