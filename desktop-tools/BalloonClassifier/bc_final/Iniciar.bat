@echo off
REM ============================================================
REM  BalloonClassifier — Lanzador para Windows
REM ============================================================

cd /d "%~dp0"
title BalloonClassifier

echo.
echo  ============================================================
echo   BalloonClassifier - Iniciando...
echo  ============================================================
echo.

REM -- Verificar Python --
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python no encontrado.
    echo  Instala Python 3.10+ desde https://python.org
    echo  Marca "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)

REM -- Verificar dependencias clave, instalar si faltan --
python -c "import torch, torchvision, cv2, sklearn; from PyQt6.QtCharts import QChart" >nul 2>&1
if errorlevel 1 (
    echo  [AVISO] Faltan dependencias. Instalando automaticamente...
    echo  Esto puede tardar unos minutos la primera vez.
    echo.

    python -m pip install --upgrade pip --quiet

    echo  Instalando PyTorch...
    python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
    if errorlevel 1 goto :install_error

    echo  Instalando resto de dependencias...
    python -m pip install opencv-python Pillow numpy scikit-learn matplotlib PyQt6 PyQt6-Charts
    if errorlevel 1 goto :install_error

    REM Verificar de nuevo
    python -c "import torch, torchvision, cv2, sklearn; from PyQt6.QtCharts import QChart" >nul 2>&1
    if errorlevel 1 goto :install_error

    echo.
    echo  [OK] Dependencias instaladas correctamente.
    echo.
)

echo  [OK] Dependencias verificadas. Abriendo aplicacion...
echo.
python main.py

if errorlevel 1 (
    echo.
    echo  ============================================================
    echo   La aplicacion cerro con un error.
    echo   Revisa el archivo: logs\startup_error.txt
    echo  ============================================================
    echo.
    pause
)
exit /b 0

:install_error
echo.
echo  ============================================================
echo   [ERROR] No se pudieron instalar las dependencias.
echo   Ejecuta manualmente: Instalar_Dependencias.bat
echo  ============================================================
echo.
pause
exit /b 1
