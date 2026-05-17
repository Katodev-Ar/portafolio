@echo off
REM PrintBridge — Instalación / Desinstalación del Servicio Windows
REM Mejora 7 del Roadmap Técnico
REM
REM Este script NO requiere ejecutarse como administrador.
REM El servicio se instala para el usuario actual.
REM
REM Uso:
REM   service_install.bat install    → instala e inicia el servicio
REM   service_install.bat remove     → detiene y desinstala el servicio

setlocal
cd /d "%~dp0.."

set ACTION=%1
if "%ACTION%"=="" (
    echo.
    echo Uso: service_install.bat [install ^| remove]
    echo.
    echo  install  → Instala PrintBridge como servicio Windows
    echo             (arranca automáticamente con el sistema)
    echo  remove   → Detiene y desinstala el servicio
    echo.
    pause
    exit /b 0
)

REM Verificar que Python esté disponible
python --version >nul 2>&1
if errorlevel 1 (
    REM Intentar con el venv
    if exist "venv\Scripts\python.exe" (
        set PYTHON=venv\Scripts\python.exe
    ) else (
        echo [ERROR] Python no encontrado.
        echo         Ejecuta install.bat primero o instala Python.
        pause
        exit /b 1
    )
) else (
    set PYTHON=python
)

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║         PrintBridge — Servicio Windows                  ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

if /i "%ACTION%"=="install" (
    echo  Instalando servicio PrintBridge...
    %PYTHON% service.py install
    if errorlevel 1 (
        echo.
        echo [ERROR] No se pudo instalar el servicio.
        echo         Verifica que pywin32 esté instalado: pip install pywin32
        pause
        exit /b 1
    )
    echo.
    echo  Iniciando servicio...
    %PYTHON% service.py start
    if errorlevel 1 (
        echo [AVISO] El servicio se instaló pero no pudo iniciarse.
        echo         Revisa el log en data\service.log
    ) else (
        echo.
        echo ╔══════════════════════════════════════════════════════════╗
        echo ║  ✅ PrintBridge instalado y corriendo como servicio     ║
        echo ║                                                          ║
        echo ║  Panel web: https://localhost:7878                       ║
        echo ║  Logs:      data\service.log                            ║
        echo ║                                                          ║
        echo ║  Para desinstalar: service_install.bat remove           ║
        echo ╚══════════════════════════════════════════════════════════╝
    )
) else if /i "%ACTION%"=="remove" (
    echo  Deteniendo y desinstalando servicio PrintBridge...
    %PYTHON% service.py stop  >nul 2>&1
    timeout /t 2 /nobreak >nul
    %PYTHON% service.py remove
    if errorlevel 1 (
        echo [ERROR] No se pudo desinstalar el servicio.
        pause
        exit /b 1
    )
    echo.
    echo ╔══════════════════════════════════════════════════════════╗
    echo ║  ✅ Servicio PrintBridge desinstalado correctamente     ║
    echo ╚══════════════════════════════════════════════════════════╝
) else (
    echo [ERROR] Acción desconocida: %ACTION%
    echo         Usar: install o remove
    exit /b 1
)

echo.
pause
