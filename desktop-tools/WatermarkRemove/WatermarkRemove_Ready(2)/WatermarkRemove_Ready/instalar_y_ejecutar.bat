@echo off
echo ============================================
echo   WatermarkRemove - Instalacion y Arranque
echo ============================================
echo.

:: Verificar que Python este instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado. Por favor instala Python 3.9 o superior desde:
    echo         https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [OK] Python encontrado:
python --version
echo.

:: Instalar dependencias usando python -m pip
echo Instalando dependencias...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Fallo la instalacion de dependencias.
    echo Intenta ejecutar manualmente: python -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo.
echo [OK] Dependencias instaladas correctamente.
echo.
echo Iniciando WatermarkRemove...
echo.

python main.py

pause
